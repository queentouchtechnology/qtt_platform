import unittest

from qtt_platform import erp_kinds as K


class Registry(unittest.TestCase):
	def test_every_link_and_next_is_known(self):
		for k in K.KINDS:
			for f in k["fields"] + (k["table"]["fields"] if k["table"] else []):
				if f["type"] == "link":
					self.assertIn(f["extra"], K.LINKS, (k["key"], f["name"]))
				if f["type"] == "select":
					self.assertTrue(f["extra"], (k["key"], f["name"]))
			for n in k["next"]:
				self.assertIn(n["kind"], K.BY_KEY, k["key"])
				self.assertEqual(K.BY_KEY[n["kind"]]["product"], k["product"], k["key"])
			self.assertIn(k["group"], K.GROUP_ORDER, k["key"])
			self.assertIn(k["scope"], ("company", "tenant", "item", "supplier", "employee", "delivery_note", "maintenance_plan", "global"), k["key"])

	def test_keys_unique_and_no_shared_global_writes(self):
		keys = [k["key"] for k in K.KINDS]
		self.assertEqual(len(keys), len(set(keys)))
		# nothing a business creates may be shared with every other business
		self.assertFalse([k["key"] for k in K.KINDS if k["scope"] == "global" and k["create"]])

	def test_plans_and_areas(self):
		self.assertTrue(K.allowed("sales", None, ["sales"], {}))
		self.assertFalse(K.allowed("sales", "crm", ["sales"], {"crm": 0}))
		self.assertTrue(K.allowed("sales", "crm", ["sales"], {"crm": "1"}))
		self.assertFalse(K.allowed("accounts", None, ["sales"], {}))
		self.assertEqual({k["product"] for k in K.KINDS}, {"QTT_ORBITRA", "QTT_OFFICE_PULSE"})
		self.assertTrue(all(r[6] in ("QTT_ORBITRA", "QTT_OFFICE_PULSE") for r in K.REPORTS.values()))


if __name__ == "__main__":
	unittest.main()
