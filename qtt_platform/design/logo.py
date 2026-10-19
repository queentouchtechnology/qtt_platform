"""
QTT Studio › Logo and brand (PROJ-0012 S5) — logos drawn from the business's name, an icon and its brand fonts and
colours, as SVG (no Frappe; tests/test_logo.py). The words are always set in a real font — an AI mark (Recraft) is only
ever the symbol beside them, so the name is never misspelt.

  KINDS        monogram (initials in a shape), wordmark (the name), emblem (icon in a ring, name below), side (icon tile
               and name, tagline under), stacked (big initials over the name)
  SHAPES       the monogram's frame: circle, rounded square, hexagon, shield
  initials     "Sri Lakshmi Bags" → "SL" (small words like and / the / pvt / ltd left out)
  ideas        a dozen logo ideas for a business: every kind, shapes and colours from its palette
  clean_spec   a logo picked in the app, checked (only known kinds, shapes, icons, palette roles; words trimmed)
  svg          the logo as a whole SVG (the font comes with it), at its own size
  sheet        a page with every idea in a grid — drawn once, cut into one picture each
"""

import html
import re

from qtt_platform.design import base, elements

KINDS = ("monogram", "wordmark", "emblem", "side", "stacked")
SHAPES = ("circle", "rounded", "hexagon", "shield")
TONES = ("primary", "dark", "accent", "secondary")
SIZE = {"monogram": (600, 600), "stacked": (600, 600), "emblem": (600, 600), "wordmark": (1000, 360), "side": (1000, 360)}
SMALL_WORDS = {"and", "&", "the", "of", "pvt", "ltd", "llp", "inc", "co", "private", "limited", "a"}
TILE = (500, 300)  # one idea's cell on the sheet


def initials(name: str, n: int = 2) -> str:
	words = [w for w in re.findall(r"[^\W\d_]+|\d+", name or "", re.U) if w.lower() not in SMALL_WORDS]
	if not words:
		return (name or "Q").strip()[:1].upper() or "Q"
	if len(words) == 1:
		return words[0][: min(n, 2)].upper() if len(words[0]) > 1 and n > 1 and words[0][1].isalpha() else words[0][:1].upper()
	return "".join(w[0] for w in words[:n]).upper()


def _esc(t: str) -> str:
	return html.escape(str(t or ""), quote=True)


def _shape(shape: str, cx: float, cy: float, r: float, fill: str) -> str:
	if shape == "rounded":
		return f'<rect x="{cx - r:.1f}" y="{cy - r:.1f}" width="{2 * r:.1f}" height="{2 * r:.1f}" rx="{r * .32:.1f}" fill="{fill}"/>'
	if shape == "hexagon":
		import math

		pts = " ".join(f"{cx + r * math.cos(math.radians(60 * k - 90)):.1f},{cy + r * math.sin(math.radians(60 * k - 90)):.1f}" for k in range(6))
		return f'<polygon points="{pts}" fill="{fill}"/>'
	if shape == "shield":
		return (f'<path d="M{cx:.1f} {cy - r:.1f} L{cx + r * .9:.1f} {cy - r * .62:.1f} V{cy + r * .05:.1f} '
				f'C{cx + r * .9:.1f} {cy + r * .55:.1f} {cx + r * .45:.1f} {cy + r * .85:.1f} {cx:.1f} {cy + r:.1f} '
				f'C{cx - r * .45:.1f} {cy + r * .85:.1f} {cx - r * .9:.1f} {cy + r * .55:.1f} {cx - r * .9:.1f} {cy + r * .05:.1f} '
				f'V{cy - r * .62:.1f} Z" fill="{fill}"/>')
	return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"/>'


def _icon(icon: str, pal: dict, x: float, y: float, size: float, colour: str) -> str:
	icon = icon if icon in elements.ICONS else "icon_star"
	inner = elements.element(icon, {**pal, "accent": colour, "primary": colour, "dark": colour}, int(size), int(size), tone="accent")
	return f'<g transform="translate({x:.1f} {y:.1f})">{inner}</g>'


def _text(t: str, x: float, y: float, size: float, colour: str, *, font: str = "heading", weight: int = 800, spacing: float = 0,
		  anchor: str = "middle") -> str:
	fam = "var(--logo-heading)" if font == "heading" else "var(--logo-body)"
	return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" font-weight="{weight}" fill="{colour}" text-anchor="{anchor}" '
			f'dominant-baseline="central" letter-spacing="{spacing:.1f}" style="font-family:{fam}">{_esc(t)}</text>')


