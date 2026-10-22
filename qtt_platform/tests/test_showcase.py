"""
QTT Studio › Poster variations (PROJ-0012 S10) — the showcase layouts, colour sets and rules, no bench.

    python -m unittest qtt_platform.tests.test_showcase -v
"""

import io
import re
import unittest

from qtt_platform.design import archetypes, arrange, base, catalog, layouts, palettes, showcase
from qtt_platform.studio import rules
from qtt_platform.studio import showcase_rules as sr

FULL = {"business": "Acme Tasks", "kicker": "Acme", "headline": "Plan your day *in minutes*", "subline": "Lists, reminders and a calm week.",
		"cta": "Get the app", "stat": "40+", "stat_label": "ready templates", "list": ["Work", "Home", "School", "Health"],
		"steps": ["Sign up", "Add a list", "Done"], "problems": ["Sticky notes everywhere", "Missed deadlines"],
		"items": [{"icon": "icon_check", "title": "Smart lists", "text": ""}, {"icon": "icon_clock", "title": "Reminders", "text": ""},
				  {"icon": "icon_team", "title": "Share with family", "text": ""}]}
PLAIN = {"business": "Acme Tasks", "headline": "Plan your day *in minutes*", "cta": "Get the app"}


SIZES = {"square": 1080, "portrait": 1350, "story": 1920, "wide": 608, "landscape": 720}  # design/post.py (needs Frappe to import)


def _page(layout: str, content: dict, fmt: str, photos=("shot0.png",)) -> str:
	tpl = next(t for t in catalog.templates() if t["layout"] == layout)
	x = layouts.Ctx(palette=base.palette(catalog.PALETTES[tpl["palette"]]), fonts={}, height=SIZES[fmt], look=tpl["look"], content=content,
					photos=list(photos))
	body, css = archetypes.LAYOUTS[layout](x, tpl["variant"])
	return body + "<style>" + css + "</style>"


class Directions(unittest.TestCase):
	def test_thirty_four_directions_each_a_layout_and_a_template(self):
		self.assertEqual(len(showcase.DIRECTIONS), 34)  # 11 first, 20 more, 3 other devices (laptop, tablet, before-and-after)
		keys = {t["layout"] for t in catalog.templates() if t["post_types"] == ["showcase"]}
		self.assertEqual(keys, set(showcase.DIRECTIONS))
		for k in showcase.DIRECTIONS:
			self.assertIn(k, archetypes.LAYOUTS)
		labels = [v[0] for v in showcase.DIRECTIONS.values()]
		self.assertEqual(len(labels), len(set(labels)))
		for t in catalog.templates():
			if t["post_types"] == ["showcase"]:
				self.assertEqual(t["formats"], ["square", "portrait", "story", "wide", "landscape"])
				self.assertIn(t["palette"], catalog.PALETTES)

	def test_every_direction_draws_every_size_with_the_screenshot_as_it_is(self):
		for k in showcase.DIRECTIONS:
			for fmt in SIZES:
				html = _page(k, FULL, fmt, photos=("shot0.png", "shot1.png"))
				self.assertRegex(html, r'<img class="shot( pos-top)?" src="shot0.png">', (k, fmt))  # the owner's own screenshot, untouched
				self.assertIn("data-piece", html, (k, fmt))  # the device moves as one in Move and resize
				self.assertIn("Plan your day", html)

	def test_screenshot_position_and_whole(self):
		html = _page("ui_showcase", {**FULL, "shot_fit": ["bottom"]}, "square")
		self.assertIn('<img class="shot pos-bottom" src="shot0.png">', html)
		html = _page("laptop_showcase", {**FULL, "shot_fit": ["whole"]}, "wide")
		self.assertIn('class="shot whole" src="shot0.png"', html)  # the whole screen, nothing cut
		self.assertIn('class="shot blurfill"', html)
		html = _page("ui_showcase", {**FULL, "shot_fit": ["javascript"]}, "square")
		self.assertIn("pos-top", html)  # anything unknown → the top

	def test_keep_the_screen_clear(self):
		self.assertIn('class="stage clear"', _page("pop_cards", {**FULL, "clear_screen": True}, "portrait"))
		self.assertNotIn('class="stage clear"', _page("pop_cards", FULL, "portrait"))
		self.assertIn("inset:10% 35%", _page("ui_orbit", {**FULL, "clear_screen": True}, "square"))

	def test_before_and_after_labels(self):
		html = _page("before_after", FULL, "square", photos=("shot0.png", "shot1.png"))
		self.assertIn(">Before<", html)
		self.assertIn(">After<", html)
		html = _page("before_after", {**FULL, "before_label": "Paper", "after_label": "Acme"}, "story", photos=("shot0.png", "shot1.png"))
		self.assertIn(">Paper<", html)
		self.assertIn('src="shot1.png"', html)
		self.assertFalse(showcase.can_use("before_after", FULL, 1))

	def test_without_a_screenshot_a_plain_sample_screen(self):
		html = _page("ui_showcase", FULL, "square", photos=())
		self.assertIn('class="sk"', html)
		self.assertNotIn("<img class=\"shot\"", html)

	def test_needs(self):
		self.assertFalse(showcase.can_use("stat_hero", PLAIN, 1))
		self.assertTrue(showcase.can_use("stat_hero", FULL, 1))
		self.assertFalse(showcase.can_use("duo_screens", FULL, 1))
		self.assertTrue(showcase.can_use("duo_screens", FULL, 2))
		self.assertFalse(showcase.can_use("problem_solution_ui", PLAIN, 1))
		self.assertFalse(showcase.can_use("globe_reach", {**FULL, "list": ["One", "Two"]}, 1))
		self.assertTrue(showcase.can_use("ui_showcase", PLAIN, 1))

	def test_nothing_the_owner_did_not_give(self):
		for k in showcase.DIRECTIONS:
			if not showcase.can_use(k, PLAIN, 1):
				continue
			html = _page(k, PLAIN, "portrait")
			text = re.sub(r"<style.*?</style>|<script.*?</script>|<[^>]+>", " ", html, flags=re.S)
			self.assertNotRegex(text, r"\b\d+\s*\+", k)  # no made-up "100+"
			self.assertNotIn("ready templates", text, k)

	def test_showcase_kept_out_of_the_post_library(self):
		t = next(t for t in catalog.templates() if t["layout"] == "device_tilt")
		self.assertFalse(catalog.matches(t))
		self.assertFalse(catalog.matches(t, post_type="product"))
		self.assertTrue(catalog.matches(t, post_type="showcase"))
		self.assertTrue(catalog.matches(next(t for t in catalog.templates() if t["layout"] == "sale")))

	def test_wide_sizes(self):
		from pathlib import Path

		src = (Path(archetypes.__file__).parent / "post.py").read_text(encoding="utf-8")
		self.assertIn('"wide": 608, "landscape": 720', src)
		self.assertIn("wide", arrange.FORMATS)


