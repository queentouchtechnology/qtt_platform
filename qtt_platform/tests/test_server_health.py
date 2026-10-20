"""
Bench-independent tests for QTT Admin → Servers health rules
(qtt_platform.ops.server_health).

    python -m unittest qtt_platform.tests.test_server_health -v
"""

import unittest
from datetime import datetime, timedelta

from qtt_platform.ops import server_health as h

NOW = datetime(2026, 10, 10, 12, 0)


def raw(**over):
	r = {
		"hostname": "vmi2682166", "cpu_count": 3, "load": [0.2, 0.3, 0.4], "uptime_seconds": 3600,
		"disk": {"total_bytes": 72e9, "used_bytes": 60e9}, "memory": {"total_bytes": 8e9, "available_bytes": 3e9},
		"containers": [{"name": "chatwoot", "state": "running"}, {"name": "qdrant", "state": "running"}],
		"ports": [{"port": 443, "public": True}, {"port": 5432, "public": True}, {"port": 3306, "public": False}],
		"reboot_required": True, "security_updates": 3, "firewall_active": False, "ssh_password_login": True, "ssh_failed_24h": 19346,
	}
	r.update(over)
	return r


class CleanTest(unittest.TestCase):
	def test_numbers(self):
		c = h.clean_report(raw())
		self.assertEqual((c["disk_used_pct"], c["disk_total_gb"], c["mem_used_pct"]), (83.3, 72.0, 62.5))
		self.assertEqual(c["cpu_count"], 3)

	def test_bounds_and_junk(self):
		c = h.clean_report(raw(containers=[{"state": "running"}] + [{"name": f"c{i}", "state": "running"} for i in range(200)],
							   ports=[{"port": 99999}, {"port": "22", "public": True}], firewall_active="yes"))
		self.assertEqual(len(c["containers"]), h.MAX_CONTAINERS)
		self.assertEqual(c["ports"], [{"port": 22, "public": True, "process": ""}])
		self.assertIsNone(c["firewall_active"])
		with self.assertRaises(h.ReportError):
			h.clean_report({"disk": {}, "memory": {}})
		with self.assertRaises(h.ReportError):
			h.clean_report("nope")


class EvaluateTest(unittest.TestCase):
	def test_warning_with_notices(self):
		e = h.evaluate(h.clean_report(raw()), last_report_at=NOW - timedelta(minutes=2), now=NOW)
		self.assertEqual(e["status"], "ok")  # 83% disk is under the 85% warning
		self.assertIn("Open to the internet: 5432 (PostgreSQL).", e["notices"])
		self.assertIn("Reboot needed for updates.", e["notices"])
		self.assertIn("19346 failed SSH logins in 24 h.", e["notices"])

	def test_levels(self):
		disk = h.evaluate(h.clean_report(raw(disk={"total_bytes": 100, "used_bytes": 96})), last_report_at=NOW, now=NOW)
		self.assertEqual(disk["status"], "critical")
		down = h.evaluate(h.clean_report(raw(containers=[{"name": "chatwoot", "state": "exited"}])), last_report_at=NOW, now=NOW)
		self.assertEqual(down["status"], "critical")
		self.assertIn("chatwoot", down["problems"][0]["text"])
		load = h.evaluate(h.clean_report(raw(load=[9, 9, 9])), last_report_at=NOW, now=NOW)
		self.assertEqual(load["status"], "warning")
		swap = h.evaluate(h.clean_report(raw(swap={"used_pct": 92.5})), last_report_at=NOW, now=NOW)
		self.assertEqual((swap["status"], swap["problems"][0]["text"]), ("warning", "Swap 92% used (memory is short)."))
		limits = h.evaluate(h.clean_report(raw()), last_report_at=NOW, now=NOW, limits={"disk_warn": 80})
		self.assertEqual(limits["status"], "warning")

	def test_offline(self):
		self.assertEqual(h.evaluate(None, last_report_at=None, now=NOW)["status"], "offline")
		old = h.evaluate(h.clean_report(raw()), last_report_at=NOW - timedelta(minutes=40), now=NOW)
		self.assertEqual((old["status"], old["problems"][0]["text"]), ("offline", "No report for 40 minutes."))