def _fit(t: str, width: float, size: float, ratio: float = 0.62) -> float:
	"""A size the words fit in `width` with (about `ratio` of the size per letter)."""
	n = max(1, len(t or ""))
	return min(size, width / (n * ratio))


def clean_spec(spec: dict, *, name: str, tagline: str = "") -> dict | None:
	"""A logo picked in the app → only what's allowed; None when it isn't a logo."""
	if not isinstance(spec, dict) or spec.get("kind") not in KINDS:
		return None
	words = re.sub(r"\s+", " ", str(spec.get("name") or name or "")).strip()[:40]
	if not words:
		return None
	return {
		"kind": spec["kind"],
		"shape": spec.get("shape") if spec.get("shape") in SHAPES else "circle",
		"icon": spec.get("icon") if spec.get("icon") in elements.ICONS else None,
		"tone": spec.get("tone") if spec.get("tone") in TONES else "primary",
		"name": words,
		"tagline": re.sub(r"\s+", " ", str(spec.get("tagline") if spec.get("tagline") is not None else tagline or "")).strip()[:50],
		"initials": re.sub(r"[^\w]", "", str(spec.get("initials") or initials(words)), flags=re.U)[:3].upper() or initials(words),
		"letters": bool(spec.get("letters")) and spec["kind"] == "side",
		"mark": spec.get("mark") if isinstance(spec.get("mark"), str) and re.fullmatch(r"[a-f0-9]{16}", spec.get("mark") or "") else None,
	}


def _body(spec: dict, pal: dict, w: float, h: float, mark_svg: str | None) -> str:
	"""The logo's drawing (without the <svg> wrapper) in a w × h box."""
	k, tone = spec["kind"], spec.get("tone") or "primary"
	main = pal.get(tone) or pal["primary"]
	# the small touches (underlines): the owner's own accent, else a deeper shade of the main colour (a worked-out accent
	# is the opposite colour and can clash)
	touch = pal["accent"] if "accent" in (pal.get("owner") or []) else pal["secondary"]
	on_main = base.on(main, dark=pal["dark"])
	ink = pal["dark"]
	name, tag = spec["name"], spec.get("tagline") or ""
	ini = spec.get("initials") or initials(name)

	def mark(x, y, size):  # the symbol: an AI mark when there is one, else the icon
		if mark_svg:
			return f'<svg x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" viewBox="0 0 1024 1024" preserveAspectRatio="xMidYMid meet">{mark_svg}</svg>'
		return _icon(spec.get("icon") or "icon_star", pal, x, y, size, main)

	if k == "monogram":
		r = min(w, h) * .46
		return _shape(spec["shape"], w / 2, h / 2, r, main) + _text(ini, w / 2, h / 2 + r * .03, _fit(ini, r * 1.4, r * .95, .66), on_main)
	if k == "stacked":
		big = _fit(ini, w * .8, h * .5, .66)
		top = mark(w / 2 - h * .27, h * .08, h * .54) if mark_svg else _text(ini, w / 2, h * .38, big, main, weight=900)
		return (top +
				f'<rect x="{w * .3:.1f}" y="{h * .64:.1f}" width="{w * .4:.1f}" height="{max(3, h * .012):.1f}" fill="{touch}"/>' +
				_text(name.upper(), w / 2, h * .76, _fit(name, w * .86, h * .075, .7), ink, weight=700, spacing=h * .006) +
				(_text(tag, w / 2, h * .87, _fit(tag, w * .86, h * .045, .55), pal.get("secondary") or ink, font="body", weight=500) if tag else ""))
	if k == "emblem":
		r = min(w, h) * .27
		cy = h * .36
		# with an AI mark: a white disc in a coloured ring (the mark's own colours would vanish on the main colour)
		disc = (f' fill="#ffffff" stroke="{main}" stroke-width="{max(3, r * .08):.1f}"' if mark_svg else f' fill="{main}"')
		ring = (f'<circle cx="{w / 2:.1f}" cy="{cy:.1f}" r="{r:.1f}"{disc}/>'
				f'<circle cx="{w / 2:.1f}" cy="{cy:.1f}" r="{r * 1.12:.1f}" fill="none" stroke="{main}" stroke-width="{max(2, r * .05):.1f}"/>')
		sym = mark(w / 2 - r * .58, cy - r * .58, r * 1.16) if mark_svg else _icon(spec.get("icon") or "icon_star", pal, w / 2 - r * .55, cy - r * .55, r * 1.1, on_main)
		return (ring + sym + _text(name, w / 2, h * .78, _fit(name, w * .9, h * .1), ink) +
				(_text(tag, w / 2, h * .89, _fit(tag, w * .9, h * .05, .55), pal.get("secondary") or ink, font="body", weight=500) if tag else ""))
	if k == "side":
		s = h * .62
		x0 = h * .19
		tile = (f'<rect x="{x0:.1f}" y="{(h - s) / 2:.1f}" width="{s:.1f}" height="{s:.1f}" rx="{s * .24:.1f}" fill="{main}"/>'
				if not mark_svg else "")
		if mark_svg:
			sym = mark(x0, (h - s) / 2, s)
		elif spec.get("letters"):  # the initials in the tile instead of an icon
			sym = _text(ini, x0 + s / 2, h / 2 + s * .02, _fit(ini, s * .8, s * .55, .66), on_main)
		else:
			sym = _icon(spec.get("icon") or "icon_star", pal, x0 + s * .2, (h - s) / 2 + s * .2, s * .6, on_main)
		tx = x0 + s + h * .12
		room = w - tx - h * .1
		return (tile + sym + _text(name, tx, h * (.43 if tag else .5), _fit(name, room, h * .3), ink, anchor="start") +
				(_text(tag, tx, h * .68, _fit(tag, room, h * .12, .55), pal.get("secondary") or ink, font="body", weight=500, anchor="start") if tag else ""))
	# wordmark: the name, one key letter-dot in the accent, a line under
	size = _fit(name, w * .9, h * .4)
	return (_text(name, w / 2, h * .44, size, main if tone != "dark" else ink, weight=900, spacing=size * .01) +
			f'<rect x="{w * .5 - w * .12:.1f}" y="{h * .44 + size * .62:.1f}" width="{w * .24:.1f}" height="{max(3, h * .018):.1f}" rx="{h * .009:.1f}" fill="{touch}"/>' +
			(_text(tag.upper(), w / 2, h * .84, _fit(tag, w * .8, h * .075, .7), ink, font="body", weight=600, spacing=h * .008) if tag else ""))


