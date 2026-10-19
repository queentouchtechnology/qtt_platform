"""
QTT Studio › quality (PROJ-0012 S9) — what the nightly template check flags, and Studio problems on QTT Admin's home.
No bench.

    python -m unittest qtt_platform.tests.test_quality -v
"""

import io
import unittest

from PIL import Image, ImageDraw

from qtt_platform import saas_admin_logic as logic
from qtt_platform.design import quality


def _png(im):
	b = io.BytesIO()
	im.save(b, "PNG")
	return b.getvalue()


class Picture(unittest.TestCase):
	def test_a_real_design_is_fine(self):
		im = Image.new("RGB", (540, 540), "#f5efe6")
		ImageDraw.Draw(im).rectangle((40, 40, 300, 160), fill="#b45309")
		self.assertIsNone(quality.picture_problem(_png(im), 540, 540))

	def test_blank_wrong_size_not_a_picture(self):
		self.assertIn("blank", quality.picture_problem(_png(Image.new("RGB", (540, 540), "#ffffff")), 540, 540))
		self.assertIn("wrong size", quality.picture_problem(_png(Image.new("RGB", (100, 100), "#ffffff")), 540, 540))
		self.assertEqual(quality.picture_problem(b"<html>error</html>", 540, 540), "not a picture")

	def test_summary(self):
		self.assertEqual(quality.summary([{"check_status": "ok"}, {"check_status": "problem"}, {"check_status": ""}, {}]),
						 {"ok": 1, "problem": 1, "unchecked": 2})


class Attention(unittest.TestCase):
	def test_studio_problems_are_one_item(self):
		items = logic.attention_items(studio=[{"key": "a", "title": "Hero split", "note": "story: blank"}, {"key": "b", "title": "Sale"}],
									  today_str="2026-10-20")
		s = [i for i in items if i["kind"] == "studio_templates"]
		self.assertEqual(len(s), 1)
		self.assertEqual((s[0]["count"], s[0]["area"], s[0]["level"]), (2, "studio", "warning"))
		self.assertFalse([i for i in logic.attention_items(today_str="2026-10-20") if i["kind"] == "studio_templates"])


if __name__ == "__main__":
	unittest.main()
