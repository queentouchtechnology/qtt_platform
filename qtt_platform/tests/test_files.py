"""
Office Pulse Files — sharing and file control rules (PROJ-0016 A), no bench.

    python -m unittest qtt_platform.tests.test_files -v
"""

import unittest
from datetime import datetime, timedelta

from qtt_platform import files_rules as r

NOW = datetime(2026, 10, 20, 12, 0)


class Rights(unittest.TestCase):
	def test_spaces(self):
		self.assertEqual(r.space_rights("team", hr=False, admin=False), r.FULL)
		self.assertEqual(r.space_rights("company", hr=False, admin=False), {"read"})
		self.assertEqual(r.space_rights("company", hr=True, admin=False), r.FULL)
		self.assertEqual(r.space_rights("hr", hr=False, admin=False), frozenset())
		self.assertEqual(r.space_rights("mydocs", hr=True, admin=True), {"read"})

	def test_folder_rules_deepest_and_most_personal_win(self):
		rules = [{"path": "Payroll", "who_type": "everyone", "rights": ""},
				 {"path": "Payroll", "who_type": "role", "who": "HR Admin", "rights": "read,write,create,delete"},
				 {"path": "Payroll/2026", "who_type": "user", "who": "ann@x.com", "rights": "read"}]
		base = r.FULL
		self.assertEqual(r.folder_rights(base, rules, "Payroll/a.pdf", user="bo@x.com", roles={"HR"}), frozenset())  # nobody else
		self.assertEqual(r.folder_rights(base, rules, "Payroll/a.pdf", user="bo@x.com", roles={"HR Admin"}), {"read", "write", "create", "delete"})
		self.assertEqual(r.folder_rights(base, rules, "Payroll/2026/m.pdf", user="ann@x.com", roles={"HR Admin"}), {"read"})  # deeper wins
		self.assertEqual(r.folder_rights(base, rules, "Payrolls/x.pdf", user="bo@x.com", roles=set()), base)  # not a prefix match
		self.assertEqual(r.folder_rights(base, rules, "../Payroll/a.pdf", user="bo@x.com", roles=set()), frozenset())  # can't climb past

	def test_lock(self):
		self.assertEqual(r.without_lock(r.FULL, "ann", NOW + timedelta(hours=1), "bo", NOW), {"read", "create", "share"})
		self.assertEqual(r.without_lock(r.FULL, "ann", NOW + timedelta(hours=1), "ann", NOW), r.FULL)  # the one who locked it
		self.assertEqual(r.without_lock(r.FULL, "ann", NOW - timedelta(hours=1), "bo", NOW), r.FULL)  # lock ran out


class Links(unittest.TestCase):
	def test_keys_and_passwords(self):
		k = r.new_key()
		self.assertGreaterEqual(len(k), 32)
		self.assertNotEqual(k, r.new_key())
		self.assertEqual(r.key_hash(k), r.key_hash(k))
		h = r.hash_password("s3cret!")
		self.assertTrue(r.check_password("s3cret!", h))
		self.assertFalse(r.check_password("s3cret", h))
		self.assertNotIn("s3cret", h)
		self.assertFalse(r.check_password("x", ""))

	def test_expiry(self):
		self.assertEqual(r.expires_at("1h", NOW), NOW + timedelta(hours=1))
		self.assertEqual(r.expires_at("7d", NOW), NOW + timedelta(days=7))
		self.assertEqual(r.expires_at("date", NOW, "2026-11-01"), datetime(2026, 11, 1, 23, 59, 59))
		self.assertIsNone(r.expires_at("", NOW))
		with self.assertRaises(ValueError):
			r.expires_at("date", NOW, "2026-10-01")

	def test_state(self):
		link = {"status": "Active", "mode": "download", "max_views": 3, "views": 1, "max_downloads": 1, "downloads": 0}
		self.assertEqual(r.link_state(link, NOW), "ok")
		self.assertEqual(r.link_state({**link, "status": "Revoked"}, NOW), "revoked")
		self.assertEqual(r.link_state({**link, "expires_at": NOW - timedelta(seconds=1)}, NOW), "expired")
		self.assertEqual(r.link_state({**link, "views": 3}, NOW), "used_up")
		self.assertEqual(r.link_state({**link, "downloads": 1}, NOW, "download"), "used_up")
		self.assertEqual(r.link_state({**link, "mode": "preview"}, NOW, "download"), "no")  # preview only
		self.assertEqual(r.link_state({**link, "mode": "upload"}, NOW, "view"), "no")  # File Drop shows nothing
		self.assertEqual(r.link_state({**link, "mode": "upload"}, NOW, "upload"), "ok")

	def test_emails(self):
		link = {"allowed_emails": "Ann@X.com, bo@y.in;junk"}
		self.assertEqual(r.emails(link["allowed_emails"]), ["ann@x.com", "bo@y.in"])
		self.assertTrue(r.needs_email(link))
		self.assertTrue(r.email_allowed(link, " ANN@x.com"))
		self.assertFalse(r.email_allowed(link, "eve@x.com"))
		self.assertTrue(r.email_allowed({"require_approval": 1}, "anyone@z.com"))
		self.assertFalse(r.needs_email({}))
		self.assertRegex(r.new_code(), r"^\d{6}$")


