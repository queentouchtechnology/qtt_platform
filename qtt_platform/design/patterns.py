"""
Background patterns (PROJ-0011 B) — SVG, drawn only in the business's palette (base.palette), any size.

pattern(name, palette, width, height, base=..., seed=...) → a whole <svg>. `base` is what the pattern sits on:
  light    the brand's light colour, soft tints of its main and accent colours on top (text in the brand's dark)
  primary  the main colour, white and accent at low strength on top (text in on_primary)
  dark     the brand's dark colour, the main and accent colours on top (text in white)
The same name and seed always draw the same picture, so a series stays consistent.
"""

import math
import random

from qtt_platform.design.base import mix as mix_hex

BASES = ("light", "primary", "dark")
# name: (label, good for) — the library the template builder and QTT Admin show
PATTERNS = {
	"dots": ("Dots", "any"), "grid": ("Grid", "tech, offices"), "stripes": ("Diagonal stripes", "offers, sale"),
	"chevron": ("Chevron", "fashion, retail"), "waves": ("Waves", "health, beauty, travel"),
	"blobs": ("Soft shapes", "beauty, kids, cafés"), "corner_circles": ("Corner circles", "any"),
	"confetti": ("Confetti", "celebrations, launches"), "triangles": ("Triangles", "fitness, automotive"),
	"hexagons": ("Hexagons", "tech, manufacturing"), "plus": ("Plus signs", "health, clinics"),
	"rings": ("Rings", "jewellery, events"), "arches": ("Arches", "interiors, real estate"),
	"zigzag": ("Zigzag", "kids, food"), "checker": ("Checks", "restaurants, retail"),
	"diamonds": ("Diamonds", "jewellery, fashion"), "sunburst": ("Sunburst", "festivals, big news"),
	"kolam": ("Kolam dots", "festivals, sweets, homes"), "mandala": ("Rosette", "festivals, weddings"),
	"bubbles": ("Bubbles", "cleaning, drinks, kids"), "split": ("Two-tone split", "announcements"),
	"corner_arcs": ("Corner arcs", "any"), "frame_lines": ("Frame lines", "premium, quotes"),
	"half_circles": ("Half circles", "cafés, bakeries"), "stars": ("Stars", "festivals, kids, offers"),
	"leaves": ("Leaves", "organic, grocery, spa"),
	# technology (QTT's own posts: light with a blue sweep, or dark with glow and circuit lines)
	"sweep": ("Diagonal sweep", "technology, launches"), "dot_corners": ("Dot-grid corners", "technology, any"),
	"circuit": ("Circuit lines", "technology, AI"), "glow_rings": ("Glow rings", "technology, AI, launches"),
	# local market (local-post-references.md)
	"stage_glow": ("Stage lights", "events, worship, concerts"), "rays": ("Light rays", "worship, festivals, greetings"),
	"corner_blobs": ("Corner blobs", "coaching, kids, cafés"),
	# modern agency style (agency-post-references in docs/design)
	"shards": ("Angular shards", "sales, fashion"), "organic_curve": ("Organic curve", "agencies, consultants"),
	"wave_split": ("Wave split", "agencies, services"), "spotlight": ("Spotlight", "products, food, offers"),
	"chalkboard": ("Chalkboard", "food, cafés, menus"), "big_circles": ("Big circles", "agencies, youth, offers"),
}


def _tones(p: dict, base: str) -> tuple[str, list[tuple[str, float]]]:
	"""(the background fill, [(motif colour, strength)…]) for the base."""
	if base == "primary":
		return p["primary"], [("#ffffff", 0.14), (p["accent"], 0.55), ("#ffffff", 0.08)]
	if base == "dark":
		return p["dark"], [(p["primary"], 0.34), (p["accent"], 0.45), ("#ffffff", 0.06)]
	return p["light"], [(p["primary"], 0.16), (p["accent"], 0.28), (p["primary"], 0.08)]


