"""
Office Pulse Contacts (PROJ-0016 C2) — vCard in and out. No bench.

    python -m unittest qtt_platform.tests.test_contacts -v
"""

import unittest

from qtt_platform import contacts_rules as c

PHONE_EXPORT = """BEGIN:VCARD
VERSION:3.0
N:Kumar;Ravi;;;
FN:Ravi Kumar
ORG:Sri Balaji Traders;
item1.TEL;type=CELL:+91 98765 43210
TEL;type=HOME:044 2345 6789
EMAIL;type=INTERNET:Ravi@Balaji.in
ADR;type=WORK:;;12 Main Road;Madurai;Tamil Nadu;625001;India
NOTE:Supplies packing boxes\\, every Monday
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:No number
END:VCARD
BEGIN:VCARD
VERSION:2.1
N:;Anand Steel;;;
ORG:Anand Steel
TEL;CELL:98400
 12345
END:VCARD
"""


class VCard(unittest.TestCase):
	def test_read_a_phone_export(self):
		rows = c.parse_vcf(PHONE_EXPORT)
		self.assertEqual(len(rows), 2)  # the card without a number or email is left out
		r = rows[0]
		self.assertEqual((r["customer_name"], r["company_name"]), ("Ravi Kumar", "Sri Balaji Traders"))
		self.assertEqual((r["phone"], r["whatsapp"]), ("+91 98765 43210", "044 2345 6789"))
		self.assertEqual(r["email"], "ravi@balaji.in")
		self.assertEqual((r["city"], r["state"], r["pincode"]), ("Madurai", "Tamil Nadu", "625001"))
		self.assertEqual(r["notes"], "Supplies packing boxes, every Monday")
		self.assertEqual(rows[1]["phone"], "9840012345")  # a folded line joins up
		self.assertEqual(rows[1]["customer_name"], "Anand Steel")

	def test_write_and_read_back(self):
		row = {"customer_name": "Meena; Exports", "company_name": "Meena Co", "phone": "+919876500000", "email": "m@co.in", "city": "Salem",
			   "notes": "Line one\nLine two", "kind": "Supplier"}
		vcf = c.to_vcf([row])
		self.assertIn("FN:Meena\\; Exports", vcf)
		self.assertIn("CATEGORIES:Supplier", vcf)
		back = c.parse_vcf(vcf)[0]
		self.assertEqual((back["customer_name"], back["phone"], back["city"], back["notes"]), ("Meena; Exports", "+919876500000", "Salem", "Line one\nLine two"))
		self.assertEqual(c.to_vcf([]), "")


if __name__ == "__main__":
	unittest.main()
