"""
Bench-independent tests for QTT Admin → SaaS rules
(qtt_platform.saas_admin_logic — no frappe import).

    python -m unittest qtt_platform.tests.test_saas_admin -v
"""

import unittest
from datetime import date

from qtt_platform import saas_admin_logic as logic

TODAY = date(2026, 10, 10)


class RevenueTest(unittest.TestCase):
	def test_mrr(self):
		self.assertEqual(logic.monthly_value(12000, "yearly"), 1000)
		self.assertEqual(logic.monthly_value(999, "monthly", [{"unit_price": 100, "quantity": 2}]), 1199)
		summary = logic.revenue_summary([
			{"product": "QTT_ONBOX", "status": "active", "base_price": 1000, "billing_period": "monthly"},
			{"product": "QTT_ONBOX", "status": "past_due", "base_price": 500, "billing_period": "monthly"},
			{"product": "QTT_LMS", "status": "active", "base_price": 24000, "billing_period": "yearly"},
			{"product": "QTT_ONBOX", "status": "trialing", "base_price": 1000, "billing_period": "monthly"},
			{"product": "QTT_ONBOX", "status": "cancelled", "base_price": 9999, "billing_period": "monthly"},
		])
		self.assertEqual(summary["mrr"], 3500)
		self.assertEqual(summary["arr"], 42000)
		self.assertEqual(summary["at_risk_mrr"], 500)
		self.assertEqual(summary["trial_mrr"], 1000)
		self.assertEqual(summary["mrr_by_product"], {"QTT_ONBOX": 1500, "QTT_LMS": 2000})
		self.assertEqual(summary["counts"], {"active": 2, "trialing": 1, "past_due": 1})


if __name__ == "__main__":
	unittest.main()


class AttentionTest(unittest.TestCase):
	def test_ranked_most_urgent_first(self):
		items = logic.attention_items(
			servers=[{"key": "n8n", "title": "n8n", "status": "warning", "problems": "Swap 92% used"},
					 {"key": "cp", "title": "Cloud Panel", "status": "offline", "problems": None}],
			trials=[{"tenant": "T2", "tenant_name": "Bala", "product": "QTT_ONBOX", "trial_end": "2026-10-17"},
					{"tenant": "T3", "tenant_name": "Acme", "product": "QTT_ONBOX", "trial_end": "2026-10-11"}],
			past_due=[{"tenant": "T4", "tenant_name": "Zed", "product": "QTT_OFFICE_PULSE"}],
			approvals=[{"name": "C1", "title": "LinkedIn post"}, {"name": "C2", "title": "Article"}],
			setup_errors=[{"tenant": "T5", "tenant_name": "Kay", "product": "Inbox", "error": "Chatwoot 401"}],
			today_str="2026-10-10",
		)
		self.assertEqual([i["kind"] for i in items], ["server", "setup", "payment", "server", "trial", "approval", "trial"])
		self.assertEqual(items[0]["title"], "Cloud Panel")  # offline = critical
		trial_soon = next(i for i in items if i["kind"] == "trial" and i["target"] == "T3")
		self.assertEqual((trial_soon["level"], trial_soon["days"]), ("warning", 1))
		self.assertEqual(items[-1]["days"], 7)  # a week away is just info
		approval = next(i for i in items if i["kind"] == "approval")
		self.assertEqual((approval["count"], approval["area"]), (2, "marketing"))

	def test_marketing_assistant(self):
		items = logic.attention_items(marketing=[
			{"level": "info", "what": "occasion_dates", "count": 2, "title": "Deepavali", "detail": "Deepavali, Pongal"},
			{"level": "critical", "what": "renderer_down", "count": 1, "title": "renderer", "detail": "ConnectTimeout"},
		], today_str="2026-10-10")
		self.assertEqual([i["what"] for i in items], ["renderer_down", "occasion_dates"])  # down first
		self.assertEqual((items[0]["kind"], items[0]["area"], items[0]["target"]), ("marketing", "marketing_assistant", "renderer_down"))
		self.assertEqual(items[1]["count"], 2)

	def test_nothing_to_do(self):
		self.assertEqual(logic.attention_items(today_str="2026-10-10"), [])


class RevenueCountsOnlyBilled(unittest.TestCase):
	def test_house_and_unbilled_are_not_revenue(self):
		from qtt_platform import saas_admin_logic as L

		self.assertFalse(L.counts_as_revenue({"is_house": 1, "billing_mode": "invoice"}))
		self.assertFalse(L.counts_as_revenue({"is_house": 0, "billing_mode": None}))
		self.assertFalse(L.counts_as_revenue({"is_house": 0, "billing_mode": ""}))
		self.assertTrue(L.counts_as_revenue({"is_house": 0, "billing_mode": "invoice"}))
		self.assertTrue(L.counts_as_revenue({"is_house": 0, "billing_mode": "razorpay"}))

