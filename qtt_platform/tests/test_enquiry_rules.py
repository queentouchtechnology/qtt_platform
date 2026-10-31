import unittest

from qtt_platform import enquiry_rules as r

S = "secret-for-tests"


class Tickets(unittest.TestCase):
	def test_good_ticket(self):
		t = r.make_ticket(S, now=1000)
		self.assertIsNone(r.check_ticket(t, S, now=1010))

	def test_bad_tickets(self):
		t = r.make_ticket(S, now=1000)
		self.assertEqual(r.check_ticket("", S, now=1010), "missing")
		self.assertEqual(r.check_ticket("1000.abc", S, now=1010), "forged")
		self.assertEqual(r.check_ticket(t, "other", now=1010), "forged")
		self.assertEqual(r.check_ticket(t, S, now=1001), "too_fast")
		self.assertEqual(r.check_ticket(t, S, now=1000 + r.MAX_SECONDS + 1), "expired")
		ts, sig = t.split(".")
		self.assertEqual(r.check_ticket(f"{int(ts) - 50}.{sig}", S, now=1010), "forged")  # can't shift the time


class Spam(unittest.TestCase):
	def test_people_pass(self):
		self.assertIsNone(r.spam_reason("Ravi Kumar", "Need a website for my bakery. See www.ravibakes.in", "Ravi Bakes"))

	def test_spam(self):
		self.assertEqual(r.spam_reason("Bob", "buy http://a.co http://b.co http://c.co"), "links")
		self.assertEqual(r.spam_reason("Bob", '<a href="http://x">cheap</a>'), "markup")
		self.assertEqual(r.spam_reason("http://seo.biz", "hello"), "link_in_name")
		self.assertEqual(r.spam_reason("hello", "hello"), "same_text")
		self.assertEqual(r.spam_reason("Bot", "TPtefCTolpbmOBzQNCaxJ"), "random_letters")  # seen on queentouchtech.com, 28 Oct 2026
		self.assertEqual(r.spam_reason("xKqPzWmLrTvBnYc", "hi there"), "random_letters")

	def test_real_words_with_capitals_pass(self):
		for name, msg in (("Ravi McDonald", "WhatsApp"), ("Amr Kholif", "Seeking an Experienced Team for an AI Platform"),
						  ("Sri", "OpenAIIntegration"), ("Priya", "Supercalifragilistic")):
			self.assertIsNone(r.spam_reason(name, msg), (name, msg))


if __name__ == "__main__":
	unittest.main()
