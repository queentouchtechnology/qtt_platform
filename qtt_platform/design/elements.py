"""
Design elements (PROJ-0011 B): badges, price tags, ribbons, dividers, icons — SVG in the business's palette.

element(name, palette, width, height, text="", tone=...) → a whole <svg> the templates place over a background. Text on
an element is the template's own words (a price written in the knowledge, "New", the business's phone) — an element
never invents an offer. tone picks the element's colour: accent (default), primary or dark. No other company's logo
is ever drawn (no WhatsApp, Instagram or payment marks) — icons are plain shapes.
"""

import hashlib
import html
import math

from qtt_platform.design.base import contrast, hex6, mix

# name: (label, needs text)
ELEMENTS = {
	"badge": ("Round badge", True), "price_tag": ("Price tag", True), "ribbon": ("Ribbon", True),
	"starburst": ("Starburst", True), "pill": ("Pill label", True), "corner_ribbon": ("Corner ribbon", True),
	"wave_divider": ("Wave divider", False), "swash": ("Underline swash", False), "quote": ("Quote marks", False),
	"sparkle": ("Sparkle", False), "arrow": ("Arrow", False), "dots_line": ("Dotted line", False),
	"icon_phone": ("Phone", False), "icon_pin": ("Location pin", False), "icon_clock": ("Clock", False),
	"icon_check": ("Tick", False), "icon_truck": ("Delivery", False), "icon_star": ("Star", False),
	"icon_cart": ("Shopping bag", False), "icon_calendar": ("Calendar", False),
	# technology (QTT's reference posts): icon tiles, device frames, a call-to-action pill, tech icons
	"icon_tile": ("Icon tile", False), "device_laptop": ("Laptop frame", False), "device_phone": ("Phone frame", False),
	"cta": ("Button with arrow", True),
	"icon_cloud": ("Cloud", False), "icon_shield": ("Shield", False), "icon_gear": ("Gear", False), "icon_chart": ("Chart", False),
	"icon_rocket": ("Rocket", False), "icon_team": ("Team", False), "icon_mail": ("Email", False), "icon_globe": ("Website", False),
	"icon_lock": ("Lock", False), "icon_ai": ("AI chip", False), "icon_code": ("Code", False), "icon_sync": ("Backup / sync", False),
}
ELEMENTS.update({
	# local market (local-post-references.md): brush strokes, date block, QR, labelled circles, wave band, ornaments
	"brush_banner": ("Brush banner", True), "brush_swipe": ("Brush swipe", True), "brush_underline": ("Brush underline", False),
	"brush_badge": ("Brush price badge", True), "date_block": ("Date block", True), "qr": ("QR code", False),
	"label_circle": ("Circle with label", True), "wave_band": ("Wave band", False), "flourish": ("Ornament divider", False),
	"icon_book": ("Book", False), "icon_home": ("House", False), "icon_drop": ("Water", False), "icon_bolt": ("Power", False),
	"icon_cross": ("Cross", False), "icon_lamp": ("Lamp", False), "icon_music": ("Music note", False), "icon_heart": ("Heart", False),
})
ELEMENTS.update({
	# modern agency style: hand-drawn marks, a cloud bubble, outline boxes, a vertical label, an order bar
	"scribble_circle": ("Hand-drawn circle", True), "dashed_arrow": ("Curved dashed arrow", False), "splash": ("Paint splash", False),
	"speech_cloud": ("Cloud bubble", True), "outline_box": ("Outline box", False), "vertical_label": ("Vertical label", True),
	"order_bar": ("Order bar", True), "hand_underline": ("Hand-drawn underline", False),
})
ICONS = [n for n in ELEMENTS if n.startswith("icon_") and n != "icon_tile"]


def _qr(data: str, w: float, h: float, colour: str) -> str:
	"""A QR code as SVG squares on white (with its quiet zone), made locally (PyQRCode, part of Frappe)."""
	s = min(w, h)
	try:
		import pyqrcode

		code = pyqrcode.create(str(data or " ")[:500], error="M").code  # rows of 0 / 1, quiet zone included
	except Exception:
		return f'<rect width="{s:.0f}" height="{s:.0f}" fill="#ffffff"/>'
	cell = s / len(code)
	squares = "".join(f'<rect x="{x * cell:.2f}" y="{y * cell:.2f}" width="{cell + .3:.2f}" height="{cell + .3:.2f}"/>'
					  for y, row in enumerate(code) for x, v in enumerate(row) if v)
	return f'<rect width="{s:.0f}" height="{s:.0f}" rx="{s * .04:.0f}" fill="#ffffff"/><g fill="{colour}">{squares}</g>'


