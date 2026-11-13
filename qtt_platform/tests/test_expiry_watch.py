"""
Bench-independent tests for the expiry register and the Monday ops report (ops.expiry_watch).

    python -m unittest qtt_platform.tests.test_expiry_watch -v
"""

import unittest
from datetime import date

from qtt_platform.ops import expiry_watch as e

TODAY = date(2026, 11, 13)


class ExpiryTest(unittest.TestCase):
	def test_reminder_steps(self):
		prev, sent = None, []
		for days in (60, 31, 30, 29, 20, 14, 10, 7, 5, 3, 2, 1, 0, -1, -2):
			prev, now = e.step(prev, days)
			if now:
				sent.append(days)
		self.assertEqual(sent, [30, 14, 7, 3, 1, 0, -1])  # one reminder per step

	def test_renewed_goes_quiet(self):
		prev, _ = e.step(None, 5)
		self.assertEqual(prev, 7)
		prev, now = e.step(prev, 365)
		self.assertEqual((prev, now), (None, False))
		self.assertEqual(e.step(prev, 30), (30, True))  # a year later: reminders start again

	def test_first_check_already_close(self):
		self.assertEqual(e.step(None, 2), (3, True))  # added late: one reminder now, not every step skipped
		self.assertEqual(e.step(3, 2), (3, False))

	def test_texts(self):
		t = e.reminder(title="GitHub QTT-AI-OS token", kind="Access token", days=7, used_by="n8n daily report", renew_how="GitHub › Settings")
		self.assertEqual(t, "🟠 Access token: GitHub QTT-AI-OS token expires in 7 days.\nUsed by: n8n daily report\nRenew: GitHub › Settings")
		self.assertTrue(e.reminder(title="x", kind=None, days=0, used_by=None, renew_how=None).startswith("🔴 Expiry: x expires TODAY"))
		self.assertIn("EXPIRED 2 days ago", e.when(-2))
		self.assertIn("in 1 day", e.when(1))

	def test_problems(self):
		items = [{"title": "a", "kind": "API key", "expires_on": date(2026, 11, 20), "watch": 1},
				 {"title": "b", "kind": "Domain", "expires_on": date(2026, 11, 14), "watch": 1},
				 {"title": "c", "kind": "Domain", "expires_on": date(2026, 11, 14), "watch": 0},
				 {"title": "d", "kind": "Domain", "expires_on": date(2027, 1, 1), "watch": 1}]
		self.assertEqual([(p["title"], p["status"], p["problems"]) for p in e.problems(items, TODAY)],
						 [("a", "warning", "API key expires in 7 days."), ("b", "critical", "Domain expires in 1 day.")])


class DigestTest(unittest.TestCase):
	def base(self, **kw):
		args = dict(today=TODAY, servers=[{"title": "Frappe", "status": "ok", "problems": None, "disk_pct": 67.2, "forecast_days": None}],
					certs=[{"host": "a.in", "days": 60, "error": None}, {"host": "b.in", "days": 45, "error": None}],
					expiries=[{"title": "token", "kind": "Access token", "days": 200}], domains=[{"domain": "x.org", "days": 100}],
					n8n={"failing": []}, jobs_age_minutes=2)
		args.update(kw)
		return e.digest(**args)

	def test_all_quiet(self):
		t = self.base()
		self.assertIn("All quiet", t)
		self.assertIn("🟢 Frappe — disk 67%", t)
		self.assertIn("2 watched, all fine (nearest renewal in 45 days)", t)
		self.assertIn("✅ no failed runs", t)
		self.assertIn("✅ running", t)

	def test_things_to_look_at(self):
		t = self.base(servers=[{"title": "n8n", "status": "warning", "problems": "Disk 93% full.", "disk_pct": 93, "forecast_days": 3.2}],
					  certs=[{"host": "a.in", "days": 12, "error": None}, {"host": "c.in", "days": None, "error": "self-signed"},
							 {"host": "d.in", "days": 28, "error": None}],
					  expiries=[{"title": "token", "kind": "Access token", "days": 5}], domains=[{"domain": "truthofbible.org", "days": 18}],
					  n8n={"failing": [("Daily report", 7)]}, jobs_age_minutes=200)
		self.assertIn("👀 7 things to look at.", t)
		self.assertIn("🟠 n8n — disk 93%, full in ~3 days\n   Disk 93% full.", t)
		self.assertLess(t.index("c.in"), t.index("a.in"))  # unreadable first
		self.assertIn("🔁 d.in — 28 days left (should renew this week)", t)
		self.assertIn("🟠 Access token: token — expires in 5 days", t)
		self.assertIn("🟠 Domain truthofbible.org — expires in 18 days", t)
		self.assertIn("🟠 Daily report — 7 failed runs", t)
		self.assertIn("🔴 no scheduled job for 200 minutes", t)

	def test_cant_check_and_length(self):
		t = self.base(n8n={"error": "n8n not configured"}, jobs_age_minutes=None, certs=[])
		self.assertIn("couldn't check: n8n not configured", t)
		self.assertIn("— none watched", t)
		long = self.base(servers=[{"title": f"s{i}", "status": "warning", "problems": "x" * 240, "disk_pct": 50, "forecast_days": None}
								  for i in range(40)])
		self.assertLessEqual(len(long), 3800)
		self.assertTrue(long.endswith("…(shortened)"))


if __name__ == "__main__":
	unittest.main()