class AlertTest(unittest.TestCase):
	def test_only_on_change(self):
		self.assertIsNone(h.alert_for_change("ok", "ok", "Frappe", []))
		self.assertIsNone(h.alert_for_change(None, "ok", "Frappe", []))
		self.assertEqual(h.alert_for_change("ok", "critical", "n8n", [{"level": "critical", "text": "Disk 96% full."}]),
						 "🔴 n8n: critical. Disk 96% full.")
		self.assertEqual(h.alert_for_change("offline", "ok", "n8n", []), "✅ n8n is healthy again.")

	def test_thin(self):
		pts = [{"i": i} for i in range(1000)]
		t = h.thin(pts, 100)
		self.assertEqual(len(t), 100)
		self.assertEqual((t[0]["i"], t[-1]["i"]), (0, 999))
		self.assertEqual(h.thin(pts[:5], 100), pts[:5])



class HermesTest(unittest.TestCase):
	def test_counts_kept_everything_else_dropped(self):
		c = h.clean_report(raw(hermes={"allowed_users": 1, "gateway_running": True, "sessions": 4, "users": 2, "sessions_7d": 3,
										"users_7d": 2, "messages_7d": 40, "cost_usd": 0.42, "cost_usd_7d": 0.1,
										"by_source_7d": {"telegram": 3}, "chat_ids": ["12345"]}))["hermes"]
		self.assertEqual((c["allowed_users"], c["users_7d"], c["messages_7d"], c["cost_usd"]), (1, 2, 40, 0.42))
		self.assertEqual(c["by_source_7d"], {"telegram": 3})
		self.assertNotIn("chat_ids", c)  # only the whitelisted counts reach Frappe
		self.assertIsNone(h.clean_report(raw())["hermes"])  # no Hermes on this server

	def test_gateway_down_is_a_notice(self):
		down = h.clean_report(raw(hermes={"gateway_running": False}))
		ev = h.evaluate(down, last_report_at=NOW, now=NOW)
		self.assertIn("Hermes gateway (Telegram) is not running.", ev["notices"])


class BackupsTest(unittest.TestCase):
	"""The server's backup jobs: a failed or missed one is a problem (QTT Admin › Servers, and the alert)."""

	def ev(self, backups):
		small = raw(disk={"total_bytes": 100, "used_bytes": 10}, containers=[], reboot_required=False, backups=backups)
		return h.evaluate(h.clean_report(small), last_report_at=NOW, now=NOW)

	def test_fresh_ok(self):
		e = self.ev([{"name": "Frappe sites", "ok": True, "finished_at": NOW.timestamp() - 3600, "size_bytes": 6e6}])
		self.assertEqual(e["status"], "ok")

	def test_failed_and_missed(self):
		e = self.ev([{"name": "Frappe sites", "ok": False, "finished_at": NOW.timestamp(), "detail": "bench backup failed"},
					 {"name": "Files store copy", "ok": True, "finished_at": NOW.timestamp() - 30 * 3600}])
		self.assertEqual(e["status"], "warning")
		texts = [p["text"] for p in e["problems"]]
		self.assertIn("Backup failed: Frappe sites — bench backup failed.", texts)
		self.assertIn("Backup missed: Files store copy — last one 30 h ago.", texts)

	def test_own_limit_and_junk(self):
		e = self.ev([{"name": "Weekly", "ok": True, "finished_at": NOW.timestamp() - 100 * 3600, "max_age_hours": 170}, {"ok": True}, "x"])
		self.assertEqual(e["status"], "ok")
		self.assertEqual(h.clean_report(raw())["backups"], [])


if __name__ == "__main__":
	unittest.main()