class Automation(unittest.TestCase):
	RULE = {"enabled": 1, "event": "upload", "space": "hr", "folder": "Inbox", "kinds": "pdf", "name_words": "payslip, salary", "has_tag": ""}

	def test_matches(self):
		self.assertTrue(r.auto_matches(self.RULE, event="upload", space="hr", path="Inbox/Payslip Oct.pdf", kind="pdf", tags=[]))
		self.assertTrue(r.auto_matches(self.RULE, event="upload", space="hr", path="Inbox/2026/salary.pdf", kind="pdf", tags=[]))  # any depth
		self.assertFalse(r.auto_matches(self.RULE, event="upload", space="hr", path="Inbox/Offer letter.pdf", kind="pdf", tags=[]))  # no word
		self.assertFalse(r.auto_matches(self.RULE, event="upload", space="hr", path="Inbox/payslip.docx", kind="word", tags=[]))  # not a PDF
		self.assertFalse(r.auto_matches(self.RULE, event="upload", space="team", path="Inbox/payslip.pdf", kind="pdf", tags=[]))  # other space
		self.assertFalse(r.auto_matches(self.RULE, event="upload", space="hr", path="Payslip.pdf", kind="pdf", tags=[]))  # not in the folder
		self.assertFalse(r.auto_matches({**self.RULE, "enabled": 0}, event="upload", space="hr", path="Inbox/payslip.pdf", kind="pdf", tags=[]))
		tag_rule = {"enabled": 1, "event": "tag", "has_tag": "Invoices"}
		self.assertTrue(r.auto_matches(tag_rule, event="tag", space="team", path="a/b.pdf", kind="pdf", tags=["invoices"]))
		self.assertFalse(r.auto_matches(tag_rule, event="upload", space="team", path="a/b.pdf", kind="pdf", tags=["invoices"]))

	def test_folder_and_tags(self):
		self.assertEqual(r.auto_folder("Payslips/{year}/{month}", datetime(2026, 10, 20)), "Payslips/2026/10")
		self.assertEqual(r.auto_folder("../Archive/{month_name}", datetime(2026, 10, 20)), "Archive/October")
		self.assertEqual(r.auto_tags("Payslip, HR,, Payslip"), ["Payslip", "HR"])


class Text(unittest.TestCase):
	def _zip(self, files: dict) -> bytes:
		import io
		import zipfile

		b = io.BytesIO()
		with zipfile.ZipFile(b, "w") as z:
			for n, t in files.items():
				z.writestr(n, t)
		return b.getvalue()

	def test_office_and_text(self):
		from qtt_platform import files_text as ft

		docx = self._zip({"word/document.xml": "<w:document><w:body><w:p><w:r><w:t>Offer letter for Ann</w:t></w:r></w:p><w:p><w:t>Salary &amp; benefits</w:t></w:p></w:body></w:document>"})
		t = ft.text_of("Offer.docx", docx)
		self.assertIn("Offer letter for Ann", t)
		self.assertIn("Salary & benefits", t)
		xlsx = self._zip({"xl/sharedStrings.xml": "<sst><si><t>Invoice</t></si><si><t>GST 18%</t></si></sst>", "xl/worksheets/sheet1.xml": "<sheetData><row><c><v>1250</v></c></row></sheetData>"})
		self.assertIn("GST 18%", ft.text_of("Budget.xlsx", xlsx))
		self.assertIn("1250", ft.text_of("Budget.xlsx", xlsx))
		pptx = self._zip({"ppt/slides/slide2.xml": "<p:sld><a:p><a:t>Second</a:t></a:p></p:sld>", "ppt/slides/slide1.xml": "<p:sld><a:p><a:t>First</a:t></a:p></p:sld>"})
		self.assertLess(ft.text_of("Deck.pptx", pptx).index("First"), ft.text_of("Deck.pptx", pptx).index("Second"))
		self.assertEqual(ft.text_of("notes.txt", b"hello\n\n\nworld"), "hello\nworld")
		self.assertEqual(ft.text_of("photo.jpg", b"\xff\xd8"), "")
		self.assertEqual(ft.text_of("broken.docx", b"not a zip"), "")  # never raises

	def test_pdf(self):
		from qtt_platform import files_text as ft

		try:
			from pypdf import PdfWriter
		except ImportError:
			self.skipTest("pypdf is on the server")
		import io

		w = PdfWriter()
		w.add_blank_page(100, 100)
		b = io.BytesIO()
		w.write(b)
		self.assertEqual(ft.text_of("blank.pdf", b.getvalue()), "")

	def test_snippet_and_words(self):
		from qtt_platform import files_text as ft

		self.assertEqual(ft.search_words('  GST "invoice" a 2026  '), ["gst", "invoice", "2026"])
		s = ft.snippet("x " * 200 + "the GST invoice for October " + "y " * 200, ["invoice"])
		self.assertIn("GST invoice", s)
		self.assertTrue(s.startswith("…"))
		self.assertEqual(ft.snippet("nothing here", ["gst"]), "")


if __name__ == "__main__":
	unittest.main()
