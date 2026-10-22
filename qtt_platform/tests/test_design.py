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
		allowed = {v for k, v in p.items() if isinstance(v, str)}  # the palette's roles (its own colours and their tints)
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


class Cutouts(unittest.TestCase):
	def test_trim_to_the_subject(self):
		import io

		from PIL import Image

		im = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
		im.paste((200, 50, 50, 255), (150, 100, 200, 220))
		b = io.BytesIO()
		im.save(b, "PNG")
		self.assertEqual(Image.open(io.BytesIO(photos.trim(b.getvalue()))).size, (58, 128))  # 50 x 120 + a little room
		empty = io.BytesIO()
		Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(empty, "PNG")
		self.assertEqual(photos.trim(empty.getvalue()), empty.getvalue())


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


class PremiumUpgrade(unittest.TestCase):
	"""The premium finish, lit elements, roomy buttons, fit warnings and the new layouts (docs/design/studio-design-rules.md)."""

	def test_finish_layers(self):
		from qtt_platform.design import finish

		p = base.palette({"primary": "#2563eb"})
		self.assertEqual(finish.layers("clean", p, "dark", 1080, 1080), ("", ""))
		html_, css = finish.layers("premium", p, "light", 1080, 1080, "k")
		self.assertIn("fx-grain", html_)
		self.assertNotIn("fx-bokeh", html_)  # specks of light only in the cinematic direction
		html_, css = finish.layers("cinematic", p, "dark", 1080, 1080, "k")
		self.assertIn("fx-bokeh", html_)
		self.assertIn("pointer-events:none", css)  # never takes a touch in Move and resize
		self.assertEqual(finish.layers("cinematic", p, "dark", 1080, 1080, "k"), (html_, css))  # the same every render
		self.assertEqual(finish.default_for("dark"), "premium")

	def test_lit_elements_are_valid_svg(self):
		p = base.palette({"primary": "#2563eb", "accent": "#fff"})
		for n in ("badge", "pill", "cta", "icon_tile", "date_block", "ribbon", "price_tag", "starburst", "device_laptop", "device_phone"):
			ET.fromstring(elements.element(n, p, 240, 120, text="icon_cloud" if n == "icon_tile" else "Hello", tone="accent"))

	def test_buttons_widen_instead_of_shrinking(self):
		from qtt_platform.design import layouts

		x = layouts.Ctx(palette=base.palette({"primary": "#2563eb"}), fonts={}, height=1080, look="light", content={})
		svg = x.el("cta", 300, 70, text="Book your free visit today", tone="primary")
		w = int(re.search(r'width="(\d+)"', svg).group(1))
		self.assertGreater(w, 300)
		self.assertIn('width="300"', x.el("cta", 300, 70, text="Go", tone="primary"))

	def test_fit_warnings(self):
		from qtt_platform.design import fitcheck

		fitcheck.budgets.cache_clear()
		real = fitcheck.budgets
		fitcheck.budgets = lambda: {"sale": {"headline": 20, "phone": 16}}
		try:
			self.assertEqual(fitcheck.check("sale", {"headline": "Big *sale*", "phone": "98400 12345"}), [])
			w = fitcheck.check("sale", {"headline": "A very long headline that will never fit in the box"})
			self.assertEqual(w[0]["slot"], "headline")
			self.assertEqual(w[0]["max"], 20)
			self.assertEqual(fitcheck.check("sale", {"headline": "x" * 26}, "story"), [])  # taller sizes hold more
			self.assertEqual(fitcheck.check("unknown", {"headline": "x" * 300}), [])
		finally:
			fitcheck.budgets = real

	def test_new_layouts_render_every_size(self):
		from qtt_platform.design import archetypes, archetypes_more, catalog, layouts

		for name, fn in archetypes_more.LAYOUTS.items():
			self.assertIs(archetypes.LAYOUTS[name], fn, name)
			t = next(t for t in catalog.templates() if t["layout"] == name)
			for h in (1080, 1350, 1920):
				for content in (catalog.sample_for(name, t["sample_group"]), {"business": "Shop"}):
					x = layouts.Ctx(palette=base.palette(catalog.PALETTES[t["palette"]]), fonts=base.fonts("Poppins", "Inter"), height=h,
									look=t["look"], content=content, photos=["a.jpg"], finish="premium", key=name)
					body, css = fn(x, t["variant"])
					page = layouts.page(body, css, x, 1080, h)
					self.assertIn("qttReady", page)
					self.assertNotIn("None", body, name)  # an empty slot is left out, never printed

	def test_trend_sets_are_readable(self):
		from qtt_platform.design import palettes

		for key, (_l, _m, c) in palettes.CURATED.items():
			p = base.palette(c)
			for role in ("primary", "dark", "light"):
				self.assertGreaterEqual(base.contrast(p[role], p["on_" + role]), 4.5, f"{key} {role}")


if __name__ == "__main__":
	unittest.main()
