"""
The design base (PROJ-0011 B) — no bench.

    python -m unittest qtt_platform.tests.test_design -v
"""

import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from qtt_platform.design import base, business_types, elements, patterns, photos, sheet


class Palette(unittest.TestCase):
	def test_owner_colours_are_never_changed(self):
		p = base.palette({"primary": "#B45309", "accent": "#0EA5E9"})
		self.assertEqual((p["primary"], p["accent"]), ("#b45309", "#0ea5e9"))
		self.assertEqual(p["owner"], ["accent", "primary"])
		for k in ("secondary", "dark", "light"):
			self.assertRegex(p[k], r"^#[0-9a-f]{6}$")

	def test_text_is_always_readable(self):
		for primary in ("#facc15", "#1d4ed8", "#16a34a", "#f472b6", "#111827", "#ffffff"):
			p = base.palette({"primary": primary})
			for k in ("primary", "secondary", "accent", "dark", "light"):
				self.assertGreaterEqual(base.contrast(p[k], p[f"on_{k}"]), 3.0, (primary, k))
		self.assertGreater(base.contrast(base.palette({})["light"], base.palette({})["dark"]), 7)

	def test_no_colours_still_designs(self):
		self.assertEqual(base.palette(None)["primary"], base.DEFAULT_PRIMARY)
		self.assertEqual(base.palette({"primary": "blue"})["primary"], base.DEFAULT_PRIMARY)


class Fonts(unittest.TestCase):
	def test_brand_fonts_and_scripts(self):
		f = base.fonts("playfair display", "", "Tamil")
		self.assertEqual((f["heading"], f["body"]), ("Playfair Display", "Playfair Display"))
		self.assertIn("Noto Sans Tamil", f["css_body"])
		self.assertIn("family=Noto+Sans+Tamil", " ".join(f["urls"]))
		self.assertTrue(all("600" not in u for u in base.fonts("Playfair Display", "Lato")["urls"]))  # Lato has no 600 / 800
		self.assertIn("Great+Vibes", " ".join(base.fonts(extra=("great vibes",))["urls"]))
		self.assertEqual(base.fonts("Comic Sans", "Wingdings")["heading"], base.PAIRS[0][0])  # unknown → the default pair
		self.assertTrue(base.fonts(language="Arabic")["rtl"])
		self.assertEqual(base.script_of("வணக்கம்"), "tamil")
		self.assertEqual(base.script_of("नमस्ते"), "devanagari")
		self.assertIsNone(base.script_of("Hello"))


def _svg_ok(test, svg: str):
	ET.fromstring(svg)  # well-formed
	test.assertIsNone(re.search(r"\bnan\b|\binf\b", svg.lower()))


class Patterns(unittest.TestCase):
	def test_every_pattern_every_base_every_format(self):
		p = base.palette({"primary": "#7c3aed"})
		for name in patterns.PATTERNS:
			for b in patterns.BASES:
				for w, h, *_ in base.FORMATS.values():
					svg = patterns.pattern(name, p, w, h, base=b, seed=3)
					_svg_ok(self, svg)
					self.assertIn(f'width="{w}" height="{h}"', svg)

	def test_only_the_palette_is_used(self):
		p = base.palette({"primary": "#7c3aed", "accent": "#f59e0b"})
		allowed = {p["primary"], p["accent"], p["light"], p["dark"], "#ffffff"}
		for name in patterns.PATTERNS:
			for b in patterns.BASES:
				used = set(re.findall(r'(?:fill|stroke)="(#[0-9a-f]{6})"', patterns.pattern(name, p, 600, 600, base=b)))
				self.assertLessEqual(used, allowed, (name, b))

	def test_same_seed_same_picture(self):
		p = base.palette({})
		self.assertEqual(patterns.pattern("confetti", p, 500, 500, seed=7), patterns.pattern("confetti", p, 500, 500, seed=7))
		self.assertNotEqual(patterns.pattern("confetti", p, 500, 500, seed=7), patterns.pattern("confetti", p, 500, 500, seed=8))


