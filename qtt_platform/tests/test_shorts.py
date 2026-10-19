"""
QTT Studio › Shorts (PROJ-0012 S6) — the words, the pages drawn for them, timing and the AI prompt. No bench. (A 10.6 s
1080 × 1920 Short was built while building this — H.264 + a silent AAC track — and its frames checked.)

    python -m unittest qtt_platform.tests.test_shorts -v
"""

import unittest

from qtt_platform.design import base, shorts
from qtt_platform.studio import rules

PAL = base.palette({"primary": "#b45309"})
FONTS = base.fonts("Poppins", "Inter", "")


class Words(unittest.TestCase):
	def test_clean(self):
		s = shorts.clean_script({"hook": "  Homely   *meals* ", "captions": ["a", "b", "c", "d", "e"], "end_line": "x" * 200, "evil": 1})
		self.assertEqual(s["hook"], "Homely *meals*")
		self.assertEqual(len(s["captions"]), shorts.MAX_SCENES)
		self.assertEqual(len(s["end_line"]), 70)
		self.assertNotIn("evil", s)
		self.assertEqual(shorts.clean_script("bad"), {"hook": "", "captions": [], "end_line": ""})

	def test_timing(self):
		self.assertEqual(shorts.timing(3), (10.6, shorts.SCENE_S))
		self.assertEqual(shorts.timing(10)[0], round(shorts.MAX_SCENES * shorts.SCENE_S + shorts.END_S, 2))
		self.assertEqual(shorts.timing(0)[0], round(shorts.SCENE_S + shorts.END_S, 2))


class Pages(unittest.TestCase):
	def test_overlay(self):
		p = shorts.overlay_page("Fresh *daily* <b>x</b>", PAL, FONTS, hook="Homely meals")
		self.assertIn('class="hook"', p)
		self.assertIn("<em>daily</em>", p)
		self.assertNotIn("<b>x</b>", p)
		self.assertIn("background:transparent", p)
		self.assertNotIn('class="hook"', shorts.overlay_page("c", PAL, FONTS))

	def test_end_card(self):
		p = shorts.end_page("Annapoorna <Mess>", "Order now", "+91 98765 43210", "annapoorna.in", PAL, FONTS, logo="logo.png")
		self.assertIn("Annapoorna &lt;Mess&gt;", p)
		self.assertIn('src="logo.png"', p)
		self.assertIn(PAL["primary"], p)


class Prompt(unittest.TestCase):
	def test_short_prompt_never_invents(self):
		m = rules.short_prompt(about="breakfast menu", brief="Annapoorna Mess, Madurai", language="ta", scenes=3)
		s = m[0]["content"]
		for must in ("never invent", "exactly 3", "Tamil", "JSON"):
			self.assertIn(must, s)
		self.assertIn("breakfast menu", m[1]["content"])
		self.assertEqual(rules.parse_json('ok {"hook": "Hi"} done'), {"hook": "Hi"})
		self.assertEqual(rules.CREDITS["short_script"], 2)


if __name__ == "__main__":
	unittest.main()