def font_css(fonts: dict) -> str:
	"""The fonts a logo uses, for inside the SVG (and the page it's drawn on)."""
	urls = fonts.get("urls") or [fonts.get("url")]
	imports = "".join(f"@import url('{_esc(u)}');" for u in urls if u)
	return f"{imports}:root{{--logo-heading:{fonts['css_heading']};--logo-body:{fonts['css_body']}}}"


def mark_prompt(about: str, trade: str = "") -> str:
	"""The AI's brief for a logo symbol: the symbol only — no words, letters or numbers (the name is set beside it)."""
	what = re.sub(r"\s+", " ", about or "").strip()[:200]
	trade = re.sub(r"[^\w &/-]", "", trade or "")[:60].strip()
	for_ = f" for a {trade} business" if trade else ""
	return (f"A simple, modern flat logo symbol{for_}: {what}. Centred on plain white, bold clean shapes, at most three "
			"colours, works small. No text, no letters, no numbers, no words, no watermark.")


def svg(spec: dict, pal: dict, fonts: dict, mark_svg: str | None = None, *, background: str | None = None, scale: float = 1) -> str:
	"""The logo as a whole SVG at its own size × `scale` (transparent unless a background colour is given)."""
	w, h = SIZE[spec["kind"]]
	bg = f'<rect width="{w}" height="{h}" fill="{background}"/>' if background else ""
	return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w * scale:g}" height="{h * scale:g}">'
			f'<style>{font_css(fonts)}</style>{bg}{_body(spec, pal, w, h, mark_svg)}</svg>')


