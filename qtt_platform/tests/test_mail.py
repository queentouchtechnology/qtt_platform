"""
Office Pulse Mail (PROJ-0016 C3) — settings, reading, writing, folders. No bench, no mail server.

    python -m unittest qtt_platform.tests.test_mail -v
"""

import unittest

from qtt_platform import mail_rules as m

RAW = (b"From: =?utf-8?b?4K6w4K6/4K6v4K6+?= <Riya@Example.com>\r\nTo: ann@qtt.in, Bo <bo@qtt.in>\r\nSubject: =?utf-8?q?Invoice_=E2=82=B9_12,000?=\r\n"
	   b"Date: Tue, 20 Oct 2026 09:30:00 +0530\r\nMessage-ID: <abc@example.com>\r\nMIME-Version: 1.0\r\n"
	   b"Content-Type: multipart/mixed; boundary=XX\r\n\r\n--XX\r\nContent-Type: multipart/alternative; boundary=YY\r\n\r\n"
	   b"--YY\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPlease pay by Friday.\r\n--YY\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
	   b"<p onclick=\"steal()\">Please pay</p><script>alert(1)</script><img src=\"https://track.example/p.gif\"><a href=\"javascript:x()\">x</a>\r\n"
	   b"--YY--\r\n--XX\r\nContent-Type: application/pdf; name=inv.pdf\r\nContent-Disposition: attachment; filename=inv.pdf\r\nContent-Transfer-Encoding: base64\r\n\r\n"
	   b"JVBERi0xLjQ=\r\n--XX--\r\n")


class Settings(unittest.TestCase):
	def test_guess(self):
		self.assertEqual(m.guess("a@gmail.com")["imap_host"], "imap.gmail.com")
		self.assertIn("app password", m.guess("a@gmail.com")["note"])
		o = m.guess("a@outlook.com")
		self.assertEqual((o["smtp_port"], o["smtp_starttls"]), (587, True))
		self.assertEqual(m.guess("sales@queentouchtech.in")["imap_host"], "mail.queentouchtech.in")


class Reading(unittest.TestCase):
	def test_read(self):
		r = m.read(RAW)
		self.assertEqual(r["subject"], "Invoice ₹ 12,000")
		self.assertEqual(r["from"][0], {"name": "ரியா", "email": "riya@example.com"})
		self.assertEqual([a["email"] for a in r["to"]], ["ann@qtt.in", "bo@qtt.in"])
		self.assertEqual(r["date"][:10], "2026-10-20")
		self.assertIn("Please pay by Friday.", r["text"])
		self.assertNotIn("<script", r["html"])
		self.assertNotIn("onclick", r["html"])
		self.assertNotIn("javascript:", r["html"])
		self.assertTrue(r["remote_images"])
		self.assertNotIn(' src="https://track', r["html"])  # held back
		self.assertEqual([(a["name"], a["type"]) for a in r["attachments"]], [("inv.pdf", "application/pdf")])
		name, ctype, data = m.attachment(RAW, 0)
		self.assertEqual((name, data[:4]), ("inv.pdf", b"%PDF"))
		self.assertIsNone(m.attachment(RAW, 5))


class Writing(unittest.TestCase):
	def test_compose_reply(self):
		self.assertEqual(m.reply_subject("RE: Fwd: Invoice"), "Re: Invoice")
		self.assertEqual(m.reply_subject("Invoice", forward=True), "Fwd: Invoice")
		msg = m.compose(from_email="ann@qtt.in", from_name="Ann", to=["riya@example.com"], cc=[], bcc=["boss@qtt.in"], subject="Re: Invoice",
						text="Paid today.", signature="Ann · QTT", in_reply_to="<abc@example.com>", attachments=[("r.pdf", "application/pdf", b"%PDF")])
		self.assertEqual(msg["In-Reply-To"], "<abc@example.com>")
		self.assertIn("<abc@example.com>", msg["References"])
		raw = msg.as_bytes()
		self.assertIn(b"Paid today.", raw)
		self.assertIn(b"-- \n", raw.replace(b"\r\n", b"\n"))
		self.assertIn(b'filename="r.pdf"', raw)

	def test_clean_list(self):
		self.assertEqual(m.clean_list("Riya <riya@x.com>; bo@y.in, not-an-email, bo@y.in"), ["riya@x.com", "bo@y.in"])


class Folders(unittest.TestCase):
	def test_names(self):
		self.assertEqual(m.folder_name("&BCcEPwQ1BDQ-"), "Чпед")
		for n in ("Sent", "Rechnungen & Belege", "அனுப்பியவை", "Archive/2026"):
			self.assertEqual(m.folder_name(m.folder_encode(n)), n)
		f = m.parse_list_line('(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"')
		self.assertEqual((f["name"], f["role"]), ("[Gmail]/Sent Mail", "sent"))
		self.assertEqual(m.parse_list_line('(\\HasNoChildren) "." INBOX.Trash')["role"], "trash")
		self.assertFalse(m.parse_list_line('(\\Noselect \\HasChildren) "/" "[Gmail]"')["selectable"])


if __name__ == "__main__":
	unittest.main()
