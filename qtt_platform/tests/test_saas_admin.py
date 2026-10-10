"""
Bench-independent tests for QTT Admin → SaaS rules
(qtt_platform.saas_admin_logic — no frappe import).

    python -m unittest qtt_platform.tests.test_saas_admin -v
"""

import unittest
from datetime import date

from qtt_platform import saas_admin_logic as logic
from qtt_platform.saas_admin_logic import SaasInputError

TODAY = date(2026, 10, 10)


class PlanTest(unittest.TestCase):
	def test_new_plan_cleaned(self):
		clean = logic.clean_plan({
			"plan_code": "growth_2", "product": "QTT_INBOX", "display_name": " Growth ", "base_price": "1499",
			"billing_period": "Monthly", "trial_days": "14", "is_public": True,
			"features": [{"feature_key": "Max_Agents", "limit_value": 10}, {"feature_key": "", "limit_value": "x"}],
		}, is_new=True)
		self.assertEqual(clean["plan_code"], "GROWTH_2")
		self.assertEqual((clean["display_name"], clean["base_price"], clean["billing_period"], clean["trial_days"], clean["is_public"]),
						 ("Growth", 1499.0, "monthly", 14, 1))
		self.assertEqual(clean["features"], [{"feature_key": "max_agents", "limit_value": "10"}])

	def test_edit_ignores_code_and_product(self):
		clean = logic.clean_plan({"plan_code": "HACK", "product": "OTHER", "display_name": "Pro", "base_price": 0}, is_new=False)
		self.assertNotIn("plan_code", clean)
		self.assertNotIn("product", clean)

	def test_rejects_bad_plans(self):
		bad = [
			{"display_name": "x"},
			{"display_name": "Pro", "base_price": "-1"},
			{"display_name": "Pro", "base_price": "abc"},
			{"display_name": "Pro", "billing_period": "weekly"},
			{"display_name": "Pro", "trial_days": "400"},
			{"display_name": "Pro", "features": [{"feature_key": "a.b", "limit_value": "1"}, {"feature_key": "a.b", "limit_value": "2"}]},
			{"display_name": "Pro", "features": [{"feature_key": "max agents", "limit_value": "1"}]},
			{"display_name": "Pro", "features": [{"feature_key": "max_agents", "limit_value": ""}]},
		]
		for plan in bad:
			with self.subTest(plan=plan), self.assertRaises(SaasInputError):
				logic.clean_plan(plan, is_new=False)
		with self.assertRaises(SaasInputError):
			logic.clean_plan({"display_name": "Pro", "plan_code": "bad code", "product": "X"}, is_new=True)

	def test_billing_changed(self):
		self.assertTrue(logic.billing_changed({"base_price": 999}, {"base_price": 1499}))
		self.assertTrue(logic.billing_changed({"base_price": 999, "billing_period": "monthly"}, {"base_price": 999, "billing_period": "yearly"}))
		self.assertFalse(logic.billing_changed({"base_price": 999.0, "billing_period": "monthly"}, {"base_price": 999, "billing_period": "monthly"}))


class TrialTest(unittest.TestCase):
	def test_extends_running_trial(self):
		self.assertEqual(logic.extended_trial(status="trialing", trial_end="2026-10-15", linked_to_gateway=False, days=7, today=TODAY),
						 ("trialing", date(2026, 10, 22)))

	def test_restarts_expired_trial_from_today(self):
		self.assertEqual(logic.extended_trial(status="suspended", trial_end="2026-09-01", linked_to_gateway=False, days=14, today=TODAY),
						 ("trialing", date(2026, 10, 24)))

	def test_refusals(self):
		cases = [
			dict(status="trialing", trial_end="2026-10-15", linked_to_gateway=True, days=7),
			dict(status="active", trial_end=None, linked_to_gateway=False, days=7),
			dict(status="suspended", trial_end=None, linked_to_gateway=False, days=7),
			dict(status="trialing", trial_end="2026-10-15", linked_to_gateway=False, days=0),
			dict(status="trialing", trial_end="2026-10-15", linked_to_gateway=False, days=91),
		]
		for case in cases:
			with self.subTest(case=case), self.assertRaises(SaasInputError):
				logic.extended_trial(today=TODAY, **case)


class RevenueTest(unittest.TestCase):
	def test_mrr(self):
		self.assertEqual(logic.monthly_value(12000, "yearly"), 1000)
		self.assertEqual(logic.monthly_value(999, "monthly", [{"unit_price": 100, "quantity": 2}]), 1199)
		summary = logic.revenue_summary([
			{"product": "QTT_INBOX", "status": "active", "base_price": 1000, "billing_period": "monthly"},
			{"product": "QTT_INBOX", "status": "past_due", "base_price": 500, "billing_period": "monthly"},
			{"product": "QTT_LMS", "status": "active", "base_price": 24000, "billing_period": "yearly"},
			{"product": "QTT_INBOX", "status": "trialing", "base_price": 1000, "billing_period": "monthly"},
			{"product": "QTT_INBOX", "status": "cancelled", "base_price": 9999, "billing_period": "monthly"},
		])
		self.assertEqual(summary["mrr"], 3500)
		self.assertEqual(summary["arr"], 42000)
		self.assertEqual(summary["at_risk_mrr"], 500)
		self.assertEqual(summary["trial_mrr"], 1000)
		self.assertEqual(summary["mrr_by_product"], {"QTT_INBOX": 1500, "QTT_LMS": 2000})
		self.assertEqual(summary["counts"], {"active": 2, "trialing": 1, "past_due": 1})


if __name__ == "__main__":
	unittest.main()
