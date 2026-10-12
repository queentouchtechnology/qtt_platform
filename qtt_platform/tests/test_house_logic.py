"""
Bench-independent tests for the house gate (qtt_platform.house_logic — pure).

	python -m unittest qtt_platform.tests.test_house_logic -v
"""

import unittest

from qtt_platform import house_logic as h


class HouseFeaturesTests(unittest.TestCase):
	ROWS = [  # three Orbitra-like plans
		{"feature_key": "max_stores", "limit_value": "1"}, {"feature_key": "purchases", "limit_value": "0"},
		{"feature_key": "max_stores", "limit_value": "10"}, {"feature_key": "purchases", "limit_value": "1"},
		{"feature_key": "max_users", "limit_value": "50"}, {"feature_key": "reports", "limit_value": "0"},
		{"feature_key": "ai_credits_grant", "limit_value": "2000"}, {"feature_key": "ai_credits_grant", "limit_value": "500"},
		{"feature_key": "tier", "limit_value": "gold"}, {"feature_key": "", "limit_value": "1"},
	]

	def test_counted_limits_are_unlimited_and_flags_are_on(self):
		f = h.house_features(self.ROWS, counted={"max_stores", "max_users"})
		self.assertEqual(f["max_stores"], h.HOUSE_LIMIT)
		self.assertEqual(f["max_users"], h.HOUSE_LIMIT)
		self.assertEqual(f["purchases"], 1)  # the best any plan gives
		self.assertEqual(f["ai_credits_grant"], 2000)  # numbers that aren't counted: the highest
		self.assertEqual(f["tier"], "gold")
		self.assertNotIn("", f)

	def test_a_flag_no_plan_turns_on_stays_off(self):
		self.assertEqual(h.house_features(self.ROWS, counted=set())["reports"], 0)

	def test_no_plans_means_nothing(self):
		self.assertEqual(h.house_features([], counted={"x"}), {})


class BillableLinesTests(unittest.TestCase):
	LINES = [{"description": "Domain and SSL watch — first month", "amount": 299},
			 {"description": "WhatsApp AI receptionist — one-time setup", "amount": 1999}]

	def test_the_house_pays_no_service_fees(self):
		self.assertEqual(h.billable_lines(self.LINES, house=True), [])  # even a service whose title starts with "Domain"

	def test_other_businesses_pay_as_usual(self):
		self.assertEqual(h.billable_lines(self.LINES, house=False), self.LINES)


if __name__ == "__main__":
	unittest.main()
