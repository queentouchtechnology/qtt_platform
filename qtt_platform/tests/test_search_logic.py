"""
Bench-independent tests for global search rules (qtt_platform.search_logic — pure).

	python -m unittest qtt_platform.tests.test_search_logic -v
"""

import unittest

from qtt_platform import search_logic as s


class SearchLogicTest(unittest.TestCase):
	def test_terms(self):
		self.assertEqual(s.terms("  Bala   Chennai "), ["bala", "chennai"])
		self.assertEqual(s.terms(""), [])

	def test_every_word_must_match_any_order(self):
		f = ["Bala Stores", "Wholesale", "Chennai"]
		self.assertTrue(s.matches(f, "chennai bala"))
		self.assertFalse(s.matches(f, "bala madurai"))

	def test_phone_by_digits(self):
		f = ["Ram", "+91 98400 12345"]
		self.assertTrue(s.matches(f, "9840012345"))
		self.assertTrue(s.matches(f, "98400-12345"))
		self.assertFalse(s.matches(f, "98400 99999"))
		self.assertEqual(s.digits("+91 98400"), "9198400")
		self.assertEqual(s.digits("ab 12"), "")

	def test_rank_exact_then_prefix_then_word_then_contains(self):
		rows = [{"title": t} for t in ("Kavya Rice Mill", "Rice", "Rice Bags", "Brown rice", "Price list")]
		self.assertEqual([r["title"] for r in s.rank(rows, "rice")], ["Rice", "Rice Bags", "Brown rice", "Kavya Rice Mill", "Price list"])


if __name__ == "__main__":
	unittest.main()
