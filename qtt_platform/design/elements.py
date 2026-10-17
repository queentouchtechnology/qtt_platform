"""
Design elements (PROJ-0011 B): badges, price tags, ribbons, dividers, icons — SVG in the business's palette.

element(name, palette, width, height, text="", tone=...) → a whole <svg> the templates place over a background. Text on
an element is the template's own words (a price written in the knowledge, "New", the business's phone) — an element
never invents an offer. tone picks the element's colour: accent (default), primary or dark. No other company's logo
is ever drawn (no WhatsApp, Instagram or payment marks) — icons are plain shapes.
"""

import html
import math

from qtt_platform.design.base import mix

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
ICONS = [n for n in ELEMENTS if n.startswith("icon_") and n != "icon_tile"]
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


def element(name: str, palette: dict, width: int, height: int, *, text: str = "", tone: str = "accent") -> str:
	w, h = int(width), int(height)
	bg, fg = _colours(palette, tone)
	t = str(text or "")
	b = ""
	if name == "badge":
		r = min(w, h) / 2
		b = (f'<circle cx="{w / 2}" cy="{h / 2}" r="{r:.0f}" fill="{bg}"/><circle cx="{w / 2}" cy="{h / 2}" r="{r * .86:.0f}" fill="none" '
			 f'stroke="{fg}" stroke-opacity=".5" stroke-width="{r * .03:.1f}" stroke-dasharray="{r * .06:.1f} {r * .05:.1f}"/>'
			 + _text(t, w / 2, h / 2, _fit(t, r * 1.5, r * 1.5, .34), fg))
	elif name == "price_tag":
		n = h / 2
		b = (f'<path d="M{n:.0f} 0 H{w - 8} Q{w} 0 {w} 8 V{h - 8} Q{w} {h} {w - 8} {h} H{n:.0f} L0 {h / 2} Z" fill="{bg}"/>'
			 f'<circle cx="{n * .62:.0f}" cy="{h / 2}" r="{h * .09:.1f}" fill="{fg}" fill-opacity=".9"/>'
			 + _text(t, n + (w - n) / 2, h / 2, _fit(t, w - n, h, .5), fg))
	elif name == "ribbon":
		k = h * .35
		b = (f'<path d="M0 0 H{w} L{w - k:.0f} {h / 2} L{w} {h} H0 L{k:.0f} {h / 2} Z" fill="{bg}"/>'
			 + _text(t, w / 2, h / 2, _fit(t, w - 2 * k, h, .5), fg))
	elif name == "starburst":
		cx, cy, R = w / 2, h / 2, min(w, h) / 2
		pts = " ".join(f"{cx + (R if k % 2 == 0 else R * .82) * math.cos(k * math.pi / 16):.1f},{cy + (R if k % 2 == 0 else R * .82) * math.sin(k * math.pi / 16):.1f}" for k in range(32))
		b = f'<polygon points="{pts}" fill="{bg}"/>' + _text(t, cx, cy, _fit(t, R * 1.4, R * 1.4, .34), fg)
	elif name == "pill":
		b = f'<rect width="{w}" height="{h}" rx="{h / 2:.0f}" fill="{bg}"/>' + _text(t, w / 2, h / 2, _fit(t, w - h, h, .5), fg, 700)
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
	elif name == "icon_tile":
		# a rounded tile in the colour with an icon in its text colour; text = the icon's name (icon_cloud …)
		icon = t if t in ICONS else "icon_check"
		s = min(w, h)
		inner = element(icon, {**palette, tone: fg}, int(s * .56), int(s * .56), tone=tone)
		b = (f'<rect width="{s}" height="{s}" rx="{s * .26:.0f}" fill="{bg}"/>'
			 f'<g transform="translate({s * .22:.0f} {s * .22:.0f})">{inner}</g>')
	elif name == "device_laptop":
		frame = mix(palette["dark"], "#64748b", .45)  # a slate frame — seen on light and on dark posts
		# a plain laptop frame; the screen (x 11.5%, y 6%, 77% × 76% of the lid) is where a photo or screenshot goes
		lid_h = h * .86
		b = (f'<rect x="{w * .09:.0f}" y="0" width="{w * .82:.0f}" height="{lid_h:.0f}" rx="{w * .025:.0f}" fill="{frame}"/>'
			 f'<rect x="{w * .115:.0f}" y="{lid_h * .06:.0f}" width="{w * .77:.0f}" height="{lid_h * .86:.0f}" rx="{w * .006:.0f}" fill="{palette["light"]}"/>'
			 f'<path d="M0 {lid_h:.0f} H{w} L{w * .96:.0f} {h} H{w * .04:.0f} Z" fill="{palette["primary_deep"]}"/>'
			 f'<rect x="{w * .42:.0f}" y="{lid_h:.0f}" width="{w * .16:.0f}" height="{h * .03:.0f}" rx="{h * .015:.0f}" fill="{palette["dark"]}"/>')
	elif name == "device_phone":
		b = (f'<rect width="{w}" height="{h}" rx="{w * .14:.0f}" fill="{mix(palette["dark"], "#64748b", .45)}"/>'
			 f'<rect x="{w * .06:.0f}" y="{w * .06:.0f}" width="{w * .88:.0f}" height="{h - w * .12:.0f}" rx="{w * .1:.0f}" fill="{palette["light"]}"/>'
			 f'<rect x="{w * .38:.0f}" y="{w * .09:.0f}" width="{w * .24:.0f}" height="{w * .05:.0f}" rx="{w * .025:.0f}" fill="{palette["dark"]}"/>')
	elif name == "cta":
		size = _fit(t + "  →", w - h * .6, h, .42)
		b = (f'<rect width="{w}" height="{h}" rx="{h / 2:.0f}" fill="{bg}"/>'
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
		}
		d = paths.get(name, paths["icon_check"])
		stroke = name in ("icon_calendar", "icon_chart", "icon_mail", "icon_globe", "icon_lock", "icon_ai", "icon_code", "icon_sync")
		b = (f'<g transform="scale({s / 100:.3f})"><path d="{d}" '
			 + (f'fill="none" stroke="{bg}" stroke-width="8" stroke-linejoin="round"' if stroke else f'fill="{bg}" fill-rule="evenodd"') + "/></g>")
	else:
		return element("pill", palette, w, h, text=t, tone=tone)
	return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" overflow="visible">{b}</svg>'