def _brush(w: float, h: float, seed: str, *, ragged: float = .12) -> str:
	"""A dry-brush stroke filling w × h: wavy top and bottom edges, torn ends."""
	import random

	rnd = random.Random(seed)
	n = 14
	top = [(w * k / n, h * (rnd.random() * ragged)) for k in range(n + 1)]
	bottom = [(w * k / n, h * (1 - rnd.random() * ragged)) for k in range(n, -1, -1)]
	right = [(w - rnd.random() * w * .03, h * (.15 + .7 * k / 5)) for k in range(1, 5)]
	left = [(rnd.random() * w * .03, h * (.85 - .7 * k / 5)) for k in range(1, 5)]
	pts = top + right + bottom + left
	return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"
TONES = ("accent", "primary", "dark")


def _colours(p: dict, tone: str) -> tuple[str, str]:
	tone = tone if tone in TONES else "accent"
	return p[tone], p[f"on_{tone}"]


def _text(t: str, x: float, y: float, size: float, colour: str, weight: int = 800, anchor: str = "middle") -> str:
	if not t:
		return ""
	return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size:.0f}" font-weight="{weight}" fill="{colour}" text-anchor="{anchor}" '
			f'dominant-baseline="central" style="font-family:var(--font-heading, sans-serif)">{html.escape(str(t)[:40])}</text>')


def _fit(t: str, w: float, h: float, base: float = 0.42) -> float:
	"""A font size the text fits in (roughly: 0.58 em per character)."""
	n = max(len(str(t or "")), 1)
	return max(10.0, min(h * base, w * 0.86 / (n * 0.58)))


# ---- premium finish: a soft fall of light over a shape, a glass highlight, a fine light edge (the shape's own colour) --
def _gid(*parts) -> str:
	"""A gradient id from what it draws: the same id is always the same gradient, so SVGs on one page never clash."""
	return "q" + hashlib.md5("|".join(str(x) for x in parts).encode()).hexdigest()[:10]


def _lit(colour: str) -> tuple[str, str]:
	"""(defs, fill) — the colour lit from above: a little lighter at the top, a little deeper at the bottom. A colour that
	isn't plain hex (#fff, a CSS name) is drawn flat."""
	c = str(colour or "").strip()
	if len(c) == 4 and c.startswith("#"):
		c = "#" + "".join(ch * 2 for ch in c[1:])
	if not hex6(c):
		return "", colour
	colour = c
	gid = _gid("lit", colour)
	return (f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{mix(colour, "#ffffff", .2)}"/>'
			f'<stop offset=".55" stop-color="{colour}"/><stop offset="1" stop-color="{mix(colour, "#000000", .16)}"/></linearGradient>'), f"url(#{gid})"


