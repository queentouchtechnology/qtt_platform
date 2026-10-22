import unittest

from qtt_platform import feature_access as fa


class FeatureAccess(unittest.TestCase):
	def test_words(self):
		self.assertEqual(fa.who_can(["*"], None), "Everyone in the business")
		self.assertEqual(fa.who_can(["@owner", "HR Admin"], "QTT_OFFICE_PULSE"), "Owner and admins; Office Pulse: HR Admin")
		self.assertEqual(fa.who_can([], None), "Nobody (hidden)")

	def test_every_screen_becomes_a_row(self):
		reg = fa.registry()
		rs = fa.rows(reg)
		self.assertEqual(len(rs), len(reg["screens"]))
		ids = [r["screen_id"] for r in rs]
		self.assertEqual(len(ids), len(set(ids)))
		self.assertTrue(all(r["who_can_open"] and r["title"] for r in rs))


if __name__ == "__main__":
	unittest.main()
