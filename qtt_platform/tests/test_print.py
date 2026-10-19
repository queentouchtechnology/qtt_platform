"""
QTT Studio › Print (PROJ-0012 S4) — visiting cards, flyers and menus; filled from the business, never inventing prices;
print-ready with bleed and crop marks. No bench. (Every product and style was drawn in Chrome while building, and a
card's print-shop PDF checked: two pages, colour into the bleed, crop marks outside it.)

    python -m unittest qtt_platform.tests.test_print -v
"""

import re
import unittest

from qtt_platform.design import base, print as pr

PAL = base.palette({"primary": "#b45309"})
FONTS = base.fonts("Poppins", "Inter", "")
KNOW = {"about": "Fresh meals cooked every morning. Family recipes.", "hours": "Mon–Sat 11–10", "business_type": "restaurant",
		"offerings": [{"item": "Veg meals", "price": "₹120", "kind": "Meals"}, {"item": "Coffee", "price": "", "kind": "Drinks"},
					  {"item": "Old dish", "price": "₹1", "active": 0}]}
CONTACTS = {"phone": "+91 98765 43210", "email": "a@b.in", "website": "annapoorna.in", "address": "Madurai"}


class Fill(unittest.TestCase):
	def test_card_from_the_business(self):
		w = pr.fields_for("card", name="Annapoorna Mess", contacts=CONTACTS, knowledge=KNOW, person="R. Kumar")
		self.assertEqual((w["person"], w["phone"], w["website"]), ("R. Kumar", "+91 98765 43210", "annapoorna.in"))

	def test_menu_only_its_own_prices(self):
		w = pr.fields_for("menu", name="Annapoorna Mess", contacts=CONTACTS, knowledge=KNOW)
		self.assertEqual(w["headline"], "Menu")
		self.assertEqual([(i["name"], i["price"]) for i in w["items"]], [("Veg meals", "₹120"), ("Coffee", "")])  # no price made up; inactive left out

	def test_flyer_points_from_offerings(self):
		w = pr.fields_for("flyer_a5", name="X", contacts={}, knowledge=KNOW)
		self.assertEqual(w["points"], "Veg meals\nCoffee")
		self.assertEqual(w["offer"], "")  # an offer only when the owner types one

	def test_clean(self):
		w = pr.clean("menu", {"headline": "  Menu  ", "evil": "x", "items": [{"name": "A", "price": "₹1" * 50}, {"name": ""}, "bad"]})
		self.assertEqual(w["headline"], "Menu")
		self.assertNotIn("evil", w)
		self.assertEqual(len(w["items"]), 1)
		self.assertEqual(len(w["items"][0]["price"]), 20)
		self.assertEqual(pr.clean("flyer_a4", {"points": "a\n\n b \n"})["points"], "a\nb")


class Pages(unittest.TestCase):
	def test_every_product_and_style(self):
		for product, (_l, tw, th, sides, styles) in pr.PRODUCTS.items():
			w = pr.fields_for(product, name="Annapoorna", contacts=CONTACTS, knowledge=KNOW)
			for s in styles:
				html = pr.page(product, s, w, PAL, FONTS, logo="logo.png")
				self.assertEqual(html.count('class="pg"'), len(sides), (product, s))
				self.assertIn(f"size:{tw + 2 * pr.BLEED}mm {th + 2 * pr.BLEED}mm", html)

	def test_print_ready_has_marks_and_bleed(self):
		w = pr.fields_for("card", name="A", contacts=CONTACTS, knowledge=KNOW)
		html = pr.page("card", "band", w, PAL, FONTS, marks=True)
		self.assertEqual(html.count('class="mk"'), 2 * 8)  # 8 marks a side, 2 sides
		self.assertIn(f"size:{89 + 2 * (pr.BLEED + pr.SLUG)}mm", html)
		self.assertNotIn('class="mk"', pr.page("card", "band", w, PAL, FONTS))

	def test_words_are_escaped_and_starred(self):
		w = pr.clean("flyer_a5", {"headline": "Fresh *meals* <script>x</script>"})
		html = pr.page("flyer_a5", "block", w, PAL, FONTS)
		self.assertIn("<em>meals</em>", html)
		self.assertNotIn("<script>x", html)

	def test_qr_for_the_website(self):
		w = pr.fields_for("card", name="A", contacts=CONTACTS, knowledge=KNOW)
		self.assertIn('class="qr"', pr.page("card", "minimal", w, PAL, FONTS))

	def test_preview_size(self):
		self.assertEqual(pr.size_px("flyer_a4"), (794, 1123))
		self.assertTrue(re.match(r"\d+ × \d+", f"{pr.PRODUCTS['card'][1]} × {pr.PRODUCTS['card'][2]}"))


if __name__ == "__main__":
	unittest.main()
