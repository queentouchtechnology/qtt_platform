"""Roles and access (qtt_platform.role_access_rules) — no bench.

    python -m unittest qtt_platform.tests.test_role_access
"""

import unittest

from qtt_platform import role_access_rules as r

SPEC = {
	"product": "QTT_ORBITRA",
	"areas": [{"key": k, "label": k.title()} for k in ("pos", "sales", "inventory", "inventory_edit", "reports", "settings")],
	"roles": [{"key": k, "label": k} for k in ("Orbitra Admin", "Manager", "Cashier")],
	"grants": {"Orbitra Admin": ["pos", "sales", "inventory", "inventory_edit", "reports", "settings"],
			   "Manager": ["pos", "sales", "inventory", "inventory_edit", "reports"], "Cashier": ["pos", "sales", "inventory"]},
	"editable": ["Manager", "Cashier"],
	"fixed_areas": ["settings"],
	"requires": {"inventory_edit": ["inventory"]},
}


class RoleAccessTest(unittest.TestCase):
	def test_defaults_until_the_owner_changes_something(self):
		self.assertEqual(r.effective(SPEC, "Cashier", None), ["pos", "sales", "inventory"])
		self.assertEqual(r.effective(SPEC, "Cashier", ["pos", "reports"]), ["pos", "reports"])

	def test_admin_and_fixed_areas_never_change(self):
		self.assertEqual(r.effective(SPEC, "Orbitra Admin", ["pos"]), SPEC["grants"]["Orbitra Admin"])  # not editable
		self.assertEqual(r.effective(SPEC, "Cashier", ["pos", "settings"]), ["pos"])  # settings stays admin's
		with self.assertRaises(r.AccessError):
			r.change(SPEC, ["pos"], "Orbitra Admin", "pos", False)
		with self.assertRaises(r.AccessError):
			r.change(SPEC, ["pos"], "Cashier", "settings", True)

	def test_switching_one_area(self):
		self.assertEqual(r.change(SPEC, ["pos", "sales", "inventory"], "Cashier", "reports", True), ["pos", "sales", "inventory", "reports"])
		self.assertEqual(r.change(SPEC, ["pos", "sales"], "Cashier", "inventory_edit", True), ["pos", "sales", "inventory", "inventory_edit"])
		self.assertEqual(r.change(SPEC, ["pos", "inventory", "inventory_edit"], "Manager", "inventory", False), ["pos"])  # edit needs see
		with self.assertRaises(r.AccessError):
			r.change(SPEC, ["pos"], "Cashier", "pos", False)  # nothing left

	def test_the_table_and_the_assistant_line(self):
		m = r.matrix(SPEC, {"Cashier": ["pos", "reports"]})
		reports = next(row for row in m["rows"] if row["key"] == "reports")
		cashier = next(c for c in reports["cells"] if c["role"] == "Cashier")
		self.assertEqual((cashier["on"], cashier["changed"], cashier["can_change"]), (True, True, True))
		admin = next(c for c in reports["cells"] if c["role"] == "Orbitra Admin")
		self.assertFalse(admin["can_change"])
		self.assertTrue(m["changed"])
		line = r.describe(SPEC, {"Cashier": ["pos", "reports"]})
		self.assertIn("Cashier (changed by the owner): Pos, Reports", line)
		self.assertIn("Manager: Pos, Sales, Inventory, Inventory_Edit, Reports", line)
		self.assertEqual(r.describe(SPEC, {}, only_role="Cashier"), "Cashier: Pos, Sales, Inventory")


if __name__ == "__main__":
	unittest.main()
