"""Explore QTT OS (qtt_platform.explore_rules) — no bench.

    python -m unittest qtt_platform.tests.test_explore_rules -v
"""

import unittest

from qtt_platform import explore_rules as r


class Features(unittest.TestCase):
	def test_onbox_starter_reads_plainly(self):
		lines = r.feature_lines({"max_agents": "3", "max_inboxes": "2", "channel_whatsapp": "1", "channel_website": "1",
								 "channel_email": "1", "ai_agent": "0", "ai_credits_grant": "0"})
		self.assertEqual(lines, ["3 team members", "2 inboxes", "WhatsApp, Website chat and Email"])

	def test_a_limit_of_one_reads_singular(self):
		self.assertEqual(r.feature_lines({"max_users": 2, "max_stores": 1}, "QTT_ORBITRA"), ["2 users", "1 store or branch"])
		self.assertIn("1 landing page", r.feature_lines({"studio_pages": 1}, "QTT_STUDIO"))

	def test_limits_switches_and_unknown_keys(self):
		self.assertEqual(r.feature_lines({"max_employees": "200", "payroll": "1"}), ["Up to 200 employees", "Payroll and payslips"])
		self.assertEqual(r.feature_lines({"max_users": "0"}), ["Unlimited users"])
		self.assertEqual(r.feature_lines({"ai_credits_grant": "2000", "ai_agent": "1"}), ["2,000 AI replies a month", "AI assistant replies for you"])
		self.assertEqual(r.feature_lines({"internal_flag": "1", "max_assets": "50", "max_users": "x"}), [])


class Trials(unittest.TestCase):
	def test_once_per_app(self):
		self.assertTrue(r.can_trial(14, had_before=False))
		self.assertFalse(r.can_trial(14, had_before=True))
		self.assertFalse(r.can_trial(0, had_before=False))


class Status(unittest.TestCase):
	def test_what_the_business_has(self):
		self.assertIsNone(r.app_status(None, False))
		self.assertIsNone(r.app_status({"status": "cancelled"}, False))
		self.assertEqual(r.app_status({"status": "trialing"}, False), "trial")
		self.assertEqual(r.app_status({"status": "past_due"}, True), "active")
		self.assertEqual(r.app_status({"status": "suspended", "paid_until": None}, True), "awaiting_payment")
		self.assertEqual(r.app_status({"status": "suspended", "paid_until": "2026-10-01"}, True), "paused")

class StudioWords(unittest.TestCase):
	def test_studio_credits_are_not_ai_replies(self):
		from qtt_platform.explore_rules import feature_lines

		f = {"studio_designs": "100", "ai_credits_grant": "400", "studio_doc_templates": "0", "studio_design_mode": "1"}
		lines = feature_lines(f, "QTT_STUDIO")
		self.assertIn("100 new designs a month", lines)
		self.assertIn("400 AI credits a month", lines)
		self.assertIn("Unlimited document templates of your own", lines)
		self.assertIn("Design mode (drag and drop)", lines)
		self.assertIn("400 AI replies a month", feature_lines({"ai_credits_grant": "400"}))  # Onbox keeps its words
		self.assertEqual(feature_lines({"studio_designs": "100"}), [])  # Studio's keys mean nothing elsewhere

