"""
QTT Studio (PROJ-0012 S0) — the rules, no bench.

    python -m unittest qtt_platform.tests.test_studio -v
"""

import json
import unittest

from qtt_platform.studio import rules


class Plans(unittest.TestCase):
	def test_three_plans_bigger_each_time(self):
		self.assertEqual([p[0] for p in rules.PLANS], ["STARTER", "GROWTH", "PRO"])
		prices = [p[2] for p in rules.PLANS]
		self.assertEqual(prices, sorted(prices))
		for _, _, _, f in rules.PLANS:
			self.assertIn("ai_credits_grant", f)  # granted every month by the platform's existing credit system
		self.assertEqual(rules.PLANS[0][3]["studio_design_mode"], 0)

	def test_what_is_ready(self):
		ready = [c[0] for c in rules.CATEGORIES if c[3]]
		self.assertEqual(ready, ["posts", "documents", "logos", "print", "photos"])  # S0, S3, S5, S4, S1
		self.assertEqual(rules.CREDITS["ai_background"], 10)

	def test_post_caption_is_the_design_words(self):
		w = {"kicker": "Pongal special", "headline": "Sweet *pongal* for all", "subline": "Fresh  every morning.", "cta": "Call now",
			 "items": [{"title": "Sakkarai pongal", "text": "jaggery"}, {"title": "Ven pongal"}]}
		self.assertEqual(rules.post_caption(w), "Pongal special — Sweet pongal for all\n\nFresh every morning.\n\n"
												"• Sakkarai pongal: jaggery\n• Ven pongal\n\nCall now")
		self.assertEqual(rules.post_caption({"headline": "Just *this*"}), "Just this")
		self.assertEqual(rules.post_caption({}), "")

	def test_limits(self):
		self.assertEqual(rules.limit_left(30, 12), 18)
		self.assertEqual(rules.limit_left(30, 40), 0)
		self.assertIsNone(rules.limit_left(0, 999))  # 0 = unlimited
		self.assertEqual(rules.limit_left("bad", 1), 0)


class Ai(unittest.TestCase):
	def test_make_prompt_forbids_inventing(self):
		m = rules.make_prompt(request="a Pongal post", brief="Business: Anna Mess", language="ta",
							  templates=[{"key": "greeting-festive-red", "label": "Festival wishes · Festive red", "post_types": ["greeting"]}],
							  ideas=[{"key": "wish-pongal", "headline": "இனிய பொங்கல் நல்வாழ்த்துகள்"}])
		self.assertIn("never invent prices", m[0]["content"])
		self.assertIn("Write in Tamil", m[0]["content"])
		self.assertIn("greeting-festive-red", m[1]["content"])

	def test_parse_make_keeps_only_known_designs_and_slots(self):
		keys = {"greeting-festive-red"}
		good = json.dumps({"template": "greeting-festive-red", "look": "brand",
						   "words": {"headline": "Happy *Pongal*", "kicker": "Wishing you a", "hack": "<script>", "subline": "x" * 500}})
		r = rules.parse_make("Sure! " + good, keys)
		self.assertEqual(r["template"], "greeting-festive-red")
		self.assertEqual(r["look"], "brand")
		self.assertNotIn("hack", r["words"])
		self.assertEqual(len(r["words"]["subline"]), rules.SLOTS["subline"])
		self.assertIsNone(rules.parse_make(json.dumps({"template": "made-up", "words": {"headline": "x"}}), keys))
		self.assertIsNone(rules.parse_make(json.dumps({"template": "greeting-festive-red", "words": {}}), keys))
		self.assertIsNone(rules.parse_make("no json", keys))

	def test_parse_ask_only_valid_changes(self):
		self.assertEqual(rules.parse_ask('{"look": "dark", "format": "huge", "words": {"headline": "Shorter"}}'),
						 {"look": "dark", "words": {"headline": "Shorter"}})
		self.assertEqual(rules.parse_ask('{"look": "neon"}'), {})

	def test_items_are_tidy(self):
		w = rules.clean_words({"headline": "H", "items": [{"title": "Meals", "text": "₹120"}, {"title": ""}, "x"] * 3})
		self.assertEqual(len(w["items"]), 2)
		self.assertEqual(w["items"][0], {"icon": "icon_check", "title": "Meals", "text": "₹120"})


if __name__ == "__main__":
	unittest.main()
