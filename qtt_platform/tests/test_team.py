"""
Team chat (free core of QTT OS, PROJ-0013) — the rules, no bench.

    python -m unittest qtt_platform.tests.test_team -v
"""

import unittest

from qtt_platform import team_rules as rules


class TestNames(unittest.TestCase):
	def test_workspace_per_business(self):
		self.assertEqual(rules.workspace_name("acme"), "qtt-acme")
		self.assertTrue(rules.is_business_workspace("qtt-acme"))
		self.assertFalse(rules.is_business_workspace("Queen Touch Technology"))
		self.assertFalse(rules.is_business_workspace(None))

	def test_channel_names_as_raven_keeps_them(self):
		self.assertEqual(rules.clean_channel_name("  Sales Team  "), "sales-team")
		self.assertEqual(rules.clean_channel_name("Orders!! & Billing"), "orders-billing")
		self.assertEqual(rules.clean_channel_name("விற்பனை குழு"), "விற்பனை-குழு")
		self.assertEqual(len(rules.clean_channel_name("x" * 80)), 50)
		self.assertEqual(rules.channel_id("qtt-acme", "General"), "qtt-acme-general")

	def test_direct_messages(self):
		name = rules.dm_name("a@x.com", "b@x.com")
		self.assertEqual(name, "a@x.com _ b@x.com")
		self.assertEqual(rules.dm_peer(name, "a@x.com"), "b@x.com")
		self.assertEqual(rules.dm_peer(name, "b@x.com"), "a@x.com")
		self.assertIsNone(rules.dm_peer("a@x.com _ a@x.com", "a@x.com"))  # note to self
		self.assertIsNone(rules.dm_peer("general", "a@x.com"))


class TestText(unittest.TestCase):
	def test_plain_text_to_html_is_escaped(self):
		out = rules.text_to_html("Hi <b>team</b>\nline two\n\nsee https://example.com/a?b=1")
		self.assertNotIn("<b>", out)
		self.assertIn("&lt;b&gt;", out)
		self.assertIn("<br>", out)
		self.assertEqual(out.count("<p>"), 2)
		self.assertIn('<a href="https://example.com/a?b=1"', out)

	def test_html_back_to_text(self):
		self.assertEqual(rules.html_to_text("<p>One<br>two</p><p>three &amp; four</p>"), "One\ntwo\n\nthree & four")
		self.assertEqual(rules.html_to_text("<ul><li>a</li><li>b</li></ul>"), "• a\n• b")
		self.assertEqual(rules.html_to_text(rules.text_to_html("a < b\nc")), "a < b\nc")

	def test_preview(self):
		self.assertEqual(rules.preview("Image", None), "📷 Photo")
		self.assertEqual(rules.preview("File", None, "/private/files/price list.pdf"), "📎 price list.pdf")
		self.assertEqual(rules.preview("Text", "<p>Hello   there</p>"), "Hello there")
		long = rules.preview("Text", "x" * 300)
		self.assertTrue(long.endswith("…"))
		self.assertEqual(len(long), 141)

	def test_kind_of_file(self):
		self.assertEqual(rules.kind_of("photo.JPG"), "Image")
		self.assertEqual(rules.kind_of("bill.pdf"), "File")


class TestWhoSees(unittest.TestCase):
	def test_open_and_private_channels(self):
		self.assertTrue(rules.can_see({"type": "Public"}, False))
		self.assertTrue(rules.can_see({"type": "Open"}, False))
		self.assertFalse(rules.can_see({"type": "Private"}, False))
		self.assertTrue(rules.can_see({"type": "Private"}, True))

	def test_archived_and_threads_hidden(self):
		self.assertFalse(rules.can_see({"type": "Public", "is_archived": 1}, True))
		self.assertFalse(rules.can_see({"type": "Public", "is_thread": 1}, True))


if __name__ == "__main__":
	unittest.main()
