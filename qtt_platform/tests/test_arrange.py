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


class FullEditor(unittest.TestCase):
	"""The full editor (24 Oct 2026): styles, added pieces, a background, photos — only fixed choices get through."""

	def test_styles_keep_only_fixed_choices(self):
		s = arrange.clean_style({"c": "#FFAA00", "f": "Poppins", "fs": "72", "fw": 800, "it": True, "al": "center", "fx": "glow", "op": 0.5,
								 "flt": "warm", "br": 120, "bl": 4, "fr": "circle", "fl": 1, "z": 5, "clip": "inset(10px 20px 30px 40px)"})
		self.assertEqual(s, {"c": "#ffaa00", "f": "Poppins", "fs": 72, "fw": 800, "it": 1, "al": "center", "fx": "glow", "op": 0.5, "flt": "warm",
							 "br": 120, "bl": 4, "fr": "circle", "fl": 1, "z": 5, "clip": "inset(10px 20px 30px 40px)"})
		bad = arrange.clean_style({"c": "red;background:url(x)", "f": "Comic Sans; x", "fs": 9999, "fx": "evil", "op": 3,
								   "clip": "url(javascript:x)", "al": "justify", "z": "1e9"})
		self.assertEqual(bad, {})

	def test_added_pieces(self):
		raw = {"square": {"_add": [
			{"id": "a1", "k": "text", "x": 100, "y": 200, "w": 600, "text": "Fresh *cake*", "s": {"fs": 80, "c": "#ffffff"}},
			{"id": "a2", "k": "badge", "x": 800, "y": 60, "w": 200, "h": 200, "text": "20% OFF", "shape": "burst"},
			{"id": "a3", "k": "shape", "x": 0, "y": 0, "w": 300, "h": 40, "shape": "line", "s": {"bg": "#123456"}},
			{"id": "a4", "k": "icon", "x": 0, "y": 0, "w": 90, "h": 90, "icon": "phone"},
			{"id": "a5", "k": "photo", "x": 0, "y": 0, "w": 400, "h": 400, "src": "item:QLI-0001", "s": {"fr": "circle"}},
			{"id": "a6", "k": "photo", "x": 0, "y": 0, "w": 400, "h": 400, "src": "https://evil/x.png"},  # not a photo of theirs
			{"id": "BAD!", "k": "text", "x": 0, "y": 0, "w": 10, "text": "x"},
			{"id": "a7", "k": "script", "x": 0, "y": 0, "w": 10},
			{"id": "a1", "k": "text", "x": 0, "y": 0, "w": 10, "text": "twice"},
		], "_bg": "#0B0D12", "2": {"t": "IMG", "src": "photo:BP-1", "s": {"flt": "bw"}}}}
		out = arrange.clean_edits(raw)["square"]
		self.assertEqual([a["id"] for a in out["_add"]], ["a1", "a2", "a3", "a4", "a5"])
		self.assertEqual(out["_add"][1]["shape"], "burst")
		self.assertEqual(out["_bg"], "#0b0d12")
		self.assertEqual(out["2"], {"t": "IMG", "src": "photo:BP-1", "s": {"flt": "bw"}})
		self.assertEqual(sorted(arrange.sources(arrange.clean_edits(raw))), ["item:QLI-0001", "photo:BP-1"])
		self.assertEqual(arrange.clean_edits({"square": {"_add": "x", "_bg": "red"}}), {})

	def test_without_text_keeps_added_pieces(self):
		e = {"square": {"1": {"t": "H1", "text": "a"}, "_add": [{"id": "a1", "k": "text", "x": 0, "y": 0, "w": 9, "text": "b"}], "_bg": "#000000"}}
		self.assertEqual(arrange.without_text(e), {"square": {"_add": e["square"]["_add"], "_bg": "#000000"}})

	def test_script_loads_fonts_and_photos(self):
		js = arrange.script_for({"square": {"1": {"t": "H1", "s": {"f": "Pacifico"}}}}, "square", {"item:Q1": "src-item-Q1-ab.jpg"})
		self.assertIn("window.qttLinks", js)
		self.assertIn("Pacifico", js)
		self.assertIn('window.qttSrc={"item:Q1": "src-item-Q1-ab.jpg"}', js)
		self.assertNotIn("qttLinks", arrange.script_for({"square": {"1": {"t": "H1", "tf": "scale(2)"}}}, "square"))
