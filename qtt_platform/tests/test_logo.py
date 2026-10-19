"""
QTT Studio › Logo and brand (PROJ-0012 S5) — logos from the name, an icon and the brand; AI marks made safe. No bench.
(Drawn in Chrome while building: twelve ideas on one sheet, and an AI mark beside the name, in a ring, and stacked.)

    python -m unittest qtt_platform.tests.test_logo -v
"""

import unittest

from qtt_platform.design import base, logo

PAL = base.palette({"primary": "#0f766e"})
FONTS = base.fonts("Poppins", "Inter", "")


class Initials(unittest.TestCase):
	def test_initials(self):
		self.assertEqual(logo.initials("Sri Lakshmi Bags"), "SL")
		self.assertEqual(logo.initials("The Anbu Dental Care Pvt Ltd"), "AD")
		self.assertEqual(logo.initials("Zoho"), "ZO")
		self.assertEqual(logo.initials("அன்பு பல் மருத்துவம்"), "அப")
		self.assertEqual(logo.initials(""), "Q")


class Spec(unittest.TestCase):
	def test_only_known_things(self):
		s = logo.clean_spec({"kind": "monogram", "shape": "star", "icon": "icon_evil", "tone": "rainbow", "name": "  A   B  ", "mark": "x"}, name="")
		self.assertEqual((s["shape"], s["icon"], s["tone"], s["name"], s["mark"]), ("circle", None, "primary", "A B", None))
		self.assertIsNone(logo.clean_spec({"kind": "poster"}, name="A"))
		self.assertIsNone(logo.clean_spec({"kind": "wordmark", "name": ""}, name=""))
		self.assertEqual(len(logo.clean_spec({"kind": "wordmark", "name": "x" * 100}, name="")["name"]), 40)

	def test_a_dozen_ideas_every_kind(self):
		ideas = logo.ideas("Anbu Dental Care", "Gentle care", "icon_heart", PAL)
		self.assertEqual(len(ideas), 12)
		self.assertEqual({i["kind"] for i in ideas}, set(logo.KINDS))
		self.assertTrue(all(i["icon"] == "icon_heart" for i in ideas))


class Drawing(unittest.TestCase):
	def test_svg_and_words_escaped(self):
		s = logo.clean_spec({"kind": "side", "name": "<script>alert(1)</script> & Co"}, name="")
		out = logo.svg(s, PAL, FONTS)
		self.assertTrue(out.startswith("<svg"))
		self.assertNotIn("<script>", out)
		self.assertIn("&lt;script&gt;", out)
		self.assertIn("fonts.googleapis.com", out)  # its font comes with it
		self.assertIn('width="2000"', logo.svg(s, PAL, FONTS, scale=2))

	def test_sheet_has_every_idea(self):
		ideas = logo.ideas("Sri Lakshmi Bags", "", "icon_cart", PAL)
		page, w, h = logo.sheet(ideas, PAL, FONTS)
		self.assertEqual((w, h), (3 * logo.TILE[0], 4 * logo.TILE[1]))
		import re

		self.assertEqual(len(re.findall(r'<g transform="translate\([^)]*\) scale\(', page)), 12)  # one cell each
		self.assertIn("window.qttReady", page)


class AiMark(unittest.TestCase):
	RAW = ('<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2048 2048">'
		   '<path transform="translate(0,0)" fill="rgb(255,255,255)" d="M 0 0 L 2048 0 L 2048 2048 L 0 2048 L 0 0 z"/>'
		   '<path fill="#0f766e" d="M10 10 L100 100 Z" onclick="steal()"/>'
		   '<script>alert(1)</script><image href="https://evil.example/x.png"/><use xlink:href="#a"/>'
		   '<rect style="fill:url(https://evil.example/f)" width="5" height="5"/></svg>')

	def test_made_safe(self):
		m = logo.safe_mark(self.RAW)
		for bad in ("<script", "onclick", "evil.example"):
			self.assertNotIn(bad, m)
		self.assertNotIn("L 2048 2048 L 0 2048", m)  # the white background is gone
		self.assertIn('fill="#0f766e"', m)  # the drawing stays
		self.assertIn('href="#a"', m)  # links inside the drawing stay
		self.assertIn('viewBox="0 0 2048 2048"', m)

	def test_not_a_drawing(self):
		self.assertIsNone(logo.safe_mark("<html>no</html>"))
		self.assertIsNone(logo.safe_mark('<svg viewBox="0 0 10 10"><script>x</script></svg>'))

	def test_prompt_has_no_words(self):
		p = logo.mark_prompt("a friendly tooth", "Dental clinic")
		for must in ("a friendly tooth", "Dental clinic", "No text", "no letters"):
			self.assertIn(must, p)
		self.assertLess(len(logo.mark_prompt("x" * 1000)), 450)

	def test_marks_draw_in_the_layouts(self):
		mark = logo.safe_mark(self.RAW)
		for kind in ("side", "emblem", "stacked"):
			s = logo.clean_spec({"kind": kind, "name": "Anbu", "mark": "a" * 16}, name="")
			self.assertIn('viewBox="0 0 1024 1024"', logo.svg(s, PAL, FONTS, mark))


if __name__ == "__main__":
	unittest.main()