class Palettes(unittest.TestCase):
	def test_every_set_complete_and_readable(self):
		self.assertGreaterEqual(len(palettes.CURATED), 30)  # the first ten, then the trend and premium sets
		for key, (_label, _mood, c) in palettes.CURATED.items():
			self.assertEqual(set(c), {"primary", "secondary", "accent", "dark", "light"}, key)
			p = base.palette(c)
			self.assertGreaterEqual(base.contrast(p["dark"], p["light"]), 7, key)  # body text on the light background
			self.assertGreaterEqual(base.contrast(p["on_primary"], p["primary"]), 4.5, key)  # words on the main colour
			self.assertIn(key, catalog.PALETTES)

	def _png(self, colour):
		from PIL import Image

		im = Image.new("RGB", (200, 400), "#ffffff")
		im.paste(Image.new("RGB", (200, 120), colour), (0, 140))
		buf = io.BytesIO()
		im.save(buf, "PNG")
		return buf.getvalue()

	def test_sets_that_fight_the_screenshot_go_last(self):
		orange = palettes.rank(palettes.shot_colours(self._png("#f59e0b")))
		# last: a set whose own colours sit on the screenshot's orange (amber, gold, butter, marigold…)
		self.assertGreater(palettes._clash(palettes.CURATED[orange[-1]][2]["primary"], palettes.shot_colours(self._png("#f59e0b"))["hues"])
						   + palettes._clash(palettes.CURATED[orange[-1]][2]["accent"], palettes.shot_colours(self._png("#f59e0b"))["hues"]), 0)
		self.assertLess(orange.index("purple_lavender"), orange.index("royal_orange"))
		blue = palettes.rank(palettes.shot_colours(self._png("#1d4ed8")))
		self.assertGreater(blue.index("royal_orange"), blue.index("teal_mint"))
		self.assertEqual(palettes.rank(None), list(palettes.CURATED))