def ideas(name: str, tagline: str, icon: str | None, pal: dict) -> list[dict]:
	"""A dozen logo ideas: each kind, in shapes and the palette's colours (the business's own colours first)."""
	icon = icon if icon in elements.ICONS else "icon_star"
	out = [{"kind": "monogram", "shape": "circle", "tone": "primary"}, {"kind": "monogram", "shape": "rounded", "tone": "primary"},
		   {"kind": "monogram", "shape": "hexagon", "tone": "dark"}, {"kind": "monogram", "shape": "shield", "tone": "secondary"},
		   {"kind": "wordmark", "tone": "primary"}, {"kind": "wordmark", "tone": "dark"},
		   {"kind": "side", "tone": "primary"}, {"kind": "side", "tone": "dark", "letters": True},
		   {"kind": "emblem", "tone": "primary"}, {"kind": "emblem", "tone": "dark"},
		   {"kind": "stacked", "tone": "primary"}, {"kind": "stacked", "tone": "dark"}]
	return [clean_spec({**o, "icon": icon, "name": name, "tagline": tagline}, name=name, tagline=tagline) for o in out]


def sheet(specs: list[dict], pal: dict, fonts: dict, marks: dict | None = None, cols: int = 3) -> tuple[str, int, int]:
	"""A page with every idea in a grid of TILE cells (white), drawn once and then cut into one picture each.
	(html, width, height)."""
	tw, th = TILE
	rows = (len(specs) + cols - 1) // cols
	cells = []
	for i, s in enumerate(specs):
		w, h = SIZE[s["kind"]]
		scale = min((tw - 40) / w, (th - 40) / h)
		x = (i % cols) * tw + (tw - w * scale) / 2
		y = (i // cols) * th + (th - h * scale) / 2
		cells.append(f'<g transform="translate({x:.1f} {y:.1f}) scale({scale:.4f})">{_body(s, pal, w, h, (marks or {}).get(s.get("mark") or ""))}</g>')
	W, H = cols * tw, rows * th
	page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{font_css(fonts)}html,body{{margin:0;width:{W}px;height:{H}px;background:#fff}}</style></head>'
			f'<body><svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(cells)}</svg>'
			"<script>(async()=>{try{await document.fonts.ready}catch(e){}window.qttReady=true})()</script></body></html>")
	return page, W, H


def page_for(svg_text: str, w: int, h: int, background: str = "transparent") -> str:
	"""One logo on a page of its own size (for its pictures and its PDF)."""
	return (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;width:{w}px;height:{h}px;background:{background}}}'
			"@page{margin:0}</style></head>"
			f"<body>{svg_text}<script>(async()=>{{try{{await document.fonts.ready}}catch(e){{}}window.qttReady=true}})()</script></body></html>")


def safe_mark(svg_text: str) -> str | None:
	"""An AI mark's SVG made safe to keep and draw: no scripts, no outside links, no event handlers; its inner drawing
	only, sized to 1024 (None when it isn't a drawing)."""
	s = svg_text or ""
	m = re.search(r"<svg\b([^>]*)>(.*)</svg>", s, re.S | re.I)
	if not m:
		return None
	inner = m.group(2)
	inner = re.sub(r"<\s*(script|foreignObject|iframe|object|embed|style)\b.*?<\s*/\s*\1\s*>", "", inner, flags=re.S | re.I)
	inner = re.sub(r"<\s*(script|foreignObject|iframe|object|embed)\b[^>]*/?>", "", inner, flags=re.I)
	inner = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", inner, flags=re.I)
	inner = re.sub(r"(href|xlink:href)\s*=\s*(\"(?!#)[^\"]*\"|'(?!#)[^']*')", "", inner, flags=re.I)
	inner = re.sub(r"url\(\s*['\"]?(?!#)[^)]*\)", "none", inner, flags=re.I)
	vb = re.search(r'viewBox\s*=\s*"([^"]+)"', m.group(1))
	box = vb.group(1) if vb else "0 0 1024 1024"
	nums = re.findall(r"[-\d.]+", box)
	if len(nums) == 4:  # the AI paints a plain background over the whole canvas first — without it the mark sits on any colour
		W, H = float(nums[2]), float(nums[3])
		full = rf'<path[^>]*\bd="M\s*0\s+0\s+L\s*{W:g}\s+0\s+L\s*{W:g}\s+{H:g}\s+L\s*0\s+{H:g}\s+L\s*0\s+0\s*z"[^>]*/>'
		inner = re.sub(full, "", inner, count=1, flags=re.I)
	if not re.search(r"<(path|circle|rect|polygon|ellipse|g)\b", inner, re.I):
		return None
	return f'<svg viewBox="{_esc(box)}" width="1024" height="1024" preserveAspectRatio="xMidYMid meet">{inner}</svg>'
