"""
The template library (PROJ-0011 C) — no bench, no renderer: every template builds a page in every size.

    python -m unittest qtt_platform.tests.test_templates -v
"""

import re
import unittest

from qtt_platform.design import archetypes, base, business_types, catalog, layouts

SIZES = {"square": 1080, "portrait": 1350, "story": 1920}


def build(t: dict, group: str, fmt: str, look: str | None = None, content: dict | None = None) -> str:
	p = base.palette(catalog.PALETTES[t["palette"]])
	f = base.fonts(*catalog.FONT_SETS[t["fonts"]])
	x = layouts.Ctx(palette=p, fonts=f, height=SIZES[fmt], look=look or t["look"], content=content or catalog.sample_for(t["layout"], group),
					photos=["photo0.webp", "photo1.webp", "photo2.webp", "photo3.webp", "photo4.webp"])
	body, css = archetypes.LAYOUTS[t["layout"]](x, t["variant"])
	return layouts.page(body, css, x, 1080, SIZES[fmt])


class Catalog(unittest.TestCase):
	def test_every_template_is_complete(self):
		ts = catalog.templates()
		self.assertGreaterEqual(len(ts), 60)
		self.assertEqual(len({t["key"] for t in ts}), len(ts))  # unique keys
		for t in ts:
			self.assertIn(t["layout"], archetypes.LAYOUTS, t["key"])
			self.assertIn(t["palette"], catalog.PALETTES, t["key"])
			self.assertIn(t["fonts"], catalog.FONT_SETS, t["key"])
			self.assertTrue(set(t["post_types"]) <= set(catalog.POST_TYPES), t["key"])
			groups = {g for g, _ in business_types.GROUPS} | {"any"}
			self.assertTrue(set(t["groups"]) <= groups, t["key"])
		self.assertEqual(set(catalog.LAYOUTS), set(archetypes.LAYOUTS))  # every layout is in the library

	def test_every_template_builds_in_every_size(self):
		for t in catalog.templates():
			for g in list(catalog.SAMPLES.get(t["layout"], {})):
				for fmt in SIZES:
					page = build(t, g, fmt)
					self.assertIn("window.qttReady=true", page, (t["key"], g, fmt))
					self.assertIn(f"height:{SIZES[fmt]}px", page)
					self.assertNotIn("None", re.sub(r"<script.*?</script>", "", page, flags=re.S), (t["key"], g, fmt))

	def test_words_are_escaped_and_marked(self):
		t = next(t for t in catalog.templates() if t["layout"] == "quote_tip")
		page = build(t, "any", "square", content={"business": "<b>X</b>", "headline": "Fresh *every* day <script>"})
		self.assertIn("&lt;b&gt;X&lt;/b&gt;", page)
		self.assertIn("<em>every</em>", page)
		self.assertNotIn("<script>\"", page)
		self.assertNotIn("day <script>", page)

	def test_empty_content_still_builds(self):
		for t in catalog.templates():
			build(t, "any", "square", content={"business": "Anna Bakery"})

	def test_filters(self):
		ts = catalog.templates()
		tech = [t for t in ts if catalog.matches(t, group="technology")]
		self.assertTrue(any(t["layout"] == "hero_split" for t in tech))
		self.assertFalse(any(t["layout"] == "product_promo" for t in tech))
		self.assertTrue(all(catalog.matches(t, business_type="software") == catalog.matches(t, group="technology") for t in ts))
		offers = [t for t in ts if catalog.matches(t, post_type="offer", group="food")]
		self.assertTrue(offers and all("offer" in t["post_types"] for t in offers))
		self.assertTrue(any(t["layout"] == "greeting" for t in ts if catalog.matches(t, group="industry")))  # "any" fits all

	def test_cutouts_lose_their_frame(self):
		for t in catalog.templates():
			if t["layout"] not in ("center_hero", "product_promo", "numbered_services", "curve_photo", "wave_agency"):
				continue
			page = build(t, "any", "square", content={**catalog.sample_for(t["layout"], "any"), "cutout": True})
			self.assertIn("background-size:contain", page, t["key"])
			self.assertIn("drop-shadow", page, t["key"])
		framed = build(next(t for t in catalog.templates() if t["layout"] == "center_hero"), "any", "square")
		self.assertNotIn("background-size:contain", framed)

	def test_hash_is_stable(self):
		self.assertEqual(catalog.catalog_hash(), catalog.catalog_hash())


if __name__ == "__main__":
	unittest.main()
