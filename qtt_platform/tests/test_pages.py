"""
QTT Studio › Landing pages (PROJ-0012 S7) — filled from the business, checked, drawn safely; the address. No bench.
(A page was drawn at phone width while building: hero with WhatsApp button, offer card, points, gallery, contact.)

    python -m unittest qtt_platform.tests.test_pages -v
"""

import unittest

from qtt_platform.design import base, pages

PAL = base.palette({"primary": "#b45309"})
FONTS = base.fonts("Poppins", "Inter", "")
KNOW = {"about": "Fresh meals every morning.", "hours": "Mon–Sat 11–10", "map_link": "https://maps.google.com/?q=x",
		"offerings": [{"item": "Veg meals", "details": "Rice and sambar"}, {"item": "Old", "active": 0}],
		"faqs": [{"question": "Do you deliver?", "answer": "Yes, within 5 km."}, {"question": "No answer", "answer": ""}]}
CONTACTS = {"phone": "98765 43210", "whatsapp": "98765 43210", "email": "a@b.in", "address": "Madurai"}


def _html(p, **kw):
	return pages.html(pages.clean(p), name="Annapoorna Mess", pal=PAL, fonts=FONTS, contacts=CONTACTS, knowledge=KNOW, logo_url=None,
					  photos=kw.pop("photos", {}), **kw)


class Start(unittest.TestCase):
	def test_from_the_business_never_made_up(self):
		p = pages.start("offer", name="Annapoorna Mess", knowledge=KNOW, contacts=CONTACTS)
		self.assertEqual(p["sections"], ["hero", "offer", "points", "gallery", "contact"])
		self.assertEqual([x["title"] for x in p["points"]], ["Veg meals"])
		self.assertEqual(p["offer"]["price"], "")  # the owner types a real offer
		self.assertEqual([f["q"] for f in p["faq"]], ["Do you deliver?"])
		self.assertEqual(p["hero"]["cta"], "whatsapp")

	def test_every_kind(self):
		for kind in pages.KINDS:
			self.assertEqual(pages.clean(pages.start(kind, name="X", knowledge={}, contacts={}))["kind"], kind)


class Clean(unittest.TestCase):
	def test_only_known_and_safe(self):
		p = pages.clean({"kind": "evil", "sections": ["hero", "script", "hero", "faq"], "hero": {"cta": "steal", "link": "javascript:alert(1)"},
						 "points": [{"title": "a" * 100}, {"title": ""}, "bad"] * 3, "gallery": ["p1", 5, "p2"]})
		self.assertEqual(p["kind"], "general")
		self.assertEqual(p["sections"], ["hero", "faq"])
		self.assertEqual(p["hero"]["cta"], "whatsapp")
		self.assertEqual(p["hero"]["link"], "")
		self.assertEqual(len(p["points"]), 3)
		self.assertEqual(len(p["points"][0]["title"]), 70)
		self.assertEqual(p["gallery"], ["p1", "p2"])
		self.assertEqual(pages.clean({"hero": {"link": "annapoorna.in/menu"}})["hero"]["link"], "https://annapoorna.in/menu")

	def test_slug(self):
		self.assertEqual(pages.slugify("Annapoorna Mess · Pongal Offer!"), "annapoorna-mess-pongal-offer")
		self.assertEqual(pages.slugify("பொங்கல்"), "page")
		self.assertLessEqual(len(pages.slugify("x" * 200)), 50)


class Page(unittest.TestCase):
	def test_whatsapp_button_and_seo(self):
		p = pages.start("offer", name="Annapoorna Mess", knowledge=KNOW, contacts=CONTACTS)
		p["title"] = "Pongal offer"
		h = _html(p, url="https://app.queentouchtech.in/p/pongal")
		self.assertIn("https://wa.me/919876543210?text=", h)
		self.assertIn("<title>Pongal offer · Annapoorna Mess</title>", h)
		self.assertIn('rel="canonical" href="https://app.queentouchtech.in/p/pongal"', h)
		self.assertIn('name="viewport"', h)
		self.assertNotIn("noindex", h)
		self.assertIn("noindex", _html(p, noindex=True))

	def test_escaped(self):
		p = pages.start("general", name="X", knowledge={}, contacts=CONTACTS)
		p["hero"]["headline"] = "<script>alert(1)</script> *fresh*"
		h = _html(p)
		self.assertNotIn("<script>alert", h)
		self.assertIn("<em>fresh</em>", h)

	def test_empty_sections_left_out(self):
		p = pages.start("offer", name="X", knowledge={}, contacts={})
		h = _html(p)
		self.assertNotIn('class="offer"', h)  # no offer typed
		self.assertNotIn("<script", h)  # no scripts on the page

	def test_gallery_uses_own_photos_not_the_hero_twice(self):
		p = pages.start("general", name="X", knowledge={}, contacts={})
		h = _html(p, photos={"a": "https://x/a.jpg", "b": "https://x/b.jpg"})
		self.assertEqual(h.count("https://x/a.jpg"), 2)  # the hero (and its sharing picture), not the gallery
		self.assertIn('<img src="https://x/b.jpg"', h)


if __name__ == "__main__":
	unittest.main()
