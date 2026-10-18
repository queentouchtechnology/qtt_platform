"""
The content library (PROJ-0011 C2) — no bench.

    python -m unittest qtt_platform.tests.test_content -v
"""

import unittest

from qtt_platform.design import catalog, content

K = {"about": "South Indian meals and tiffin in Srirangam.", "hours": "6 am to 10 pm, every day", "delivery": "Free in Srirangam",
	 "offerings": [{"item": "Meals", "price": "₹120", "details": "Rice, sambar, rasam", "active": 1},
				   {"item": "Mini tiffin", "price": "₹90", "active": 1}, {"item": "Filter coffee", "active": 1}, {"item": "Old", "active": 0}]}
C = {"phone": "98400 12345", "address": ""}


class Library(unittest.TestCase):
	def test_every_idea_is_complete_in_both_languages(self):
		self.assertGreaterEqual(len(content.IDEAS), 45)
		for key, idea in content.IDEAS.items():
			self.assertIn(idea["post_type"], catalog.POST_TYPES, key)
			for lang in content.LANGUAGES:
				self.assertIn("headline", idea[lang], (key, lang))
				self.assertEqual(set(idea[lang]) - {"items"}, set(idea["en"]) - {"items"}, (key, lang))  # same slots
			for n in idea["needs"]:
				self.assertIn(n, ("hours", "product", "products3", "different", "delivery", "payments", "phone", "address", "audience",
								  "bookings", "about"), key)

	def test_every_occasion_has_a_wish_and_a_date_rule(self):
		for k, (en, ta, d) in content.OCCASIONS.items():
			self.assertIn(f"wish-{k}", content.IDEAS)
			self.assertTrue(d is None or len(d) == 5, k)  # moving festivals: dates come from Desk, never guessed

	def test_every_post_type_with_ideas_has_designs(self):
		types = {i["post_type"] for i in content.IDEAS.values()}
		designed = {p for t in catalog.templates() for p in t["post_types"]}
		self.assertLessEqual(types, designed)


class Filling(unittest.TestCase):
	def setUp(self):
		self.f = content.facts(K, C, "Annapoorna Mess")

	def test_facts_only_from_the_business(self):
		self.assertEqual(self.f["product"], "Meals")
		self.assertEqual(self.f["price"], "₹120")
		self.assertNotIn("address", self.f)  # empty in the profile → absent
		self.assertEqual(len(self.f["products3"]), 3)  # the switched-off one isn't offered

	def test_fill_and_never_invent(self):
		w = content.fill(content.IDEAS["product-highlight"], self.f)
		self.assertEqual((w["headline"], w["badge"], w["subline"]), ("*Meals*", "₹120", "Rice, sambar, rasam"))
		self.assertIsNone(content.fill(content.IDEAS["find-us"], self.f))  # needs the address
		self.assertIsNone(content.fill(content.IDEAS["why-us"], self.f))  # needs what makes them different
		self.assertEqual(content.missing(content.IDEAS["why-us"], self.f), ["different"])
		no_price = content.facts({"offerings": [{"item": "Dosa", "active": 1}]}, {}, "X")
		self.assertNotIn("badge", content.fill(content.IDEAS["product-highlight"], no_price))  # no price → no badge, not a gap

	def test_tamil_and_lists(self):
		w = content.fill(content.IDEAS["what-we-offer"], self.f, "ta")
		self.assertIn("வழங்குவது", w["headline"])
		self.assertEqual([i["title"] for i in w["items"]], ["Meals", "Mini tiffin", "Filter coffee"])
		self.assertEqual(w["items"][0]["text"], "₹120 · Rice, sambar, rasam")
		self.assertIn("98400 12345", w["cta"])
		self.assertEqual(content.language_of("Tamil"), "ta")
		self.assertEqual(content.language_of(""), "en")

	def test_wishes_and_topics(self):
		w = content.fill(content.IDEAS["wish-pongal"], self.f, "ta")
		self.assertEqual(w["tagline"], "— Annapoorna Mess")
		self.assertTrue(content.suits(content.IDEAS["wish-pongal"], post_types=["greeting"], group="food", occasion="pongal"))
		self.assertFalse(content.suits(content.IDEAS["tip-backup"], group="food"))
		topics = content.article_topics("food", self.f)
		self.assertIn("How to choose the right Meals for you", topics)
		self.assertFalse(any("{" in t for t in topics))


if __name__ == "__main__":
	unittest.main()