class Elements(unittest.TestCase):
	def test_every_element_and_text_is_escaped(self):
		p = base.palette({})
		for name in elements.ELEMENTS:
			_svg_ok(self, elements.element(name, p, 240, 120, text="<b>₹120 & more</b>"))
		self.assertIn("&lt;b&gt;", elements.element("badge", p, 200, 200, text="<b>"))

	def test_no_other_brands(self):
		self.assertFalse([n for n in elements.ELEMENTS if re.search(r"whatsapp|instagram|facebook|upi|paytm|gpay", n)])


class LocalMarket(unittest.TestCase):
	def test_brush_date_qr_labels(self):
		p = base.palette({"primary": "#1e3a8a", "accent": "#facc15"})
		_svg_ok(self, elements.element("brush_badge", p, 300, 120, text="₹35 லட்சம்"))
		self.assertIn(">18<", elements.element("date_block", p, 160, 180, text="18 Oct"))
		self.assertIn(">OCT<", elements.element("date_block", p, 160, 180, text="18 Oct"))
		qr = elements.element("qr", p, 200, 200, text="https://maps.google.com/?q=Tuticorin")
		_svg_ok(self, qr)
		self.assertGreater(qr.count("<rect"), 100)  # a real code, made here
		self.assertIn(">Reading<", elements.element("label_circle", p, 200, 240, text="icon_book|Reading"))
		self.assertEqual(elements.element("brush_swipe", p, 300, 100, text="New Home"), elements.element("brush_swipe", p, 300, 100, text="New Home"))

	def test_text_styles_and_frames(self):
		p = base.palette({"primary": "#b91c1c"})
		self.assertIn("background-clip:text", base.text_style("gold", p))
		self.assertIn(p["primary_deep"], base.text_style("3d", p))
		self.assertEqual(base.text_style("sparkly", p), "")
		self.assertIn("grayscale", base.FRAMES["mono"])

	def test_religious_type(self):
		self.assertEqual(business_types.group_of("religious"), "other")


class TypesAndPhotos(unittest.TestCase):
	def test_technology_has_its_own_room(self):
		tech = [t for t in business_types.listing() if t["group"] == "technology"]
		self.assertGreaterEqual(len(tech), 4)
		self.assertIn("software", [t["key"] for t in tech])
		self.assertEqual(business_types.photo_kit("software"), "it")
		self.assertEqual(business_types.valid("bakery"), "")

	def test_photo_library(self):
		with tempfile.TemporaryDirectory() as d:
			for kit, files in {"restaurant": ["hero-1.webp", "about.webp", "cat-snacks.webp"], "other": ["hero-1.webp"]}.items():
				(Path(d) / kit).mkdir()
				for f in files:
					(Path(d) / kit / f).write_bytes(b"x")
			lib = photos.library(Path(d))
			self.assertEqual(photos.pick(lib, "restaurant", seed=0)["file"], "about.webp")  # wide scenes, sorted
			self.assertEqual(photos.pick(lib, "restaurant", role="category")["file"], "cat-snacks.webp")
			self.assertIsNone(photos.pick(lib, "software")["kit"])  # no kit → another's photo
			self.assertIn("rgba(", photos.scrim(base.palette({})))


class Sheet(unittest.TestCase):
	def test_brand_sheet(self):
		html_, w, h = sheet.brand_sheet(business="Anna <Bakery>", colors={"primary": "#b45309"}, logo_file="logo.png",
										 font_heading="Lora", language="Tamil")
		self.assertEqual(w, sheet.SHEET_W)
		self.assertGreater(h, 2000)
		self.assertIn('src="logo.png"', html_)
		self.assertIn("Anna &lt;Bakery&gt;", html_)
		self.assertIn("Noto+Sans+Tamil", html_)
		self.assertEqual(html_.count("<svg"), len(patterns.PATTERNS) + 10)


if __name__ == "__main__":
	unittest.main()
