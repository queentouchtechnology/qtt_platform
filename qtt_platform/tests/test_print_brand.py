"""
Bench-independent tests for the printed-document helpers (qtt_platform.print_brand):
the HSN-wise GST summary and the brand colour guard, imported against a fake
frappe with sys.modules restored afterwards.

    python -m unittest qtt_platform.tests.test_print_brand -v
"""

import importlib
import json
import sys
import types
import unittest


class _D(dict):
	__getattr__ = dict.get


HSN = {"SOAP": "3401", "OIL": "1508", "SVC": "998314"}


class PrintBrandTest(unittest.TestCase):
	def setUp(self):
		self._modules = dict(sys.modules)
		fake = types.ModuleType("frappe")
		fake._dict = _D
		fake.db = types.SimpleNamespace(
			has_column=lambda doctype, col: True,
			get_value=lambda doctype, name, field, *a, **k: HSN.get(name) if (doctype, field) == ("Item", "qtt_hsn") else None,
		)
		sys.modules["frappe"] = fake
		sys.modules.pop("qtt_platform.print_brand", None)
		self.pb = importlib.import_module("qtt_platform.print_brand")

	def tearDown(self):
		for name in list(sys.modules):
			if name not in self._modules:
				del sys.modules[name]
		sys.modules.update(self._modules)

	@staticmethod
	def _invoice(taxes):
		items = [_D(item_code="SOAP", net_amount=1000.0), _D(item_code="OIL", net_amount=500.0), _D(item_code="SOAP", net_amount=200.0)]
		return _D(items=items, taxes=taxes)

	def test_intrastate_cgst_sgst_by_hsn(self):
		detail = json.dumps({"SOAP": [9, 108.0], "OIL": [2.5, 12.5]})
		doc = self._invoice([
			_D(account_head="Output Tax CGST - QTT", description="CGST", item_wise_tax_detail=detail, tax_amount=120.5),
			_D(account_head="Output Tax SGST - QTT", description="SGST", item_wise_tax_detail=detail, tax_amount=120.5),
		])
		g = self.pb.gst_summary(doc)
		self.assertFalse(g["interstate"])
		rows = {r["hsn"]: r for r in g["rows"]}
		self.assertEqual(rows["3401"]["taxable"], 1200.0)
		self.assertEqual(rows["3401"]["CGST"], 108.0)
		self.assertEqual(rows["3401"]["rate"], 18.0)
		self.assertEqual(rows["1508"]["rate"], 5.0)
		self.assertEqual(g["totals"]["taxable"], 1700.0)
		self.assertEqual(g["totals"]["tax"], 241.0)

	def test_interstate_igst_and_new_style_detail(self):
		detail = json.dumps({"SOAP": {"tax_rate": 18, "tax_amount": 216.0}, "OIL": {"tax_rate": 5, "tax_amount": 25.0}})
		doc = self._invoice([_D(account_head="Output Tax IGST - QTT", description="IGST", item_wise_tax_detail=detail, tax_amount=241.0)])
		g = self.pb.gst_summary(doc)
		self.assertTrue(g["interstate"])
		self.assertEqual({r["hsn"]: r["IGST"] for r in g["rows"]}, {"1508": 25.0, "3401": 216.0})
		self.assertEqual(g["totals"]["IGST"], 241.0)

	def test_non_gst_rows_are_ignored(self):
		doc = self._invoice([_D(account_head="Freight and Forwarding - QTT", description="Delivery", item_wise_tax_detail="{}", tax_amount=50.0)])
		g = self.pb.gst_summary(doc)
		self.assertEqual(g["totals"]["tax"], 0)
		self.assertEqual(g["totals"]["taxable"], 1700.0)

	def test_brand_colour_guard(self):
		self.assertEqual(self.pb._color("#1A2b3C"), "#1A2b3C")
		for bad in (None, "", "red", "#123", "#12345g", "#123456;}body{display:none"):
			self.assertEqual(self.pb._color(bad), self.pb.DEFAULT_COLOR)

	def test_tax_kind(self):
		self.assertEqual(self.pb._tax_kind("Output Tax UTGST - X"), "SGST")
		self.assertEqual(self.pb._tax_kind("Input Tax CGST - X"), "CGST")
		self.assertIsNone(self.pb._tax_kind("Round Off - X"))


if __name__ == "__main__":
	unittest.main()
