"""
QTT Studio › Move and resize (PROJ-0012 S2) — the rules, no bench. (The editor itself was tried in Chrome: a drag, bigger
and new words saved, then the same page drawn with the saved moves matches the editor.)

    python -m unittest qtt_platform.tests.test_arrange -v
"""

import json
import unittest

from qtt_platform.design import arrange, archetypes, base, catalog, layouts


class Clean(unittest.TestCase):
	def test_keeps_what_is_valid(self):
		raw = {"square": {"2": {"t": "H1", "tf": "translate(157.2px, 209.7px) rotate(-4deg) scale(1.15)", "text": "Fresh *meals*"},
						  "5": {"t": "svg", "hide": True}}}
		out = arrange.clean_edits(raw)
		self.assertEqual(out["square"]["2"]["tf"], "translate(157.2px, 209.7px) rotate(-4deg) scale(1.15)")
		self.assertEqual(out["square"]["2"]["text"], "Fresh *meals*")
		self.assertEqual(out["square"]["5"], {"t": "svg", "hide": 1})
		self.assertEqual(arrange.clean_edits(json.dumps(raw)), out)  # as the app sends it

	def test_moveable_transforms(self):
		for tf in ("translate(-50%, -50%) translate(10px, 0px)", "matrix(1, 0, 0, 1, 12.5, -3)", "rotate(0.5turn)", "scale(1.2, 1.2)",
				   "translate(1e-5px, 2px)"):
			self.assertEqual(arrange.clean_edits({"story": {"0": {"t": "DIV", "tf": tf}}})["story"]["0"]["tf"], tf, tf)

	def test_drops_anything_else(self):
		bad = {
			"poster": {"1": {"t": "H1", "tf": "scale(2)"}},  # unknown size
			"square": {
				"x": {"t": "H1", "tf": "scale(2)"},  # not a piece number
				"999": {"t": "H1", "tf": "scale(2)"},  # too far
				"1": {"t": "<script>", "tf": "scale(2)"},  # not a tag
				"2": {"t": "H1", "tf": "url(javascript:alert(1))"},  # not a transform
				"3": {"t": "H1", "tf": "scale(2); background:red"},
				"4": {"t": "H1"},  # nothing changed
			},
		}
		self.assertEqual(arrange.clean_edits(bad), {})
		self.assertEqual(arrange.clean_edits("not json"), {})
		self.assertEqual(arrange.clean_edits([1, 2]), {})

	def test_words_are_capped(self):
		out = arrange.clean_edits({"square": {"0": {"t": "DIV", "text": "x" * 1000}}})
		self.assertEqual(len(out["square"]["0"]["text"]), arrange.MAX_TEXT)

	def test_without_text_keeps_moves(self):
		e = {"square": {"1": {"t": "H1", "tf": "scale(2)", "text": "a"}, "2": {"t": "DIV", "text": "b"}}, "story": {"0": {"t": "B", "text": "c"}}}
		self.assertEqual(arrange.without_text(e), {"square": {"1": {"t": "H1", "tf": "scale(2)"}}})


class Page(unittest.TestCase):
	def _page(self, edits=None):
		t = catalog.templates()[0]
		x = layouts.Ctx(palette=base.palette(catalog.PALETTES[t["palette"]]), fonts=base.fonts(*catalog.FONT_SETS[t["fonts"]], ""),
						height=1080, look=t["look"], content=catalog.sample_for(t["layout"], "any"), photos=["photo0.webp"])
		body, css = archetypes.LAYOUTS[t["layout"]](x, t["variant"] or {})
		return layouts.page(body, css, x, 1080, 1080, arrange.script_for(edits, "square"))

	def test_every_page_numbers_its_pieces_before_fitting(self):
		html = self._page()
		self.assertIn("window.qttPieces", html)
		self.assertLess(html.index("window.qttPieces=function"), html.index("window.qttReady=true"))
		self.assertNotIn("window.qttEdits=", html)

	def test_saved_moves_go_in_safely(self):
		html = self._page({"square": {"1": {"t": "H1", "text": "</script><b>x"}}})
		self.assertIn("window.qttEdits=", html)
		self.assertNotIn("</script><b>x", html)  # can't close the script
		self.assertEqual(arrange.script_for({"story": {"1": {"t": "H1"}}}, "square"), "")

	def test_editor_page(self):
		html = self._page()
		ed = arrange.editor_page(html.replace("photo0.webp", "photo0.webp"), {"photo0.webp": b"RIFF....WEBP"}, 1080, {"1": {"t": "H1", "tf": "scale(2)"}})
		self.assertIn(arrange.MOVEABLE, ed)
		self.assertIn("QttEditor.postMessage", ed)
		self.assertIn("window.qttSaved=", ed)
		self.assertNotIn("window.qttEdits=", ed)  # the editor applies the saved moves itself, once
		self.assertIn("width=device-width", ed)

	def test_inline_files(self):
		page = '<img src="logo.png"><div style="background-image:url(\'photo0.jpg\')"></div><p>photo0.jpg is here</p>'
		out = arrange.inline_files(page, {"logo.png": b"\x89PNG", "photo0.jpg": b"\xff\xd8"})
		self.assertIn('src="data:image/png;base64,', out)
		self.assertIn("url('data:image/jpeg;base64,", out)
		self.assertIn("<p>photo0.jpg is here</p>", out)  # words aren't touched


if __name__ == "__main__":
	unittest.main()
