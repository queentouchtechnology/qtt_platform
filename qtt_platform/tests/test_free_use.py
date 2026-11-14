"""
Bench-independent tests for free use (qtt_platform.free_use): all 8 apps free until one limit, then one plan.

    python -m unittest qtt_platform.tests.test_free_use -v
"""

import unittest

from qtt_platform import free_use as f


class LimitsTest(unittest.TestCase):
	def test_defaults_are_the_standard_set(self):
		self.assertEqual(f.limits_from({}), {"hr": 10, "erp": 50, "website": 1, "store": 20, "whatsapp": 100, "social": 10,
											 "articles": 3, "studio": 10})
		self.assertEqual(len(f.APPS), 8)

	def test_desk_values_win_and_zero_means_no_limit(self):
		lim = f.limits_from({"free_limit_hr": 25, "free_limit_erp": 0, "free_limit_social": None, "free_limit_store": "x"})
		self.assertEqual((lim["hr"], lim["erp"], lim["social"], lim["store"]), (25, 0, 10, 0))


class StatusTest(unittest.TestCase):
	def test_left_and_reached(self):
		s = f.status({"hr": 4, "website": 1, "social": 12}, f.DEFAULT_LIMITS)
		apps = {a["key"]: a for a in s["apps"]}
		self.assertEqual((apps["hr"]["used"], apps["hr"]["left"], apps["hr"]["reached"]), (4, 6, False))
		self.assertTrue(apps["website"]["reached"])
		self.assertEqual(apps["social"]["left"], 0)
		self.assertTrue(s["gate"])
		self.assertEqual(s["reached"], ["website", "social"])

	def test_no_gate_when_subscribed_or_switched_off(self):
		for kw in ({"subscribed": True}, {"enabled": False}):
			s = f.status({"hr": 99}, f.DEFAULT_LIMITS, **kw)
			self.assertFalse(s["gate"])
			self.assertFalse(s["limited"])
			self.assertIsNone(s["apps"][0]["limit"])

	def test_zero_limit_is_unlimited(self):
		s = f.status({"erp": 500}, {**f.DEFAULT_LIMITS, "erp": 0})
		erp = next(a for a in s["apps"] if a["key"] == "erp")
		self.assertEqual((erp["limit"], erp["left"], erp["reached"]), (None, None, False))


class BlockedTest(unittest.TestCase):
	def test_up_to_the_limit_then_blocked(self):
		self.assertFalse(f.blocked("hr", 9, f.DEFAULT_LIMITS))
		self.assertTrue(f.blocked("hr", 10, f.DEFAULT_LIMITS))
		self.assertTrue(f.blocked("hr", 8, f.DEFAULT_LIMITS, adding=3))

	def test_never_blocked_when_subscribed_off_unknown_or_unlimited(self):
		self.assertFalse(f.blocked("hr", 50, f.DEFAULT_LIMITS, subscribed=True))
		self.assertFalse(f.blocked("hr", 50, f.DEFAULT_LIMITS, enabled=False))
		self.assertFalse(f.blocked("rocket", 50, f.DEFAULT_LIMITS))
		self.assertFalse(f.blocked("erp", 500, {**f.DEFAULT_LIMITS, "erp": 0}))


class PlanTest(unittest.TestCase):
	def test_prices(self):
		self.assertEqual(f.plan_prices({}), {"monthly": 1999.0, "yearly": 19990.0})
		self.assertEqual(f.plan_prices({"one_plan_monthly": 2499, "one_plan_yearly": 0}), {"monthly": 2499.0, "yearly": 19990.0})


if __name__ == "__main__":
	unittest.main()
