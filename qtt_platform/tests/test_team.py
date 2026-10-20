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


class TestFormatting(unittest.TestCase):
	def test_whatsapp_marks(self):
		out = rules.text_to_html("*Stock* came _today_, ~not~ `SKU-12`")
		self.assertIn("<strong>Stock</strong>", out)
		self.assertIn("<em>today</em>", out)
		self.assertIn("<s>not</s>", out)
		self.assertIn("<code>SKU-12</code>", out)
		self.assertEqual(rules.html_to_text(out), "*Stock* came _today_, ~not~ `SKU-12`")

	def test_marks_leave_words_and_links_alone(self):
		out = rules.text_to_html("my_file_name and 2*3*4 and https://x.in/a_b_c")
		self.assertNotIn("<em>", out)
		self.assertNotIn("<strong>", out)
		self.assertIn('href="https://x.in/a_b_c"', out)

	def test_plain_drops_marks(self):
		self.assertEqual(rules.plain("*Hi* _there_ ~x~ `y`"), "Hi there x y")
		self.assertEqual(rules.preview("Text", "<p><strong>Big</strong> news</p>"), "Big news")


class TestMentions(unittest.TestCase):
	people = {"ravi@x.com": "Ravi", "rk@x.com": "Ravi Kumar", "m@x.com": "Meena"}

	def test_longest_name_wins(self):
		self.assertEqual(rules.mentions_in("thanks @Ravi Kumar", self.people), {"rk@x.com": "Ravi Kumar"})
		self.assertEqual(set(rules.mentions_in("@Ravi and @Meena", self.people)), {"ravi@x.com", "m@x.com"})
		self.assertEqual(rules.mentions_in("email ravi@Meena.com", self.people), {})

	def test_mentions_become_raven_spans(self):
		out = rules.text_to_html("hi @Meena", {"m@x.com": "Meena"})
		self.assertIn('data-type="userMention" data-id="m@x.com"', out)
		self.assertEqual(rules.html_to_text(out), "hi @Meena")

	def test_everyone(self):
		self.assertTrue(rules.mentions_everyone("@everyone meeting at 4"))
		self.assertFalse(rules.mentions_everyone("hi everyone"))


class TestVoiceAndReactions(unittest.TestCase):
	def test_voice_notes(self):
		self.assertEqual(rules.voice("/private/files/voice-12s-1700000000.wav"), 12)
		self.assertIsNone(rules.voice("/private/files/voice-12s.pdf"))
		self.assertIsNone(rules.voice("/private/files/notes.wav"))
		self.assertEqual(rules.preview("File", None, "/private/files/voice-3s-1.wav"), "🎤 Voice note")

	def test_reactions(self):
		raw = '{"👍": {"count": 2, "users": ["a", "b"], "reaction": "👍", "is_custom": 0}, "x": {"users": [], "reaction": "🎉"}}'
		out = rules.reactions(raw, "a", {"a": "Anna", "b": "Ben"})
		self.assertEqual(out, [{"emoji": "👍", "count": 2, "mine": True, "people": ["Anna", "Ben"]}])
		self.assertEqual(rules.reactions("not json", "a", {}), [])
		self.assertEqual(rules.escaped("👍"), "\\U0001f44d")


class TestTime(unittest.TestCase):
	def test_presence(self):
		self.assertEqual(rules.presence(1000, 1060), "online")
		self.assertEqual(rules.presence(1000, 1000 + 600), "away")
		self.assertEqual(rules.presence(1000, 1000 + 3600), "offline")
		self.assertEqual(rules.presence(None, 1000), "offline")

	def test_until_and_remind(self):
		from datetime import datetime

		now = datetime(2026, 10, 20, 21, 30)  # a Tuesday evening
		self.assertEqual(rules.until_from("1h", now), datetime(2026, 10, 20, 22, 30))
		self.assertEqual(rules.until_from("today", now), datetime(2026, 10, 20, 23, 59))
		self.assertIsNone(rules.until_from(None, now))
		self.assertEqual(rules.remind_at("tomorrow", now), datetime(2026, 10, 21, 9, 0))
		self.assertEqual(rules.remind_at("tonight", now), datetime(2026, 10, 20, 22, 30))  # 19:00 is past
		self.assertEqual(rules.remind_at("next_week", now), datetime(2026, 10, 26, 9, 0))  # Monday
		self.assertTrue(rules.status_live(None, now))
		self.assertFalse(rules.status_live(datetime(2026, 10, 20, 8, 0), now))


class TestSearchAndAi(unittest.TestCase):
	def test_search_words(self):
		self.assertEqual(rules.search_words("  stock  % a  delivery_"), ["stock", "delivery"])
		self.assertEqual(len(rules.search_words("a1 b2 c3 d4 e5 f6 g7")), 6)

	def test_snippet(self):
		text = "x " * 200 + "the delivery is late"
		s = rules.snippet(text, ["delivery"])
		self.assertIn("delivery", s)
		self.assertTrue(s.startswith("…"))

	def test_catch_up_parse(self):
		got = rules.parse_catch_up('```json\n{"summary": ["Stock came"], "decisions": [], "asks": ["Ravi asks for the bill"], "todos": []}\n```')
		self.assertEqual(got["summary"], ["Stock came"])
		self.assertEqual(got["asks"], ["Ravi asks for the bill"])
		self.assertIsNone(rules.parse_catch_up('{"summary": [], "decisions": []}'))
		self.assertIsNone(rules.parse_catch_up("sorry"))

	def test_task_parse_only_people_of_the_business(self):
		people = {"m@x.com": "Meena"}
		self.assertEqual(rules.parse_task('{"title": "Send the bill", "assignee": "meena", "due": "2026-10-23"}', people),
						 {"title": "Send the bill", "assign_to": "m@x.com", "due": "2026-10-23"})
		self.assertEqual(rules.parse_task('{"title": "Call", "assignee": "Someone Else", "due": "Friday"}', people),
						 {"title": "Call", "assign_to": None, "due": None})
		self.assertIsNone(rules.parse_task('{"title": ""}', people))

	def test_prompts_keep_to_the_messages(self):
		p = rules.catch_up_prompt("#sales", ["Ravi: hi"], "ta")
		self.assertIn("never add facts", p[0]["content"])
		self.assertIn("Tamil", p[0]["content"])


if __name__ == "__main__":
	unittest.main()
