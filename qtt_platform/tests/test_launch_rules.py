import unittest

from qtt_platform import launch_rules as r


class LaunchRules(unittest.TestCase):
	def test_goals_only_point_at_real_products(self):
		for key, (_t, _l, _i, products, services) in r.GOALS.items():
			self.assertTrue(products, key)
			self.assertTrue(set(products) <= set(r.PRODUCTS), key)
			self.assertTrue(set(services) <= set(r.SERVICES), key)
		self.assertEqual(len(r.goals()), len(r.GOALS))

	def test_recommend_orders_by_goals(self):
		out = r.recommend(["team"])
		self.assertEqual(out[0]["product"], "QTT_OFFICE_PULSE")
		self.assertTrue(out[0]["recommended"])
		self.assertEqual(len(out), 4)
		self.assertFalse(out[-1]["recommended"])
		both = r.recommend(["customers", "content"])
		self.assertEqual({both[0]["product"], both[1]["product"]}, {"QTT_SERVICES", "QTT_STUDIO"})
		self.assertEqual(r.recommend([], {"QTT_ORBITRA": "active"})[1]["have"], "active")
		self.assertTrue(all(not x["recommended"] for x in r.recommend(["nonsense"])))

	def test_suite_pick(self):
		self.assertEqual(r.suite_pick(["customers"]), ["WEBSITE_DEV", "MARKETING_ASSISTANT"])
		self.assertEqual(r.suite_pick(["customers", "sell_online"]), ["ECOMMERCE_STORE", "MARKETING_ASSISTANT"])
		self.assertEqual(r.suite_pick(["team"]), [])

	def test_steps(self):
		self.assertTrue(all(s["done"] for s in r.steps("app", "trial")))
		self.assertEqual([s["done"] for s in r.steps("service", "awaiting_payment")], [False] * 4)
		self.assertEqual([s["done"] for s in r.steps("service", "setup", "building")], [True, False, False, False])
		self.assertEqual([s["done"] for s in r.steps("service", "setup", "preview")], [True, True, False, False])
		self.assertEqual([s["done"] for s in r.steps("service", "active", "live")], [True] * 4)


if __name__ == "__main__":
	unittest.main()
