"""
Bench-independent tests for the disk forecast (ops.server_health) and the certificate watch (ops.cert_watch).

    python -m unittest qtt_platform.tests.test_ops_watch -v
"""

import unittest
from datetime import datetime, timedelta

from qtt_platform.ops import cert_watch as c
from qtt_platform.ops import server_health as h

NOW = datetime(2026, 11, 12, 12, 0)


def hourly(start_gb, per_day, hours=7 * 24):
	return [(NOW - timedelta(hours=hours - i), start_gb + per_day * i / 24) for i in range(hours + 1)]


class DiskForecastTest(unittest.TestCase):
	def test_growing_disk(self):
		f = h.disk_forecast(hourly(50, 2.0), 72)  # the n8n server on 12 Nov: ~2 GB a day
		self.assertAlmostEqual(f["per_day_gb"], 2.0, places=3)
		self.assertAlmostEqual(f["days"], (72 * 0.95 - 64) / 2, places=2)

	def test_no_worry(self):
		self.assertIsNone(h.disk_forecast(hourly(50, 0.0), 72))  # flat
		self.assertIsNone(h.disk_forecast(hourly(50, -1.0), 72))  # shrinking
		self.assertIsNone(h.disk_forecast(hourly(50, 2.0, hours=12), 72))  # under a day of data
		self.assertIsNone(h.disk_forecast([], 72))
		self.assertIsNone(h.disk_forecast(hourly(50, 2.0), None))

	def test_counts_only_after_a_cleanup(self):
		before = hourly(40, 3.0)[:100]
		after = [(t, 20 + 0.01 * i) for i, (t, _) in enumerate(hourly(0, 0)[100:])]  # cleaned up, then 0.24 GB a day
		f = h.disk_forecast(before + after, 72)
		self.assertAlmostEqual(f["per_day_gb"], 0.24, places=3)  # the 3 GB a day before the cleanup doesn't count
		self.assertGreater(f["days"], 100)

	def test_full_already(self):
		self.assertEqual(h.disk_forecast(hourly(68.5, 1.0), 72)["days"], 0.0)

	def test_evaluate_levels(self):
		report = {"disk_used_pct": 60}
		ev = lambda days, **lim: h.evaluate(report, last_report_at=NOW, now=NOW, limits=lim, forecast={"days": days, "per_day_gb": 1.94})
		self.assertEqual(ev(30)["status"], "ok")
		w = ev(10)
		self.assertEqual((w["status"], w["problems"][0]["text"]), ("warning", "Disk full in about 10 days (growing 1.9 GB a day)."))
		self.assertEqual(ev(3.4)["status"], "critical")
		self.assertEqual(ev(0.5)["problems"][0]["text"], "Disk full within a day (growing 1.9 GB a day).")
		self.assertEqual(ev(20, disk_full_warn_days=30)["status"], "warning")  # own limit from QTT Ops Settings
		self.assertEqual(h.evaluate(report, last_report_at=NOW, now=NOW)["status"], "ok")  # no forecast


class CertWatchTest(unittest.TestCase):
	def test_parse_hosts(self):
		self.assertEqual(c.parse_hosts("app.queentouchtech.in\nhttps://N8N.queentouchtech.in/healthz\n# note\n\nnot a host\n"
									   "app.queentouchtech.in\nshare.queentouchtech.in:443  # files"),
						 ["app.queentouchtech.in", "n8n.queentouchtech.in", "share.queentouchtech.in"])

	def run_days(self, days_list, warn=14):
		state, alerts = None, []
		for d in days_list:
			state, a = c.step(state, host="n8n.x", days=d, error=None, warn_days=warn)
			alerts.append(a)
		return state, alerts

	def test_reminders_only_at_steps(self):
		_, alerts = self.run_days([31, 20, 14, 13, 10, 7, 6, 3, 2, 1, 0, -1, -1])
		sent = [a for a in alerts if a]
		self.assertEqual(len(sent), 6)  # 14, 7, 3, 1, 0, expired
		self.assertIn("expires in 14 days", sent[0])
		self.assertTrue(sent[2].startswith("🔴"))
		self.assertIn("EXPIRED", sent[-1])
		self.assertEqual(alerts[:2], [None, None])

	def test_renewed(self):
		state, alerts = self.run_days([10, 89])
		self.assertIn("fine again", alerts[1])
		self.assertIsNone(state["bucket"])
		self.assertEqual(self.run_days([60, 89])[1], [None, None])

	def test_errors_need_two_in_a_row(self):
		s, a1 = c.step(None, host="x.in", days=None, error="timed out", warn_days=14)
		self.assertIsNone(a1)
		self.assertEqual(c.level(None, s["error"], s["fails"], 14), "ok")
		s, a2 = c.step(s, host="x.in", days=None, error="timed out", warn_days=14)
		self.assertIn("Certificate problem: x.in", a2)
		s, a3 = c.step(s, host="x.in", days=None, error="timed out", warn_days=14)
		self.assertIsNone(a3)  # once
		s, a4 = c.step(s, host="x.in", days=70, error=None, warn_days=14)
		self.assertIn("fine again", a4)
		_, blip = c.step(c.step(None, host="x.in", days=None, error="reset", warn_days=14)[0], host="x.in", days=70, error=None, warn_days=14)
		self.assertIsNone(blip)  # one failed read, then fine: nothing to say

	def test_problems_for_needs_attention(self):
		states = {"a.in": {"days": 70, "fails": 0}, "b.in": {"days": 5, "fails": 0}, "c.in": {"days": 2, "fails": 0},
				  "d.in": {"days": None, "fails": 2, "error": "self-signed"}, "e.in": {"days": None, "fails": 1, "error": "reset"}}
		out = c.problems(["a.in", "b.in", "c.in", "d.in", "e.in", "f.in"], states, 14)
		self.assertEqual([(p["title"], p["status"]) for p in out], [("b.in", "warning"), ("c.in", "critical"), ("d.in", "critical")])
		self.assertEqual(out[0]["problems"], "Certificate expires in 5 days.")
		self.assertIsNone(out[0]["key"])


if __name__ == "__main__":
	unittest.main()