def _svg(w: int, h: int, bg: str | None, body: str, defs: str = "") -> str:
	return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
			+ (f"<defs>{defs}</defs>" if defs else "") + (f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else "") + f"{body}</svg>")


def _tile(name: str, size: int, inner: str, w: int, h: int) -> tuple[str, str]:
	return (f'<pattern id="{name}" width="{size}" height="{size}" patternUnits="userSpaceOnUse">{inner}</pattern>',
			f'<rect width="{w}" height="{h}" fill="url(#{name})"/>')


def pattern(name: str, palette: dict, width: int, height: int, *, base: str = "light", seed: int = 1, transparent: bool = False) -> str:
	"""One pattern as a whole SVG (unknown name → dots; unknown base → light). transparent: only the motif, no background
	fill — to lay one pattern over another (a sweep with dot-grid corners)."""
	name = name if name in PATTERNS else "dots"
	base = base if base in BASES else "light"
	bg, tones = _tones(palette, base)
	(c1, o1), (c2, o2), (c3, o3) = tones
	w, h = int(width), int(height)
	u = max(w, h) / 1080  # 1 at post size
	rnd = random.Random(f"{name}:{seed}")
	f = lambda c, o: f'fill="{c}" fill-opacity="{o}"'  # noqa: E731
	st = lambda c, o, sw: f'fill="none" stroke="{c}" stroke-opacity="{o}" stroke-width="{sw:.1f}"'  # noqa: E731
	body, defs = "", ""

	if name == "dots":
		s = 36 * u
		defs, body = _tile("p", round(s), f'<circle cx="{s / 2:.1f}" cy="{s / 2:.1f}" r="{5.5 * u:.1f}" {f(c1, min(1, o1 * 2.2))}/>', w, h)
	elif name == "grid":
		s = 54 * u
		defs, body = _tile("p", round(s), f'<path d="M {s:.1f} 0 L 0 0 0 {s:.1f}" {st(c1, o1 * 1.5, 1.5 * u)}/>', w, h)
	elif name == "stripes":
		s = 48 * u
		defs = (f'<pattern id="p" width="{s:.1f}" height="{s:.1f}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
				f'<rect width="{s / 2:.1f}" height="{s:.1f}" {f(c1, o1)}/></pattern>')
		body = f'<rect width="{w}" height="{h}" fill="url(#p)"/>'
	elif name == "chevron":
		s = 60 * u
		defs, body = _tile("p", round(s), f'<path d="M0 {s * .75:.1f} L{s / 2:.1f} {s * .25:.1f} L{s:.1f} {s * .75:.1f}" {st(c1, o1 * 1.6, 5 * u)}/>', w, h)
	elif name == "waves":
		for i, (c, o) in enumerate(((c1, o1 * 1.4), (c2, o2), (c1, o1))):
			y0 = h * (0.68 + i * 0.1)
			a = 40 * u * (1 + i * 0.3)
			d = f"M0 {y0:.0f} " + " ".join(f"Q {x + 135 * u:.0f} {y0 + (a if (x // (270 * u)) % 2 else -a):.0f} {x + 270 * u:.0f} {y0:.0f}"
											for x in [k * 270 * u for k in range(int(w / (270 * u)) + 2)]) + f" L {w} {h} L 0 {h} Z"
			body += f'<path d="{d}" {f(c, o)}/>'
	elif name == "blobs":
		for c, o, (cx, cy, r) in ((c1, o1 * 1.5, (0.1, 0.12, 0.32)), (c2, o2, (0.92, 0.85, 0.28)), (c3, o3 * 2, (0.85, 0.08, 0.14))):
			pts = []
			for k in range(8):
				ang = k / 8 * 2 * math.pi
				rr = r * max(w, h) * (0.8 + rnd.random() * 0.35)
				pts.append((cx * w + rr * math.cos(ang), cy * h + rr * math.sin(ang)))
			d = f"M {pts[0][0]:.0f} {pts[0][1]:.0f} " + " ".join(
				f"Q {pts[k][0]:.0f} {pts[k][1]:.0f} {(pts[k][0] + pts[(k + 1) % 8][0]) / 2:.0f} {(pts[k][1] + pts[(k + 1) % 8][1]) / 2:.0f}" for k in range(8)) + " Z"
			body += f'<path d="{d}" {f(c, o)}/>'
	elif name == "corner_circles":
		body = (f'<circle cx="{w}" cy="0" r="{0.42 * max(w, h):.0f}" {f(c1, o1 * 1.4)}/>'
				f'<circle cx="{w}" cy="0" r="{0.27 * max(w, h):.0f}" {f(c2, o2)}/>'
				f'<circle cx="0" cy="{h}" r="{0.3 * max(w, h):.0f}" {f(c1, o1)}/>')
	elif name == "confetti":
		for _ in range(int(70 * w * h / 1080 ** 2) + 20):
			x, y, a = rnd.random() * w, rnd.random() * h, rnd.random() * 180
			c, o = (c1, o1 * 2.2) if rnd.random() < 0.5 else (c2, o2 * 1.2)
			body += f'<rect x="{x:.0f}" y="{y:.0f}" width="{14 * u:.0f}" height="{6 * u:.0f}" rx="{2 * u:.0f}" transform="rotate({a:.0f} {x:.0f} {y:.0f})" {f(c, o)}/>'
	elif name == "triangles":
		s = 90 * u
		defs, body = _tile("p", round(s), f'<path d="M0 {s:.1f} L{s / 2:.1f} 0 L{s:.1f} {s:.1f} Z" {f(c1, o1)}/>', w, h)
	elif name == "hexagons":
		r = 34 * u
		hx, hy = r * math.sqrt(3), r * 1.5
		hexp = lambda cx, cy: "M" + " L".join(f"{cx + r * math.cos(math.pi / 6 + k * math.pi / 3):.1f} {cy + r * math.sin(math.pi / 6 + k * math.pi / 3):.1f}" for k in range(6)) + " Z"  # noqa: E731
		for row in range(int(h / hy) + 2):
			for col in range(int(w / hx) + 2):
				body += f'<path d="{hexp(col * hx + (hx / 2 if row % 2 else 0), row * hy)}" {st(c1, o1 * 1.6, 2 * u)}/>'
	elif name == "plus":
		s = 64 * u
		a, t = 9 * u, 3 * u
		defs, body = _tile("p", round(s), f'<path d="M{s / 2 - a:.1f} {s / 2:.1f} H{s / 2 + a:.1f} M{s / 2:.1f} {s / 2 - a:.1f} V{s / 2 + a:.1f}" {st(c1, o1 * 2, t)}/>', w, h)
	elif name == "rings":
		for _ in range(9):
			x, y, r = rnd.random() * w, rnd.random() * h, (40 + rnd.random() * 120) * u
			c, o = (c1, o1 * 1.8) if rnd.random() < 0.6 else (c2, o2)
			body += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" {st(c, o, 6 * u)}/>'
	elif name == "arches":
		for k in range(5):
			r = (180 + k * 110) * u
			body += f'<path d="M {w / 2 - r:.0f} {h} A {r:.0f} {r:.0f} 0 0 1 {w / 2 + r:.0f} {h}" {st(c1 if k % 2 else c2, (o1 if k % 2 else o2) * 1.3, 18 * u)}/>'
	elif name == "zigzag":
		s = 40 * u
		defs, body = _tile("p", round(s), f'<path d="M0 {s * .6:.1f} L{s / 4:.1f} {s * .4:.1f} L{s / 2:.1f} {s * .6:.1f} L{s * .75:.1f} {s * .4:.1f} L{s:.1f} {s * .6:.1f}" {st(c1, o1 * 2, 3 * u)}/>', w, h)
	elif name == "checker":
		s = 70 * u
		defs, body = _tile("p", round(s), f'<rect width="{s / 2:.1f}" height="{s / 2:.1f}" {f(c1, o1)}/><rect x="{s / 2:.1f}" y="{s / 2:.1f}" width="{s / 2:.1f}" height="{s / 2:.1f}" {f(c1, o1)}/>', w, h)
	elif name == "diamonds":
		s = 56 * u
		defs, body = _tile("p", round(s), f'<path d="M{s / 2:.1f} {s * .15:.1f} L{s * .85:.1f} {s / 2:.1f} L{s / 2:.1f} {s * .85:.1f} L{s * .15:.1f} {s / 2:.1f} Z" {st(c1, o1 * 1.8, 2 * u)}/>', w, h)
	elif name == "sunburst":
		cx, cy, R = w / 2, h / 2, max(w, h)
		for k in range(24):
			a1, a2 = k * 2 * math.pi / 24, (k + 0.5) * 2 * math.pi / 24
			if k % 2 == 0:
				body += f'<path d="M{cx:.0f} {cy:.0f} L{cx + R * math.cos(a1):.0f} {cy + R * math.sin(a1):.0f} L{cx + R * math.cos(a2):.0f} {cy + R * math.sin(a2):.0f} Z" {f(c1, o1)}/>'
	elif name == "kolam":
		s = 60 * u
		inner = (f'<circle cx="{s / 2:.1f}" cy="{s / 2:.1f}" r="{3.5 * u:.1f}" {f(c1, o1 * 2.5)}/>'
				 f'<path d="M{s / 2:.1f} {s * .15:.1f} Q{s * .85:.1f} {s * .15:.1f} {s * .85:.1f} {s / 2:.1f} Q{s * .85:.1f} {s * .85:.1f} {s / 2:.1f} {s * .85:.1f} '
				 f'Q{s * .15:.1f} {s * .85:.1f} {s * .15:.1f} {s / 2:.1f} Q{s * .15:.1f} {s * .15:.1f} {s / 2:.1f} {s * .15:.1f} Z" {st(c2, o2 * 1.4, 2 * u)}/>')
		defs, body = _tile("p", round(s), inner, w, h)
	elif name == "mandala":
		cx, cy = w * 0.85, h * 0.18
		for ring, n, r, c, o in ((0, 12, 260, c1, o1 * 1.6), (1, 18, 380, c2, o2), (2, 24, 500, c1, o1)):
			for k in range(n):
				a = k * 2 * math.pi / n
				x, y = cx + r * u * math.cos(a), cy + r * u * math.sin(a)
				body += f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{(28 + ring * 6) * u:.0f}" ry="{(12 + ring * 3) * u:.0f}" transform="rotate({math.degrees(a):.0f} {x:.0f} {y:.0f})" {f(c, o)}/>'
		body += f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{150 * u:.0f}" {st(c2, o2 * 1.5, 8 * u)}/>'
	elif name == "bubbles":
		for _ in range(16):
			x, y, r = rnd.random() * w, rnd.random() * h, (12 + rnd.random() * 70) * u
			body += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" {f(c1 if rnd.random() < .6 else c2, (o1 if rnd.random() < .6 else o2) * 1.3)}/>'
	elif name == "split":
		body = f'<path d="M0 {h * .62:.0f} L{w} {h * .38:.0f} L{w} {h} L0 {h} Z" {f(c1, o1 * 2.4)}/><path d="M0 {h * .78:.0f} L{w} {h * .56:.0f} L{w} {h * .6:.0f} L0 {h * .82:.0f} Z" {f(c2, o2 * 1.5)}/>'
	elif name == "corner_arcs":
		for k in range(4):
			r = (120 + k * 60) * u
			body += f'<path d="M0 {r:.0f} A {r:.0f} {r:.0f} 0 0 0 {r:.0f} 0" {st(c1, o1 * 2, 10 * u)}/>'
			body += f'<path d="M{w - r:.0f} {h} A {r:.0f} {r:.0f} 0 0 1 {w} {h - r:.0f}" {st(c2, o2 * 1.2, 10 * u)}/>'
	elif name == "frame_lines":
		m1, m2 = 36 * u, 54 * u
		body = (f'<rect x="{m1:.0f}" y="{m1:.0f}" width="{w - 2 * m1:.0f}" height="{h - 2 * m1:.0f}" {st(c1, o1 * 3, 3 * u)}/>'
				f'<rect x="{m2:.0f}" y="{m2:.0f}" width="{w - 2 * m2:.0f}" height="{h - 2 * m2:.0f}" {st(c2, o2 * 1.5, 1.5 * u)}/>')
	elif name == "half_circles":
		s = 80 * u
		defs, body = _tile("p", round(s), f'<path d="M0 {s:.1f} A {s / 2:.1f} {s / 2:.1f} 0 0 1 {s:.1f} {s:.1f} Z" {f(c1, o1)}/>', w, h)
	elif name == "stars":
		def star(x, y, r):
			return "M" + " L".join(f"{x + (r if k % 2 == 0 else r * .45) * math.cos(-math.pi / 2 + k * math.pi / 5):.1f} "
								   f"{y + (r if k % 2 == 0 else r * .45) * math.sin(-math.pi / 2 + k * math.pi / 5):.1f}" for k in range(10)) + " Z"
		for _ in range(22):
			x, y, r = rnd.random() * w, rnd.random() * h, (8 + rnd.random() * 26) * u
			body += f'<path d="{star(x, y, r)}" {f(c2 if rnd.random() < .5 else c1, (o2 if rnd.random() < .5 else o1) * 1.6)}/>'
	elif name == "sweep":
		# a bold diagonal band from the top right, with a thin echo — the main colour at full strength on light
		band = palette["primary"] if base == "light" else c1
		ob = 1 if base == "light" else min(1, o1 * 3)
		body = (f'<path d="M{w * .55:.0f} {h} L{w} {h * .38:.0f} L{w} {h * .52:.0f} L{w * .66:.0f} {h} Z" fill="{band}" fill-opacity="{ob}"/>'
				f'<path d="M{w * .8:.0f} 0 L{w} 0 L{w} {h * .12:.0f} L{w * .72:.0f} {h * .5:.0f} L{w * .7:.0f} {h * .47:.0f} Z" fill="{band}" fill-opacity="{ob * .85:.2f}"/>'
				f'<path d="M{w * .42:.0f} {h} L{w} {h * .22:.0f}" {st(c2, o2 * 1.4, 3 * u)}/>')
	elif name == "dot_corners":
		s, r = 22 * u, 3 * u
		for (x0, y0) in ((w - 8 * s - 30 * u, 30 * u), (30 * u, h - 6 * s - 30 * u)):
			for i in range(8 if x0 > w / 2 else 6):
				for j in range(6):
					body += f'<circle cx="{x0 + i * s:.0f}" cy="{y0 + j * s:.0f}" r="{r:.1f}" {f(c1, min(1, o1 * 3))}/>'
	elif name == "circuit":
		for _ in range(14):
			x, y = rnd.random() * w, rnd.random() * h
			path, px, py = f"M{x:.0f} {y:.0f}", x, y
			for _k in range(3):
				if rnd.random() < .5:
					px += (rnd.random() - .5) * 360 * u
				else:
					py += (rnd.random() - .5) * 360 * u
				path += f" L{px:.0f} {py:.0f}"
			c, o = (c1, o1 * 2) if rnd.random() < .6 else (c2, o2)
			body += f'<path d="{path}" {st(c, o, 2.5 * u)}/><circle cx="{px:.0f}" cy="{py:.0f}" r="{6 * u:.0f}" {f(c, min(1, o * 1.6))}/>'
	elif name == "glow_rings":
		cx, cy = w * .62, h * .62
		defs = (f'<radialGradient id="p" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{c1}" stop-opacity="{min(1, o1 * 2.4):.2f}"/>'
				f'<stop offset="1" stop-color="{c1}" stop-opacity="0"/></radialGradient>')
		body = f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{w * .5:.0f}" ry="{h * .3:.0f}" fill="url(#p)"/>'
		for k in range(4):
			body += f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{(160 + k * 95) * u:.0f}" ry="{(55 + k * 33) * u:.0f}" {st(c2 if k % 2 else c1, (o2 if k % 2 else o1) * 1.8, 3 * u)}/>'
	elif name == "stage_glow":
		# a dark stage: two coloured spotlights from the top and a row of small lights
		defs = "".join(
			f'<radialGradient id="p{k}" cx="50%" cy="0%" r="80%"><stop offset="0" stop-color="{c}" stop-opacity="{o:.2f}"/>'
			f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>'
			for k, (c, o) in enumerate(((palette["primary"], .85), (palette["accent"], .6))))
		body = (f'<rect width="{w}" height="{h}" fill="{palette["dark"]}"/>'
				f'<ellipse cx="{w * .3:.0f}" cy="0" rx="{w * .55:.0f}" ry="{h * .9:.0f}" fill="url(#p0)"/>'
				f'<ellipse cx="{w * .75:.0f}" cy="0" rx="{w * .5:.0f}" ry="{h * .8:.0f}" fill="url(#p1)"/>'
				+ "".join(f'<circle cx="{w * (k + .5) / 9:.0f}" cy="{h * .04:.0f}" r="{5 * u:.0f}" fill="#ffffff" fill-opacity=".7"/>' for k in range(9)))
		defs = defs.replace('id="p0"', 'id="p"')
		body = body.replace("url(#p0)", "url(#p)")
		defs = defs.replace('id="p1"', 'id="pB"')
		body = body.replace("url(#p1)", "url(#pB)")
		pidb = f"qpb-{name}-{seed}-{w}x{h}"
		defs, body = defs.replace('id="pB"', f'id="{pidb}"'), body.replace("url(#pB)", f"url(#{pidb})")
	elif name == "rays":
		cx, cy, R = w * .75, -h * .05, max(w, h) * 1.4
		for k in range(16):
			a1 = math.radians(40 + k * 7)
			a2 = a1 + math.radians(3)
			body += f'<path d="M{cx:.0f} {cy:.0f} L{cx + R * math.cos(a1):.0f} {cy + R * math.sin(a1):.0f} L{cx + R * math.cos(a2):.0f} {cy + R * math.sin(a2):.0f} Z" {f("#ffffff" if base != "light" else c2, .09 if base != "light" else o2)}/>'
	elif name == "corner_blobs":
		body = (f'<path d="M0 0 H{w * .32:.0f} C{w * .28:.0f} {h * .1:.0f} {w * .12:.0f} {h * .2:.0f} 0 {h * .26:.0f} Z" {f(palette["accent"], .9 if base == "light" else .6)}/>'
				f'<path d="M{w} 0 V{h * .2:.0f} C{w * .9:.0f} {h * .16:.0f} {w * .82:.0f} {h * .06:.0f} {w * .8:.0f} 0 Z" {f(c1, min(1, o1 * 3))}/>'
				f'<path d="M{w} {h} H{w * .7:.0f} C{w * .78:.0f} {h * .9:.0f} {w * .9:.0f} {h * .86:.0f} {w} {h * .8:.0f} Z" {f(palette["accent"], .9 if base == "light" else .6)}/>')
	elif name == "shards":
		cols = [(c1, min(1, o1 * 3.5)), (c2, min(1, o2 * 2.2)), (palette["primary_soft"] if base == "light" else c1, .9 if base == "light" else o1 * 2)]
		polys = [((0, 0), (.42, 0), (0, .36)), ((.7, 0), (1, 0), (1, .3)), ((1, .62), (1, 1), (.62, 1)), ((0, .7), (.3, 1), (0, 1)),
				 ((.55, 0), (.78, 0), (.6, .14)), ((1, .4), (1, .55), (.9, .5))]
		for k, poly in enumerate(polys):
			c, o = cols[k % 3]
			body += f'<path d="M' + " L".join(f"{x * w:.0f} {y * h:.0f}" for x, y in poly) + f' Z" {f(c, o)}/>'
	elif name == "organic_curve":
		col = palette["primary"] if base == "light" else c1
		body = (f'<path d="M{w * .62:.0f} 0 C{w * .5:.0f} {h * .3:.0f} {w * .98:.0f} {h * .45:.0f} {w * .78:.0f} {h * .72:.0f} '
				f'C{w * .66:.0f} {h * .9:.0f} {w * .72:.0f} {h:.0f} {w * .72:.0f} {h} H{w} V0 Z" fill="{col}" fill-opacity="{1 if base == "light" else min(1, o1 * 3):.2f}"/>')
	elif name == "wave_split":
		col = palette["primary_deep"] if base == "light" else c1
		body = f'<path d="M0 0 H{w} V{h * .52:.0f} C{w * .7:.0f} {h * .7:.0f} {w * .45:.0f} {h * .3:.0f} 0 {h * .55:.0f} Z" fill="{col}" fill-opacity="{1 if base == "light" else min(1, o1 * 3):.2f}"/>'
	elif name == "spotlight":
		defs = (f'<radialGradient id="p" cx="50%" cy="45%" r="65%"><stop offset="0" stop-color="{mix_hex(bg, "#ffffff", .35)}"/>'
				f'<stop offset="1" stop-color="{bg}"/></radialGradient>')
		body = f'<rect width="{w}" height="{h}" fill="url(#p)"/>'
	elif name == "chalkboard":
		defs = ('<filter id="p" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="3"/>'
				'<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .09 0"/></filter>')
		body = f'<rect width="{w}" height="{h}" fill="{palette["dark"] if base != "primary" else bg}"/><rect width="{w}" height="{h}" filter="url(#p)"/>'
	elif name == "big_circles":
		body = (f'<circle cx="{w * .22:.0f}" cy="{h * .28:.0f}" r="{w * .26:.0f}" {f(palette["accent"], .95)}/>'
				f'<circle cx="{w * .9:.0f}" cy="{h * .88:.0f}" r="{w * .12:.0f}" {f(palette["accent"], .95)}/>'
				f'<circle cx="{w * .06:.0f}" cy="{h * .48:.0f}" r="{w * .02:.0f}" {f(palette["accent"], .95)}/>')
	elif name == "leaves":
		for _ in range(14):
			x, y, s2, a = rnd.random() * w, rnd.random() * h, (40 + rnd.random() * 60) * u, rnd.random() * 360
			body += (f'<path d="M{x:.0f} {y:.0f} q {s2 / 2:.0f} {-s2 / 2:.0f} {s2:.0f} 0 q {-s2 / 2:.0f} {s2 / 2:.0f} {-s2:.0f} 0 Z" '
					 f'transform="rotate({a:.0f} {x:.0f} {y:.0f})" {f(c1 if rnd.random() < .6 else c2, (o1 if rnd.random() < .6 else o2) * 1.6)}/>')
	if defs:  # each picture its own id — many patterns on one page must not share one
		pid = f"qp-{name}-{base}-{seed}-{w}x{h}"
		defs, body = defs.replace('id="p"', f'id="{pid}"'), body.replace("url(#p)", f"url(#{pid})")
		body = body.replace('fill="url(#p)"', f'fill="url(#{pid})"')
	return _svg(w, h, None if transparent else bg, body, defs)


def text_colour(palette: dict, base: str) -> str:
	"""What text on this base is written in."""
	return {"primary": palette["on_primary"], "dark": "#ffffff"}.get(base, palette["dark"])
