"""Business and seller verification — python -m unittest qtt_platform.tests.test_verification_rules -v"""

import unittest

from qtt_platform import verification_rules as r


class Numbers(unittest.TestCase):
	def test_clean(self):
		self.assertEqual(r.clean("pan", " abcpd 1234e "), ("ABCPD1234E", None))
		self.assertEqual(r.clean("gstin", "27aaacr5055k1z7"), ("27AAACR5055K1Z7", None))
		self.assertEqual(r.clean("bank", "5010-0242 212344", " hdfc0000123 "), ("50100242212344", "HDFC0000123"))
		self.assertEqual(r.clean("cin", "L17110MH1973PLC019786"), ("L17110MH1973PLC019786", None))
		for kind, n, i in (("pan", "ABCDE12345", None), ("pan", "ABCXD1234E", None), ("gstin", "27AAACR5055K1Z8", None),
						   ("bank", "123", "HDFC0000123"), ("bank", "50100242212344", "HDFC123"), ("cin", "X123", None), ("aadhaar", "1", None)):
			with self.assertRaises(r.VerifyError, msg=(kind, n)):
				r.clean(kind, n, i)

	def test_masked(self):
		self.assertEqual(r.mask("pan", "ABCPD1234E"), "ABCXXXX34E")
		self.assertEqual(r.mask("bank", "50100242212344"), "XXXXXXXXXX2344")
		self.assertEqual(r.mask("gstin", "27AAACR5055K1Z7"), "27AAACR5055K1Z7")
		self.assertNotEqual(r.fingerprint("bank", "1", "A"), r.fingerprint("bank", "1", "B"))


class Answers(unittest.TestCase):
	def test_read(self):
		g = r.read("gstin", 200, {"verified": True, "legal_name": "RELIANCE INDUSTRIES LIMITED", "trade_name": "RELIANCE INDUSTRIES LIMITED", "status": "Active",
								  "constitution": "Public Limited Company", "filing_status": [{"x": 1}], "mobile_number": "98…"})
		self.assertEqual(g["result"], "verified")
		self.assertNotIn("filing_status", g["details"])
		self.assertNotIn("mobile_number", g["details"])
		self.assertEqual(r.read("gstin", 200, {"verified": True, "legal_name": "X", "status": "Cancelled"})["result"], "inactive")
		p = r.read("pan", 200, {"verified": True, "name": "Rohit  Sharma", "aadhaar_linked": True, "aadhaar_number": "72XXXXXXXX67", "dob": "1990-01-15"})
		self.assertEqual((p["record_name"], p["details"]), ("Rohit Sharma", {"aadhaar_linked": True}))
		self.assertEqual(r.read("bank", 200, {"verified": False})["result"], "not_found")
		self.assertEqual(r.read("pan", 422, {"error": {}})["result"], "invalid")
		self.assertEqual([r.read("pan", s, None)["reason"] for s in (401, 402, 429, 500, None)], ["setup", "wallet", "busy", "busy", "busy"])


class Names(unittest.TestCase):
	def test_same_person(self):
		for a, b in (("RAVI KUMAR", "Ravi Kumar"), ("Mr. Ravi Kumar", "KUMAR RAVI"), ("R Kumar", "Ravi Kumar"), ("Vijaykumar", "Vijay Kumar"),
					 ("Mohd Rafiq Khan", "Mohammed Rafik Khan"), ("Preeti Sharma", "Priti Sharma"), ("ABC Traders Pvt Ltd", "ABC TRADERS PRIVATE LIMITED"),
					 ("M/s Sri Balaji Stores", "SRI BALAJI STORES"), ("Ravi Kumar", "Ravi Shankar Kumar")):
			self.assertTrue(r.matches(a, b), (a, b, r.name_score(a, b)))

	def test_different(self):
		for a, b in (("Ravi Kumar", "Suresh Babu"), ("ABC Traders", "XYZ Enterprises"), ("Ravi Kumar", ""), ("Kumar", "Ravi Kumar Sharma")):
			self.assertFalse(r.matches(a, b), (a, b, r.name_score(a, b)))

	def test_summary(self):
		s = r.summary("pan", "verified", "RAVI KUMAR", {}, "Suresh", r.name_score("RAVI KUMAR", "Suresh"), 80)
		self.assertIn("doesn't match", s)
		self.assertIn("matches", r.summary("gstin", "verified", "ABC TRADERS", {"trade_name": "ABC"}, "ABC Traders", 100, 80))
		self.assertNotRegex(" ".join(r.summary(k, res, "", {}, None, None, 80) for k in r.KINDS for res in ("not_found", "invalid", "failed")).lower(), "sathi|api")


if __name__ == "__main__":
	unittest.main()