def _gloss(x: float, y: float, w: float, h: float, rx: float) -> str:
	"""A glass highlight over the top of a rounded shape, and its fine light edge."""
	gid = _gid("gloss")
	return (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".34"/>'
			f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
			f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{max(0, w - 2):.1f}" height="{h * .52:.1f}" rx="{rx:.1f}" fill="url(#{gid})"/>'
			f'<rect x="{x + .75:.1f}" y="{y + .75:.1f}" width="{max(0, w - 1.5):.1f}" height="{max(0, h - 1.5):.1f}" rx="{rx:.1f}" fill="none" '
			f'stroke="#fff" stroke-opacity=".22" stroke-width="1.5"/>')


def element(name: str, palette: dict, width: int, height: int, *, text: str = "", tone: str = "accent") -> str:
	w, h = int(width), int(height)
	bg, fg = _colours(palette, tone)
	t = str(text or "")
	b = ""
	lit_defs, lit = _lit(bg)
	if name == "badge":
		r = min(w, h) / 2
		b = (f'<defs>{lit_defs}</defs><circle cx="{w / 2}" cy="{h / 2}" r="{r:.0f}" fill="{lit}"/>'
			 f'<ellipse cx="{w / 2}" cy="{h / 2 - r * .45:.0f}" rx="{r * .7:.0f}" ry="{r * .4:.0f}" fill="#fff" fill-opacity=".14"/>'
			 f'<circle cx="{w / 2}" cy="{h / 2}" r="{r * .86:.0f}" fill="none" '
			 f'stroke="{fg}" stroke-opacity=".5" stroke-width="{r * .03:.1f}" stroke-dasharray="{r * .06:.1f} {r * .05:.1f}"/>'
			 + _text(t, w / 2, h / 2, _fit(t, r * 1.5, r * 1.5, .34), fg))
	elif name == "price_tag":
		n = h / 2
		b = (f'<defs>{lit_defs}</defs><path d="M{n:.0f} 0 H{w - 8} Q{w} 0 {w} 8 V{h - 8} Q{w} {h} {w - 8} {h} H{n:.0f} L0 {h / 2} Z" fill="{lit}"/>'
			 f'<path d="M{n:.0f} 1.5 H{w - 8} Q{w - 1.5} 1.5 {w - 1.5} 8 V{h * .45:.0f} H{n * .1:.0f} Z" fill="#fff" fill-opacity=".14"/>'
			 f'<circle cx="{n * .62:.0f}" cy="{h / 2}" r="{h * .09:.1f}" fill="{fg}" fill-opacity=".9"/>'
			 + _text(t, n + (w - n) / 2, h / 2, _fit(t, w - n, h, .5), fg))
	elif name == "ribbon":
		k = h * .35
		b = (f'<defs>{lit_defs}</defs><path d="M0 0 H{w} L{w - k:.0f} {h / 2} L{w} {h} H0 L{k:.0f} {h / 2} Z" fill="{lit}"/>'
			 f'<path d="M{k * .4:.0f} 1.5 H{w - k * .4:.0f} L{w - k * .9:.0f} {h * .42:.0f} H{k * .9:.0f} Z" fill="#fff" fill-opacity=".13"/>'
			 + _text(t, w / 2, h / 2, _fit(t, w - 2 * k, h, .5), fg))
	elif name == "starburst":
		cx, cy, R = w / 2, h / 2, min(w, h) / 2
		pts = " ".join(f"{cx + (R if k % 2 == 0 else R * .82) * math.cos(k * math.pi / 16):.1f},{cy + (R if k % 2 == 0 else R * .82) * math.sin(k * math.pi / 16):.1f}" for k in range(32))
		b = (f'<defs>{lit_defs}</defs><polygon points="{pts}" fill="{lit}"/>'
			 f'<ellipse cx="{cx:.0f}" cy="{cy - R * .42:.0f}" rx="{R * .62:.0f}" ry="{R * .34:.0f}" fill="#fff" fill-opacity=".13"/>'
			 + _text(t, cx, cy, _fit(t, R * 1.4, R * 1.4, .34), fg))
	elif name == "pill":
		b = (f'<defs>{lit_defs}</defs><rect width="{w}" height="{h}" rx="{h / 2:.0f}" fill="{lit}"/>' + _gloss(0, 0, w, h, h / 2)
			 + _text(t, w / 2, h / 2, _fit(t, w - h, h, .5), fg, 700))
	elif name == "corner_ribbon":
		b = (f'<path d="M{w * .45:.0f} 0 H{w * .75:.0f} L{w} {h * .25:.0f} V{h * .55:.0f} Z" fill="{bg}"/>'
			 + f'<g transform="rotate(45 {w * .72:.0f} {h * .28:.0f})">{_text(t, w * .72, h * .28, _fit(t, w * .42, h * .2, .9), fg)}</g>')
	elif name == "wave_divider":
		b = f'<path d="M0 {h * .5:.0f} Q {w * .125:.0f} 0 {w * .25:.0f} {h * .5:.0f} T {w * .5:.0f} {h * .5:.0f} T {w * .75:.0f} {h * .5:.0f} T {w} {h * .5:.0f}" fill="none" stroke="{bg}" stroke-width="{h * .18:.1f}" stroke-linecap="round"/>'
	elif name == "swash":
		b = f'<path d="M{w * .02:.0f} {h * .7:.0f} C {w * .3:.0f} {h * .15:.0f} {w * .7:.0f} {h * .15:.0f} {w * .98:.0f} {h * .55:.0f}" fill="none" stroke="{bg}" stroke-width="{h * .22:.1f}" stroke-linecap="round"/>'
	elif name == "quote":
		s = min(w, h)
		b = (f'<text x="0" y="{s * .95:.0f}" font-size="{s * 1.5:.0f}" font-family="Georgia, serif" fill="{bg}">&#8220;</text>')
	elif name == "sparkle":
		cx, cy, r = w / 2, h / 2, min(w, h) / 2
		b = f'<path d="M{cx} {cy - r} Q{cx} {cy} {cx + r} {cy} Q{cx} {cy} {cx} {cy + r} Q{cx} {cy} {cx - r} {cy} Q{cx} {cy} {cx} {cy - r} Z" fill="{bg}"/>'
	elif name == "arrow":
		b = f'<path d="M0 {h / 2} H{w * .8:.0f} M{w * .6:.0f} {h * .15:.0f} L{w * .95:.0f} {h / 2} L{w * .6:.0f} {h * .85:.0f}" fill="none" stroke="{bg}" stroke-width="{h * .14:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
	elif name == "dots_line":
		n = max(3, int(w / (h * 2)))
		b = "".join(f'<circle cx="{(k + .5) * w / n:.0f}" cy="{h / 2}" r="{h * .3:.1f}" fill="{bg}"/>' for k in range(n))
	elif name in ("brush_banner", "brush_swipe", "brush_badge"):
		skew = {"brush_banner": -1.5, "brush_swipe": -4, "brush_badge": -6}[name]
		ragged = {"brush_banner": .1, "brush_swipe": .18, "brush_badge": .14}[name]
		b = (f'<g transform="skewY({skew})"><path d="{_brush(w, h * .9, name + t, ragged=ragged)}" transform="translate(0 {h * .05:.0f})" fill="{bg}"/></g>'
			 + _text(t, w / 2, h / 2, _fit(t, w * .86, h, .5), fg, 800))
	elif name == "brush_underline":
		b = f'<path d="{_brush(w, h * .5, "u", ragged=.3)}" transform="translate(0 {h * .25:.0f}) skewY(-1)" fill="{bg}"/>'
	elif name == "date_block":
		# "18 OCT" → the day big, the month under it
		day, _, month = t.partition(" ")
		b = (f'<defs>{lit_defs}</defs><rect width="{w}" height="{h}" rx="{w * .12:.0f}" fill="{lit}"/>' + _gloss(0, 0, w, h, w * .12)
			 + _text(day, w / 2, h * .4, h * .44, fg, 900) + _text(month.upper(), w / 2, h * .78, h * .2, fg, 800))
	elif name == "qr":
		# text: what the code opens (a map link, wa.me, the website). Made here, never by a third-party service.
		b = _qr(t, w, h, palette["dark"])
	elif name == "label_circle":
		# text "icon_book|Reading": a coloured circle with the icon, the label on a soft pill under it
		icon, _, label = t.partition("|")
		icon = icon if icon in ICONS else "icon_check"
		d = min(w, h * .72)
		inner = element(icon, {**palette, tone: fg}, int(d * .5), int(d * .5), tone=tone)
		soft = mix(bg, "#ffffff", .75)
		b = (f'<defs>{lit_defs}</defs><circle cx="{w / 2:.0f}" cy="{d / 2:.0f}" r="{d / 2:.0f}" fill="{lit}"/>'
			 f'<ellipse cx="{w / 2:.0f}" cy="{d * .27:.0f}" rx="{d * .32:.0f}" ry="{d * .17:.0f}" fill="#fff" fill-opacity=".16"/>'
			 f'<g transform="translate({w / 2 - d * .25:.0f} {d * .25:.0f})">{inner}</g>'
			 f'<rect x="{w * .04:.0f}" y="{h * .76:.0f}" width="{w * .92:.0f}" height="{h * .22:.0f}" rx="{h * .11:.0f}" fill="{soft}"/>'
			 + _text(label, w / 2, h * .87, _fit(label, w * .85, h * .22, .7), palette["dark"], 800))
	elif name == "wave_band":
		b = (f'<path d="M0 {h * .3:.0f} C {w * .25:.0f} 0 {w * .5:.0f} {h * .45:.0f} {w * .75:.0f} {h * .2:.0f} S {w} {h * .1:.0f} {w} {h * .1:.0f} '
			 f'V{h} H0 Z" fill="{bg}"/>')
	elif name == "flourish":
		cy = h / 2
		b = (f'<path d="M0 {cy} H{w * .4:.0f} M{w * .6:.0f} {cy} H{w}" stroke="{bg}" stroke-width="{max(1.5, h * .04):.1f}"/>'
			 f'<path d="M{w / 2:.0f} {cy - h * .3:.0f} L{w / 2 + h * .3:.0f} {cy} L{w / 2:.0f} {cy + h * .3:.0f} L{w / 2 - h * .3:.0f} {cy} Z" fill="{bg}"/>'
			 f'<circle cx="{w * .42:.0f}" cy="{cy}" r="{h * .07:.1f}" fill="{bg}"/><circle cx="{w * .58:.0f}" cy="{cy}" r="{h * .07:.1f}" fill="{bg}"/>')
	elif name == "scribble_circle":
		# a loose pen ring around a price ("49/-"); the text in the brand's dark or white by tone
		cx, cy, rx, ry = w / 2, h / 2, w * .46, h * .4
		ring = " ".join(f"{cx + rx * (1 + .04 * math.sin(k * 1.7)) * math.cos(k * math.pi / 18 - .3):.1f},"
						f"{cy + ry * (1 + .05 * math.cos(k * 1.3)) * math.sin(k * math.pi / 18 - .3):.1f}" for k in range(40))
		b = (f'<polyline points="{ring}" fill="none" stroke="{bg}" stroke-width="{max(2, h * .035):.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
			 + _text(t, cx, cy, _fit(t, rx * 1.6, ry * 1.6, .5), bg, 700))
	elif name == "dashed_arrow":
		b = (f'<path d="M{w * .05:.0f} {h * .1:.0f} C{w * .1:.0f} {h * .75:.0f} {w * .6:.0f} {h * .95:.0f} {w * .9:.0f} {h * .72:.0f}" fill="none" '
			 f'stroke="{bg}" stroke-width="{max(2, min(w, h) * .03):.1f}" stroke-dasharray="{min(w, h) * .07:.0f} {min(w, h) * .05:.0f}" stroke-linecap="round"/>'
			 f'<path d="M{w * .78:.0f} {h * .58:.0f} L{w * .93:.0f} {h * .7:.0f} L{w * .8:.0f} {h * .86:.0f}" fill="none" stroke="{bg}" '
			 f'stroke-width="{max(2, min(w, h) * .03):.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
	elif name == "splash":
		b = (f'<path d="M{w * .5:.0f} {h * .2:.0f} C{w * .9:.0f} {h * .1:.0f} {w:.0f} {h * .6:.0f} {w * .6:.0f} {h * .7:.0f} C{w * .3:.0f} {h * .8:.0f} {w * .1:.0f} {h * .5:.0f} {w * .5:.0f} {h * .2:.0f} Z" fill="{bg}"/>'
			 f'<circle cx="{w * .15:.0f}" cy="{h * .3:.0f}" r="{min(w, h) * .07:.1f}" fill="{bg}"/><circle cx="{w * .85:.0f}" cy="{h * .9:.0f}" r="{min(w, h) * .05:.1f}" fill="{bg}"/>')
	elif name == "speech_cloud":
		cx, cy, r = w / 2, h / 2, min(w, h) * .4
		bumps = "".join(f'<circle cx="{cx + r * math.cos(k * math.pi / 5):.0f}" cy="{cy + r * .85 * math.sin(k * math.pi / 5):.0f}" r="{r * .38:.0f}"/>' for k in range(10))
		b = (f'<g fill="none" stroke="{bg}" stroke-width="{max(2, r * .05):.1f}">{bumps}</g>'
			 f'<g fill="{palette["white"] if tone != "dark" else palette["dark"]}">{bumps}<ellipse cx="{cx}" cy="{cy}" rx="{r * 1.02:.0f}" ry="{r * .88:.0f}"/></g>'
			 + _text(t, cx, cy, _fit(t, r * 2.1, r * 1.4, .42), bg, 800))
	elif name == "outline_box":
		sw = max(2, min(w, h) * .012)
		b = f'<rect x="{sw:.0f}" y="{sw:.0f}" width="{w - 2 * sw:.0f}" height="{h - 2 * sw:.0f}" rx="{min(w, h) * .18:.0f}" fill="none" stroke="{bg}" stroke-width="{sw:.1f}"/>'
	elif name == "vertical_label":
		b = (f'<defs>{lit_defs}</defs><rect width="{w}" height="{h}" rx="{w * .14:.0f}" fill="{lit}"/>' + _gloss(0, 0, w, h, w * .14) +
			 f'<g transform="rotate(-90 {w / 2:.0f} {h / 2:.0f})">{_text(t, w / 2, h / 2, _fit(t, h * .9, w, .5), fg, 800)}</g>')
	elif name == "order_bar":
		# a white rounded bar: "Order now" outline pill on the left, then the text (a phone number, "Order on Zomato")
		if contrast(bg, "#ffffff") < 2.6:  # a pale accent would vanish on the white bar
			bg = palette["primary"] if contrast(palette["primary"], "#ffffff") >= 2.6 else palette["dark"]
		b = (f'<rect width="{w}" height="{h}" rx="{h * .2:.0f}" fill="#ffffff"/>'
			 f'<rect x="{h * .2:.0f}" y="{h * .2:.0f}" width="{w * .28:.0f}" height="{h * .6:.0f}" rx="{h * .3:.0f}" fill="none" stroke="{bg}" stroke-width="{h * .04:.1f}"/>'
			 + _text("ORDER NOW", h * .2 + w * .14, h / 2, _fit("ORDER NOW", w * .24, h * .6, .5), bg, 800)
			 + _text(t, w * .32 + (w * .66) / 2, h / 2, _fit(t, w * .62, h, .42), palette["dark"], 800))
	elif name == "hand_underline":
		b = f'<path d="M{w * .02:.0f} {h * .6:.0f} Q{w * .3:.0f} {h * .2:.0f} {w * .55:.0f} {h * .5:.0f} T{w * .98:.0f} {h * .35:.0f}" fill="none" stroke="{bg}" stroke-width="{max(2, h * .16):.1f}" stroke-linecap="round"/>'
	elif name == "icon_tile":
		# a rounded tile in the colour with an icon in its text colour; text = the icon's name (icon_cloud …)
		icon = t if t in ICONS else "icon_check"
		s = min(w, h)
		inner = element(icon, {**palette, tone: fg}, int(s * .56), int(s * .56), tone=tone)
		b = (f'<defs>{lit_defs}</defs><rect width="{s}" height="{s}" rx="{s * .26:.0f}" fill="{lit}"/>' + _gloss(0, 0, s, s, s * .26)
			 + f'<g transform="translate({s * .22:.0f} {s * .22:.0f})">{inner}</g>')
	elif name == "device_laptop":
		# a laptop: anodised lid with a black glass bezel and camera, the screen (x 11.5%, y 6%, 77% × 76% of the lid) where a
		# photo or screenshot goes, then a brushed-aluminium base with its lip and a soft contact shadow
		lid_h = h * .86
		metal = mix(palette["dark"], "#9aa4b2", .55)
		g1, g2, g3 = _gid("lid", metal), _gid("base", metal), _gid("shadow")
		b = (f'<defs><linearGradient id="{g1}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{mix(metal, "#ffffff", .25)}"/>'
			 f'<stop offset="1" stop-color="{mix(metal, "#000000", .25)}"/></linearGradient>'
			 f'<linearGradient id="{g2}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{mix(metal, "#ffffff", .55)}"/>'
			 f'<stop offset=".35" stop-color="{mix(metal, "#ffffff", .2)}"/><stop offset="1" stop-color="{mix(metal, "#000000", .35)}"/></linearGradient>'
			 f'<radialGradient id="{g3}"><stop offset="0" stop-color="#000" stop-opacity=".35"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>'
			 f'<ellipse cx="{w / 2:.0f}" cy="{h:.0f}" rx="{w * .52:.0f}" ry="{h * .05:.0f}" fill="url(#{g3})"/>'
			 f'<rect x="{w * .09:.0f}" y="0" width="{w * .82:.0f}" height="{lid_h:.0f}" rx="{w * .028:.0f}" fill="url(#{g1})"/>'
			 f'<rect x="{w * .096:.0f}" y="{w * .006:.0f}" width="{w * .808:.0f}" height="{lid_h - w * .012:.0f}" rx="{w * .024:.0f}" fill="#07080b"/>'
			 f'<circle cx="{w / 2:.0f}" cy="{lid_h * .03:.0f}" r="{max(1.2, w * .004):.1f}" fill="#1f2937"/>'
			 f'<rect x="{w * .115:.0f}" y="{lid_h * .06:.0f}" width="{w * .77:.0f}" height="{lid_h * .86:.0f}" rx="{w * .006:.0f}" fill="{palette["light"]}"/>'
			 f'<path d="M0 {lid_h:.0f} H{w} L{w * .965:.0f} {h * .985:.0f} Q{w * .96:.0f} {h} {w * .94:.0f} {h} H{w * .06:.0f} Q{w * .04:.0f} {h} {w * .035:.0f} {h * .985:.0f} Z" fill="url(#{g2})"/>'
			 f'<rect x="{w * .42:.0f}" y="{lid_h:.0f}" width="{w * .16:.0f}" height="{h * .028:.0f}" rx="{h * .014:.0f}" fill="{mix(metal, "#000000", .35)}"/>'
			 f'<path d="M{w * .09:.0f} 1 H{w * .91:.0f}" stroke="#fff" stroke-opacity=".35" stroke-width="1"/>')
	elif name == "device_phone":
		# a phone: a metal rim catching the light, black glass, the screen (x 6%, y 6% of the width, 88% wide) where a
		# screenshot goes, a camera pill, side buttons
		rim = mix(palette["dark"], "#9aa4b2", .5)
		g1 = _gid("rim", rim)
		b = (f'<defs><linearGradient id="{g1}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{mix(rim, "#ffffff", .45)}"/>'
			 f'<stop offset=".12" stop-color="{mix(rim, "#000000", .2)}"/><stop offset=".88" stop-color="{mix(rim, "#000000", .2)}"/>'
			 f'<stop offset="1" stop-color="{mix(rim, "#ffffff", .45)}"/></linearGradient></defs>'
			 f'<rect x="{-w * .012:.1f}" y="{h * .2:.0f}" width="{w * .02:.1f}" height="{h * .08:.0f}" rx="{w * .01:.1f}" fill="{rim}"/>'
			 f'<rect x="{w * .992:.1f}" y="{h * .24:.0f}" width="{w * .02:.1f}" height="{h * .12:.0f}" rx="{w * .01:.1f}" fill="{rim}"/>'
			 f'<rect width="{w}" height="{h}" rx="{w * .15:.0f}" fill="url(#{g1})"/>'
			 f'<rect x="{w * .022:.1f}" y="{w * .022:.1f}" width="{w * .956:.1f}" height="{h - w * .044:.1f}" rx="{w * .13:.0f}" fill="#06070a"/>'
			 f'<rect x="{w * .06:.0f}" y="{w * .06:.0f}" width="{w * .88:.0f}" height="{h - w * .12:.0f}" rx="{w * .1:.0f}" fill="{palette["light"]}"/>'
			 f'<rect x="{w * .37:.0f}" y="{w * .085:.0f}" width="{w * .26:.0f}" height="{w * .075:.0f}" rx="{w * .0375:.0f}" fill="#050506"/>'
			 f'<rect x=".75" y=".75" width="{w - 1.5:.1f}" height="{h - 1.5:.1f}" rx="{w * .15:.0f}" fill="none" stroke="#fff" stroke-opacity=".3" stroke-width="1.2"/>')
	elif name == "cta":
		size = _fit(t + "  →", w - h * .6, h, .42)
		b = (f'<defs>{lit_defs}</defs><rect width="{w}" height="{h}" rx="{h / 2:.0f}" fill="{lit}"/>' + _gloss(0, 0, w, h, h / 2)
			 + _text(f"{t}  →" if t else "→", w / 2, h / 2, size, fg, 700))
	elif name.startswith("icon_"):
		s = min(w, h)
		paths = {
			"icon_phone": "M30 18c4 0 6 2 7 6l3 10c1 3 0 5-2 7l-5 4c4 9 11 16 20 20l4-5c2-2 4-3 7-2l10 3c4 1 6 3 6 7v9c0 5-4 8-9 8C47 85 15 53 15 27c0-5 3-9 8-9z",
			"icon_pin": "M50 8c-17 0-30 13-30 30 0 22 30 54 30 54s30-32 30-54C80 21 67 8 50 8zm0 42a12 12 0 1 1 0-24 12 12 0 0 1 0 24z",
			"icon_clock": "M50 10a40 40 0 1 0 0 80 40 40 0 0 0 0-80zm0 10a30 30 0 1 1 0 60 30 30 0 0 1 0-60zm-4 10v24l20 12 4-7-16-10V30z",
			"icon_check": "M38 70L16 48l7-7 15 15 39-39 7 7z",
			"icon_truck": "M8 28h52v36H8zM60 40h18l14 14v10H60zM24 78a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm52 0a8 8 0 1 0 0-16 8 8 0 0 0 0 16z",
			"icon_star": "M50 8l12 28 30 3-23 20 7 30-26-16-26 16 7-30L8 39l30-3z",
			"icon_cart": "M22 34h56l-6 54H28zM36 34v-6a14 14 0 0 1 28 0v6h-8v-6a6 6 0 0 0-12 0v6z",
			"icon_calendar": "M18 22h64v64H18zm0 18h64M34 12v18M66 12v18",
			"icon_cloud": "M30 76a18 18 0 0 1-2-36 24 24 0 0 1 46-6 20 20 0 0 1 2 42z",
			"icon_shield": "M50 8l34 12v24c0 22-14 40-34 48C30 84 16 66 16 44V20z",
			"icon_gear": "M44 8h12l2 12 10 4 10-7 8 8-7 10 4 10 12 2v12l-12 2-4 10 7 10-8 8-10-7-10 4-2 12H44l-2-12-10-4-10 7-8-8 7-10-4-10-12-2V44l12-2 4-10-7-10 8-8 10 7 10-4zm6 28a14 14 0 1 0 0 28 14 14 0 0 0 0-28z",
			"icon_chart": "M14 86h74M22 70V54M40 70V40M58 70V48M76 70V24",
			"icon_rocket": "M50 8c16 10 22 30 16 52H34C28 38 34 18 50 8zM34 60l-12 16 16-4M66 60l12 16-16-4M44 72h12l-6 16z",
			"icon_team": "M50 18a12 12 0 1 1 0 24 12 12 0 0 1 0-24zM26 30a9 9 0 1 1 0 18 9 9 0 0 1 0-18zm48 0a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM30 80c0-14 9-26 20-26s20 12 20 26zM8 76c0-10 7-18 16-18 4 0 7 1 10 4-4 4-6 9-7 14zm84 0c0-10-7-18-16-18-4 0-7 1-10 4 4 4 6 9 7 14z",
			"icon_mail": "M12 24h76v52H12zm0 4l38 28 38-28",
			"icon_globe": "M50 10a40 40 0 1 0 0 80 40 40 0 0 0 0-80zM10 50h80M50 10c-14 14-14 66 0 80M50 10c14 14 14 66 0 80",
			"icon_lock": "M28 44h44v40H28zM36 44V32a14 14 0 0 1 28 0v12",
			"icon_ai": "M24 24h52v52H24zM36 12v12M50 12v12M64 12v12M36 76v12M50 76v12M64 76v12M12 36h12M12 50h12M12 64h12M76 36h12M76 50h12M76 64h12",
			"icon_code": "M34 26L12 50l22 24M66 26l22 24-22 24M56 18L44 82",
			"icon_sync": "M78 42A30 30 0 0 0 24 34M22 58a30 30 0 0 0 54 8M78 20v22H56M22 80V58h22",
			"icon_book": "M12 22c14-4 26-2 38 6v58c-12-8-24-10-38-6zm76 0c-14-4-26-2-38 6v58c12-8 24-10 38-6z",
			"icon_home": "M50 12L8 48h12v40h22V64h16v24h22V48h12z",
			"icon_drop": "M50 8C38 28 22 44 22 62a28 28 0 0 0 56 0C78 44 62 28 50 8z",
			"icon_bolt": "M58 6L18 56h26l-6 38 44-54H54z",
			"icon_cross": "M42 8h16v24h24v16H58v44H42V48H18V32h24z",
			"icon_lamp": "M50 10c8 10 10 18 4 26h-8c-6-8-4-16 4-26zM18 52h64c-4 14-16 22-32 22S22 66 18 52zM40 78h20v10H40z",
			"icon_music": "M38 18l46-10v52a12 12 0 1 1-8-11V24L46 30v40a12 12 0 1 1-8-11z",
			"icon_heart": "M50 86S10 62 10 34a20 20 0 0 1 40-6 20 20 0 0 1 40 6c0 28-40 52-40 52z",
		}
		d = paths.get(name, paths["icon_check"])
		stroke = name in ("icon_calendar", "icon_chart", "icon_mail", "icon_globe", "icon_lock", "icon_ai", "icon_code", "icon_sync")
		b = (f'<g transform="scale({s / 100:.3f})"><path d="{d}" '
			 + (f'fill="none" stroke="{bg}" stroke-width="8" stroke-linejoin="round"' if stroke else f'fill="{bg}" fill-rule="evenodd"') + "/></g>")
	else:
		return element("pill", palette, w, h, text=t, tone=tone)
	return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" overflow="visible">{b}</svg>'
