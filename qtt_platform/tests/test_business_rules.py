"""
Bench-independent tests for business / customer profile checks
(qtt_platform.business_rules — pure).

    python -m unittest qtt_platform.tests.test_business_rules -v
"""

import importlib
import sys
import types
import unittest

from qtt_platform import business_rules as r


class GstinTest(unittest.TestCase):
	def test_valid_and_normalised(self):
		self.assertEqual(r.clean_gstin(" 27aapfu0939f1zv "), "27AAPFU0939F1ZV")
		self.assertEqual(r.gst_state("33AAACI1195H1ZT"), "Tamil Nadu")
		self.assertIsNone(r.clean_gstin(""))

	def test_wrong_check_character(self):
		with self.assertRaisesRegex(r.ProfileError, "last character"):
			r.clean_gstin("27AAPFU0939F1ZA")

	def test_bad_shape_or_state(self):
		for bad in ("27AAPFU0939F1Z", "99AAPFU0939F1ZV", "27AAPFU0939F1XV"):
			with self.assertRaises(r.ProfileError):
				r.clean_gstin(bad)

	def test_pan_must_match_gstin(self):
		r.check_gstin_pan("27AAPFU0939F1ZV", "AAPFU0939F")
		with self.assertRaisesRegex(r.ProfileError, "doesn't match"):
			r.check_gstin_pan("27AAPFU0939F1ZV", "ABCDE1234F")


class FieldsTest(unittest.TestCase):
	def test_pan_ifsc_account_upi(self):
		self.assertEqual(r.clean_pan("abcde1234f"), "ABCDE1234F")
		self.assertEqual(r.clean_ifsc("sbin0001234"), "SBIN0001234")
		self.assertEqual(r.clean_account_number("1234 5678-9012"), "123456789012")
		self.assertEqual(r.clean_upi("Shop.Name@OKAXIS"), "shop.name@okaxis")
		for fn, bad in ((r.clean_pan, "ABCD1234F"), (r.clean_ifsc, "SBIN1001234"),
						(r.clean_account_number, "12ab"), (r.clean_upi, "no-at-sign")):
			with self.assertRaises(r.ProfileError):
				fn(bad)

	def test_colour_url_email_pincode(self):
		self.assertEqual(r.clean_colour("3858f8"), "#3858F8")
		self.assertEqual(r.clean_url("www.example.com"), "https://www.example.com")
		self.assertEqual(r.clean_email(" Hello@Example.COM "), "hello@example.com")
		self.assertEqual(r.clean_pincode("628 001"), "628001")
		self.assertEqual(r.clean_pincode("SW1A1AA", "United Kingdom"), "SW1A1AA")
		for fn, bad in ((r.clean_colour, "#38F"), (r.clean_url, "not a site"), (r.clean_email, "a@b"),
						(r.clean_pincode, "012345")):
			with self.assertRaises(r.ProfileError):
				fn(bad)


class PhoneTest(unittest.TestCase):
	def test_normalise(self):
		self.assertEqual(r.normalize_phone("98765 43210"), "+919876543210")
		self.assertEqual(r.normalize_phone("098765-43210"), "+919876543210")
		self.assertEqual(r.normalize_phone("+91 98765 43210"), "+919876543210")
		self.assertEqual(r.normalize_phone("0044 20 7946 0958"), "+442079460958")
		self.assertEqual(r.normalize_phone("+971 50 123 4567"), "+971501234567")
		self.assertIsNone(r.normalize_phone("12345"))
		with self.assertRaises(r.ProfileError):
			r.clean_phone("call me")


class TagsTest(unittest.TestCase):
	def test_clean_and_split(self):
		self.assertEqual(r.clean_tags(" VIP, wholesale ,vip,,  Repeat   buyer"), "VIP, wholesale, Repeat buyer")
		self.assertEqual(r.clean_tags(["A", "a", "B"]), "A, B")
		self.assertIsNone(r.clean_tags(""))
		self.assertEqual(r.tag_list("VIP, Wholesale"), ["VIP", "Wholesale"])


class _StubFrappe(unittest.TestCase):
	"""Imports an api module against a stand-in frappe (sys.modules restored)."""

	module = ""

	def setUp(self):
		self._modules = dict(sys.modules)
		fake = types.ModuleType("frappe")
		fake._ = lambda s: s
		fake.whitelist = lambda *a, **k: (lambda fn: fn)
		utils = types.ModuleType("frappe.utils")
		utils.get_url = lambda p: "https://app.example.com" + p
		fake.utils = utils
		sys.modules["frappe"] = fake
		sys.modules["frappe.utils"] = utils
		for name in [n for n in sys.modules if n.startswith("qtt_platform.") and "tests" not in n]:
			sys.modules.pop(name)
		self.api = importlib.import_module(self.module)

	def tearDown(self):
		for name in list(sys.modules):
			if name not in self._modules:
				del sys.modules[name]
		sys.modules.update(self._modules)


class CleanCustomerTest(_StubFrappe):
	module = "qtt_platform.api.customers"

	def test_business_customer(self):
		c = self.api.clean_customer({"customer_name": "  Bala Stores ", "customer_type": "Business", "phone": "98765 43210",
									 "gstin": "33aaaci1195h1zt", "tags": "vip, VIP, Wholesale", "pincode": "625 001"}, "India")
		self.assertEqual(c["customer_name"], "Bala Stores")
		self.assertEqual(c["phone"], "+919876543210")
		self.assertEqual(c["pan"], "AAACI1195H")  # from the GSTIN
		self.assertEqual(c["state"], "Tamil Nadu")  # from the GSTIN
		self.assertEqual(c["tags"], "vip, Wholesale")
		self.assertEqual(c["country"], "India")

	def test_name_required_and_type_defaults(self):
		with self.assertRaises(r.ProfileError):
			self.api.clean_customer({"customer_name": " "}, "India")
		self.assertEqual(self.api.clean_customer({"customer_name": "A", "customer_type": "Alien"}, None)["customer_type"], "Individual")


class CleanProfileTest(_StubFrappe):
	module = "qtt_platform.api.business"

	def test_profile(self):
		p = self.api.clean_profile({"gstin": "27AAPFU0939F1ZV", "brand_color": "0f766e", "website": "acme.in",
									"bank_ifsc": "hdfc0001234", "upi_id": "Acme@OkHdfc", "state": "MH"}, "India")
		self.assertEqual(p["pan"], "AAPFU0939F")
		self.assertEqual(p["state"], "MH")  # kept when given
		self.assertEqual(p["brand_color"], "#0F766E")
		self.assertEqual(p["website"], "https://acme.in")
		self.assertEqual(p["bank_ifsc"], "HDFC0001234")
		self.assertEqual(p["upi_id"], "acme@okhdfc")

	def test_mismatched_pan_rejected(self):
		with self.assertRaises(r.ProfileError):
			self.api.clean_profile({"gstin": "27AAPFU0939F1ZV", "pan": "ABCDE1234F"}, "India")

	def test_logo_url_made_absolute(self):
		self.assertEqual(self.api.absolute_url("/files/logo.png"), "https://app.example.com/files/logo.png")
		self.assertIsNone(self.api.absolute_url(None))


if __name__ == "__main__":
	unittest.main()
