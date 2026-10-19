"""
QTT Studio › Photo Lab (PROJ-0012 S1) — the picture work, no bench.

    python -m unittest qtt_platform.tests.test_photo_lab -v
"""

import io
import unittest

from PIL import Image, ImageDraw

from qtt_platform.design import base, photo_lab as lab


def _jpeg(im):
	out = io.BytesIO()
	im.save(out, "JPEG")
	return out.getvalue()


def _png(im):
	out = io.BytesIO()
	im.save(out, "PNG")
	return out.getvalue()


def _open(data):
	return Image.open(io.BytesIO(data))


def _cutout(w=300, h=500):
	im = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
	ImageDraw.Draw(im).rounded_rectangle((40, 40, 40 + w, 40 + h), 30, fill=(200, 40, 40, 255))
	return _png(im)


class Enhance(unittest.TestCase):
	def test_dark_photo_is_lifted(self):
		dark = Image.new("RGB", (400, 300), (25, 22, 20))
		ImageDraw.Draw(dark).rectangle((100, 80, 300, 220), fill=(60, 50, 45))
		out = _open(lab.enhance(_jpeg(dark)))
		self.assertGreater(lab.brightness(out), lab.brightness(dark) + 0.15)
		self.assertEqual(out.format, "JPEG")

	def test_good_photo_stays_near(self):
		im = Image.linear_gradient("L").convert("RGB").resize((300, 300))
		before = lab.brightness(im)
		self.assertLess(abs(lab.brightness(_open(lab.enhance(_jpeg(im)))) - before), 0.1)

	def test_transparent_png_and_huge_photo(self):
		self.assertEqual(_open(lab.enhance(_cutout())).mode, "RGB")  # transparency on white
		big = Image.new("RGB", (5000, 2500), (120, 130, 140))
		self.assertLessEqual(max(_open(lab.enhance(_jpeg(big))).size), lab.MAX_SIDE)


class Crop(unittest.TestCase):
	def test_every_size_is_exact(self):
		im = _jpeg(Image.new("RGB", (1600, 1200), (90, 120, 150)))
		for key, (w, h, _) in lab.SIZES.items():
			self.assertEqual(_open(lab.smart_crop(im, key)).size, (w, h), key)

	def test_crop_follows_the_detail(self):
		# a wide photo, the busy part on the right → a square crop keeps the right side
		im = Image.new("RGB", (1200, 400), (240, 240, 240))
		d = ImageDraw.Draw(im)
		for x in range(900, 1180, 12):
			d.line((x, 20, x, 380), fill=(0, 0, 0), width=4)
		cols, rows = lab._energy(im)
		left, _, right, _ = lab.crop_box(im.size, (1080, 1080), cols, rows)
		self.assertEqual(right - left, 400)
		self.assertGreater(left, 600)

	def test_plain_crop_is_centred_or_a_little_high(self):
		self.assertEqual(lab.crop_box((2000, 1000), (1000, 1000)), (500, 0, 1500, 1000))
		_, top, _, bottom = lab.crop_box((1000, 3000), (1000, 1000))
		self.assertEqual(bottom - top, 1000)
		self.assertLess(top, 1000)  # above the middle (1000)

	def test_too_small(self):
		self.assertTrue(lab.too_small(_jpeg(Image.new("RGB", (400, 400))), "story"))
		self.assertFalse(lab.too_small(_jpeg(Image.new("RGB", (1080, 1080))), "square"))


class StudioShot(unittest.TestCase):
	pal = base.palette({"primary": "#1d4ed8"})

	def test_every_backdrop_and_size(self):
		for kind in lab.BACKDROPS:
			for key in ("square", "story", "banner"):
				out = _open(lab.studio_shot(_cutout(), key, kind, self.pal))
				self.assertEqual(out.size, lab.size_of(key))

	def test_product_stands_in_the_middle_with_a_shadow(self):
		out = _open(lab.studio_shot(_cutout(), "square", "white", self.pal)).convert("RGB")
		self.assertGreater(out.getpixel((540, 600))[0], 150)  # the red product in the middle
		self.assertLess(out.getpixel((540, 600))[1], 90)
		self.assertEqual(out.getpixel((20, 20)), (255, 255, 255))  # clean top corner
		below = out.getpixel((540, round(1080 * 0.84) + 4))
		self.assertLess(sum(below), sum(out.getpixel((20, 1070))) - 30)  # darker under it than in the corner (shadow)

	def test_brand_colour_backdrop(self):
		out = _open(lab.studio_shot(_cutout(), "square", "brand", self.pal)).convert("RGB")
		r, g, b = out.getpixel((40, 40))
		self.assertGreater(b, r + 40)  # blue brand

	def test_on_scene_keeps_the_product(self):
		scene = Image.new("RGB", (1024, 1536), (210, 190, 160))
		out = _open(lab.on_scene(_jpeg(scene), _cutout(), "story")).convert("RGB")
		self.assertEqual(out.size, (1080, 1920))
		self.assertGreater(out.getpixel((540, 1100))[0], 150)


class Prompt(unittest.TestCase):
	def test_scene_is_empty_and_never_the_product(self):
		p = lab.scene_prompt("marble")
		for must in ("marble", "no products", "no people", "no text", "no logos"):
			self.assertIn(must, p)
		self.assertIn("a beach at sunset", lab.scene_prompt("marble", "a beach at sunset"))
		self.assertIn("no logos", lab.scene_prompt("x", "anything " * 100))
		self.assertLess(len(lab.scene_prompt("x", "y" * 1000)), 700)

	def test_ai_size_for_every_size(self):
		self.assertEqual(set(lab.AI_SIZES), set(lab.SIZES))


if __name__ == "__main__":
	unittest.main()
