"""
Bench-independent tests for free use (qtt_platform.free_use): all 8 apps free until one limit, then one plan.

    python -m unittest qtt_platform.tests.test_free_use -v
"""

import unittest

from qtt_platform import free_use as f


class LimitsTest(unittest.TestCase):
	def test_defaults_are_the_standard_set(self):
		self.assertEqual(f.limits_from({}), {"hr": 10, "erp": 50, "website": 1, "store": 20, "whatsapp": 100, "social": 10,
											 "articles": 3, "newsletters": 2, "studio": 10})
		self.assertEqual(len(f.APPS), 9)  # the 8 apps, with articles and newsletters counted apart

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


class PeriodTest(unittest.TestCase):
	def test_free_amounts_say_how_they_count(self):
		apps = {a["key"]: a for a in f.status({}, f.DEFAULT_LIMITS)["apps"]}
		self.assertEqual(apps["hr"]["period"], "at_a_time")
		self.assertEqual(apps["website"]["period"], "at_a_time")
		self.assertEqual(apps["erp"]["period"], "in_total")
		self.assertEqual(apps["newsletters"]["period"], "in_total")


class PlanMonthTest(unittest.TestCase):
	def test_month_window_from_the_plan_date(self):
		from datetime import date
		self.assertEqual(f.month_window(date(2026, 11, 15), date(2026, 12, 3)), (date(2026, 11, 15), date(2026, 12, 14)))
		self.assertEqual(f.month_window(date(2026, 11, 15), date(2026, 12, 15)), (date(2026, 12, 15), date(2027, 1, 14)))
		self.assertEqual(f.month_window(date(2026, 1, 31), date(2026, 2, 28)), (date(2026, 2, 28), date(2026, 3, 30)))
		self.assertEqual(f.month_window(date(2026, 11, 15), date(2026, 11, 1)), (date(2026, 11, 15), date(2026, 12, 14)))


class FairUseTest(unittest.TestCase):
	def test_defaults_and_desk(self):
		self.assertEqual(f.plan_limits_from({})["offer_messages"], 1000)
		self.assertEqual(f.plan_limits_from({"plan_limit_ai": 800, "plan_limit_social": 0})["ai"], 800)
		self.assertEqual(f.plan_limits_from({"plan_limit_social": 0})["social"], 0)  # 0 = unlimited

	def test_status_with_topups_near_and_reached(self):
		s = f.plan_status({"offer_messages": 840, "ai": 500, "hr": 12}, f.DEFAULT_PLAN_LIMITS, {"ai": 1000})
		items = {i["key"]: i for i in s["items"]}
		self.assertTrue(items["offer_messages"]["near"])
		self.assertEqual((items["ai"]["limit"], items["ai"]["left"], items["ai"]["reached"]), (1500, 1000, False))
		self.assertEqual(items["hr"]["period"], "at_a_time")
		self.assertEqual(s["near"], ["offer_messages"])
		unlimited = f.plan_status({"social": 999}, {**f.DEFAULT_PLAN_LIMITS, "social": 0})
		self.assertIsNone(next(i for i in unlimited["items"] if i["key"] == "social")["limit"])

	def test_blocked_counts_topups_and_batch_size(self):
		lim = f.DEFAULT_PLAN_LIMITS
		self.assertFalse(f.plan_blocked("offer_messages", 900, lim, adding=100))
		self.assertTrue(f.plan_blocked("offer_messages", 900, lim, adding=101))
		self.assertFalse(f.plan_blocked("offer_messages", 900, lim, {"offer_messages": 2000}, adding=500))
		self.assertFalse(f.plan_blocked("erp", 10**6, lim))  # not a fair-use item: unlimited
		self.assertFalse(f.plan_blocked("social", 999, {**lim, "social": 0}))

	def test_topup_packs_from_desk(self):
		packs = f.topups_from({"topup_messages_price": 599, "topup_ai_amount": 2000})
		self.assertEqual((packs["messages"]["price"], packs["messages"]["amount"]), (599.0, 2000))
		self.assertEqual((packs["ai"]["amount"], packs["ai"]["price"]), (2000, 299.0))
		self.assertEqual(packs["site"]["adds"], "website")


class PlanTest(unittest.TestCase):
	def test_prices(self):
		self.assertEqual(f.plan_prices({}), {"monthly": 1999.0, "yearly": 19990.0})
		self.assertEqual(f.plan_prices({"one_plan_monthly": 2499, "one_plan_yearly": 0}), {"monthly": 2499.0, "yearly": 19990.0})


if __name__ == "__main__":
	unittest.main()
