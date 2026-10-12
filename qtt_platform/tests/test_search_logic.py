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

	def test_typo_only_when_allowed(self):
		f = ["Ram Kumar", "Chennai"]
		self.assertFalse(s.matches(f, "kumr"))
		self.assertTrue(s.matches(f, "kumr", typos=True))
		self.assertTrue(s.matches(f, "chenai ram", typos=True))
		self.assertFalse(s.matches(f, "ram", typos=True) is False)
		self.assertFalse(s.matches(f, "kmr", typos=True))  # too short to guess
		self.assertTrue(s.matches(["John Doe"], "jhon", typos=True))  # swapped letters
		self.assertTrue(s.matches(["Ranjith"], "rnjith", typos=True))  # missing letter
		self.assertEqual(s.fuzzy_fragments("rnjith"), ["rnj", "jit", "ith"])

	def test_sql_term_and_fuzzy_term(self):
		self.assertEqual(s.sql_term("bala  chennai stores"), "chennai")
		self.assertEqual(s.fuzzy_term("kumr"), "kum")
		self.assertEqual(s.fuzzy_term("ab"), "")
		self.assertTrue(s.needs_refine("bala chennai"))
		self.assertFalse(s.needs_refine("bala"))

	def test_refine_keeps_all_words_best_first(self):
		rows = [{"t": "Kavya Rice Mill", "c": "Madurai"}, {"t": "Rice Traders", "c": "Chennai"}, {"t": "Bala Rice", "c": "Chennai"}]
		out = s.refine(rows, "chennai rice", lambda r: [r["t"], r["c"]], lambda r: r["t"])
		self.assertEqual([r["t"] for r in out], ["Rice Traders", "Bala Rice"])

	def test_completions_finish_the_last_word(self):
		titles = ["Hrms Deployment", "AWS Deployment", "Docker Deployment", "Hrms Software", "Delivery Charges"]
		self.assertEqual(s.completions(titles, "dep"), ["deployment"])
		self.assertEqual(s.completions(titles, "hrms d")[0], "hrms deployment")  # from the Hrms records first
		self.assertEqual(s.completions(["Rice Bags", "Rice Bran", "Rice Bran Oil"], "rice br"), ["rice bran"])
		self.assertEqual(s.completions(titles, ""), [])

	def test_did_you_mean(self):
		titles = ["Ranjith", "Ranjith 2", "John Doe"]
		self.assertEqual(s.did_you_mean(titles, "rnjith"), "ranjith")
		self.assertEqual(s.did_you_mean(titles, "jhon doe"), "john doe")
		self.assertIsNone(s.did_you_mean(titles, "ranjith"))  # already right
		self.assertIsNone(s.did_you_mean(titles, "ran"))  # a prefix is fine
		self.assertIsNone(s.did_you_mean(titles, "98400"))  # numbers aren't corrected


if __name__ == "__main__":
	unittest.main()
