"""
Curated colour sets for Studio › Poster variations (PROJ-0012 S10) — kept apart from the layouts, which only ever use
colour roles (primary, accent, dark, light…; base.palette works out the rest). A business's own brand kit always comes
first; these are offered when it has none, or when the owner picks "try other colours" — never forced on a brand.

rank() orders them for one screenshot: a set whose main colours sit close to the screenshot's own strong colours (a blue
app on a blue poster, orange buttons beside an orange button) competes with it, so it goes down the list; a set with
calm, well-separated colours goes up. Nothing here changes the screenshot itself.

Pure (PIL only for reading the screenshot); tests/test_palettes.py.
"""

import colorsys
import io

# key: (label, mood, colours) — each a complete, tested combination (background, text, highlight, CTA)
CURATED = {
	"navy_gold": ("Navy and gold", "premium, trustworthy",
				  {"primary": "#14306b", "secondary": "#0e2350", "accent": "#d4a72c", "dark": "#0a1733", "light": "#f7f5ef"}),
	"purple_lavender": ("Deep purple and lavender", "modern, distinctive",
						{"primary": "#5b2a86", "secondary": "#3d1b5c", "accent": "#c4b5fd", "dark": "#1c0f30", "light": "#f5f1ff"}),
	"royal_orange": ("Royal blue and orange", "professional, action",
					 {"primary": "#1d4ed8", "secondary": "#1e3a8a", "accent": "#f97316", "dark": "#0b1b45", "light": "#f4f7ff"}),
	"teal_mint": ("Teal and mint", "fresh, calm",
				  {"primary": "#0f766e", "secondary": "#115e59", "accent": "#5eead4", "dark": "#062a28", "light": "#effcf8"}),
	"charcoal_gold": ("Charcoal, gold and cream", "sophisticated",
					  {"primary": "#2b2b2b", "secondary": "#3a3a3a", "accent": "#c9a227", "dark": "#161616", "light": "#faf6ec"}),
	"mono_yellow": ("Black, white and yellow", "bold, high-impact",
					{"primary": "#111111", "secondary": "#262626", "accent": "#facc15", "dark": "#0a0a0a", "light": "#ffffff"}),
	"indigo_cyan": ("Indigo and cyan", "tech, energetic",
					{"primary": "#3730a3", "secondary": "#312e81", "accent": "#22d3ee", "dark": "#12103a", "light": "#f2f5ff"}),
	"forest_cream": ("Forest green, cream and gold", "natural, traditional",
					 {"primary": "#1f4d36", "secondary": "#173a29", "accent": "#c9a227", "dark": "#0f2a1d", "light": "#f6f1e3"}),
	"burgundy_cream": ("Burgundy, cream and gold", "editorial, elegant",
					   {"primary": "#7a1f2b", "secondary": "#5c1720", "accent": "#c9a227", "dark": "#2a0b10", "light": "#f7f0e6"}),
	"orange_navy": ("Warm orange and deep navy", "energetic, strong contrast",
					{"primary": "#ea580c", "secondary": "#c2410c", "accent": "#0f1f3d", "dark": "#0f1f3d", "light": "#fff7ed"}),
}


def _hue(hex_: str) -> tuple[float, float, float]:
	r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
	return colorsys.rgb_to_hls(r, g, b)


def shot_colours(data: bytes) -> dict:
	"""The screenshot's strong colours: {hues: [(hue 0–1, share)], light: share of light pixels}. Read only, never changed."""
	from PIL import Image

	im = Image.open(io.BytesIO(data)).convert("RGB")
	im.thumbnail((120, 240))
	px = list(im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())
	bins = [0] * 24
	light = 0
	for r, g, b in px:
		h, l_, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
		if l_ > .8:
			light += 1
		if s > .45 and .2 < l_ < .8:  # a strong colour (buttons, chips, icons) — greys and white don't count
			bins[int(h * 24) % 24] += 1
	n = max(1, len(px))
	hues = sorted(((i / 24 + 1 / 48, c / n) for i, c in enumerate(bins) if c / n > .006), key=lambda t: -t[1])
	return {"hues": hues[:4], "light": light / n}


def _clash(colour: str, hues: list) -> float:
	"""How much this colour fights the screenshot's own (0 none … 1 the same hue as its main colour)."""
	h, l_, s = _hue(colour)
	if s < .25 or l_ < .12 or l_ > .9:
		return 0.0  # near-black, near-white and greys never fight a screenshot
	worst = 0.0
	for hh, share in hues:
		d = min(abs(h - hh), 1 - abs(h - hh))
		if d < .07:
			worst = max(worst, min(1.0, share * 8) * (1 - d / .07))
	return worst


def rank(colours: dict | None) -> list[str]:
	"""Curated sets, best first for this screenshot (the order they're defined in when nothing is known)."""
	if not colours or not colours.get("hues"):
		return list(CURATED)
	hues = colours["hues"]

	def score(key):
		c = CURATED[key][2]
		return _clash(c["primary"], hues) * 2 + _clash(c["accent"], hues) * 1.4 + _clash(c["secondary"], hues) * .5

	order = list(CURATED)
	return sorted(order, key=lambda k: (round(score(k), 3), order.index(k)))