class Rules(unittest.TestCase):
	def test_numbers_only_from_the_owner(self):
		w = rules.ground_numbers({"headline": "Over 500 happy *users*", "subline": "Rated 4.9 by 10k people", "cta": "Start"}, "We have 159 modules")
		self.assertEqual(w["headline"], "Over happy *users*")
		self.assertNotIn("subline", w)
		self.assertEqual(rules.ground_numbers({"headline": "159+ Bible modules"}, "159+ modules")["headline"], "159+ Bible modules")

	def test_lists_and_sizes(self):
		w = rules.clean_words({"headline": "Hi", "list": ["Tamil", " ", "Hindi"] + ["x"] * 20, "steps": ["a", "b"], "stat": "159+",
							   "items": [{"title": "One", "icon": "icon_globe"}, {"title": "Two", "icon": "javascript:"}]})
		self.assertEqual(w["list"][:2], ["Tamil", "Hindi"])
		self.assertLessEqual(len(w["list"]), 10)
		self.assertEqual(w["items"][0]["icon"], "icon_globe")
		self.assertEqual(w["items"][1]["icon"], "icon_check")
		self.assertEqual(rules.formats_for(["showcase"]), ("square", "portrait", "story", "wide", "landscape"))
		self.assertEqual(rules.formats_for(["offer"]), ("square", "portrait", "story"))

	def test_prompt_never_invents(self):
		m = rules.showcase_prompt(brief="Acme", about="A to-do app", given={"headline": "Plan"}, count=4, language="en")
		self.assertIn("never invent numbers", m[0]["content"])
		self.assertIn("4 different", m[0]["content"])
		self.assertEqual(len(rules.parse_showcase('{"sets": [{"headline": "A"}, {"kicker": "no headline"}, {"headline": "B"}]}')), 2)
		self.assertIn("no phones", rules.backdrop_prompt("an open Bible"))


class Decisions(unittest.TestCase):
	ON = {k: {} for k in showcase.DIRECTIONS}

	def test_brief(self):
		self.assertNotIn("stat", sr.clean_brief({"headline": "A", "stat": "159+"}))  # a number needs what it counts
		w = sr.clean_brief({"headline": "A", "items": ["Fast", "Offline"]})
		self.assertEqual([i["title"] for i in w["items"]], ["Fast", "Offline"])

	def test_directions(self):
		words = sr.clean_brief(PLAIN)
		picked = sr.pick_directions([], words, 1, self.ON, 6)
		self.assertEqual(len(picked), 6)
		for k in picked:
			self.assertTrue(showcase.can_use(k, words, 1))
		self.assertEqual(sr.pick_directions(["stat_hero", "minimal_device"], words, 1, self.ON, 4), ["minimal_device"])
		self.assertEqual(set(sr.SUGGESTED), set(showcase.DIRECTIONS))

	def test_media(self):
		self.assertEqual(sr.clean_media({}, 2), {"fit": ["top", "top"], "clear": False})
		self.assertEqual(sr.clean_media({"fit": ["whole", "nope", "bottom", "middle"], "clear": True}, 3),
						 {"fit": ["whole", "top", "bottom"], "clear": True})
		self.assertEqual(sr.clean_brief({"headline": "A", "before_label": "Paper", "after_label": "Acme"})["after_label"], "Acme")

	def test_small_screenshots_enlarged(self):
		from PIL import Image

		def png(w, h):
			buf = io.BytesIO()
			Image.new("RGB", (w, h), "#3366cc").save(buf, "PNG")
			return buf.getvalue()

		data, w, h = sr.upscale(png(540, 1170))
		self.assertEqual((w, h), (831, 1800))
		self.assertEqual(Image.open(io.BytesIO(data)).format, "PNG")
		self.assertIsNone(sr.upscale(png(1080, 2340)))  # big enough: kept exactly as it is

	def test_colours(self):
		ranked = list(palettes.CURATED)
		self.assertEqual(sr.colour_sets("", True, ranked, 3), [None, None, None])  # a brand: always theirs
		self.assertEqual(sr.colour_sets("auto", True, ranked, 3), ranked[:3])
		self.assertEqual(sr.colour_sets("", False, ranked, 2), ranked[:2])
		self.assertEqual(sr.colour_sets("teal_mint", True, ranked, 2), ["teal_mint", "teal_mint"])


class Pieces(unittest.TestCase):
	def test_marked_pieces_move_as_one(self):
		self.assertIn("data-piece", arrange.PIECES_JS)
		self.assertIn("data-piece", showcase._phone(layouts.Ctx(palette=base.palette({}), fonts={}, height=1080, look="light", content={}, photos=["a.png"])))


if __name__ == "__main__":
	unittest.main()
