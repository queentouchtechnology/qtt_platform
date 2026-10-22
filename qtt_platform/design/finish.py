"""
The finish (PROJ-0012 S2, premium and cinematic) — the light and texture over a whole design, the same for every layout,
drawn only with the business's own palette:

  clean      nothing added (the flat look)
  premium    soft pools of light in the brand colours, a gentle vignette, fine film grain, photos graded a little
             richer, headlines lifted off the background
  cinematic  premium, and: a light beam, a few floating specks of light, an anamorphic flare, a deeper vignette,
             stronger grading — a creative direction for dark and brand looks, set per template

The layers lie over the design as full-size boxes that never take a touch (pointer-events:none) and that Studio's Move and
resize never counts as pieces (anything covering most of the post isn't one), so saved arrangements keep their numbers.
Pure (no Frappe); tests/test_design.py.
"""

import hashlib
import random

from qtt_platform.design import base

FINISHES = ("clean", "premium", "cinematic")

# fine monochrome noise (an SVG turbulence tile), blended over the design
_GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='260' height='260'>"
		  "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/>"
		  "<feColorMatrix values='0 0 0 0 .5 0 0 0 0 .5 0 0 0 0 .5 0 0 0 .9 0'/></filter>"
		  "<rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")")


def default_for(look: str) -> str:
	"""Every design gets the restrained premium finish; the cinematic one (beam, flare, specks of light) is a creative
	direction of its own, chosen per template (variant "finish": "cinematic") — effects only where they serve the design."""
	return "premium"


def _seed(*parts) -> int:
	return int(hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def _rgba(hex_: str, a: float) -> str:
	h = base.hex6(hex_) or "#000000"
	return f"rgba({int(h[1:3], 16)},{int(h[3:5], 16)},{int(h[5:7], 16)},{a:.3f})"


def _bokeh(p: dict, w: int, h: int, seed: int, count: int) -> str:
	"""Specks of light, out of focus — one SVG (one layer, never a movable piece)."""
	rnd = random.Random(seed)
	light = base.mix(p["accent"], "#ffffff", .45)
	glow = base.mix(p["primary"], "#ffffff", .35)
	dots = []
	for _ in range(count):
		r = rnd.choice((3, 4, 6, 9, 14, 22, 34))
		x, y = rnd.uniform(0, w), rnd.uniform(0, h)
		col = rnd.choice((light, glow, "#ffffff"))
		a = rnd.uniform(.10, .38) if r > 12 else rnd.uniform(.25, .7)
		dots.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{col}" fill-opacity="{a:.2f}" filter="url(#b{min(r // 8, 3)})"/>')
	blur = "".join(f'<filter id="b{i}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="{(1.2, 3, 6, 10)[i]}"/></filter>' for i in range(4))
	return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs>{blur}</defs>{"".join(dots)}</svg>'


def layers(finish: str, p: dict, look: str, w: int, h: int, key: str = "") -> tuple[str, str]:
	"""(html laid over the post's content, css) for a finish; ('', '') for clean."""
	if finish not in FINISHES or finish == "clean":
		return "", ""
	dark = look in ("dark", "brand")
	cine = finish == "cinematic"
	seed = _seed(key, p.get("primary"), look, w, h)
	rnd = random.Random(seed)
	lx, ly = rnd.choice((22, 30, 70, 78)), rnd.choice((18, 26))
	if dark:  # coloured light thrown onto a dark ground
		pools = (f"radial-gradient(60% 46% at {lx}% {ly}%,{_rgba(p['accent'], .55)},transparent 70%),"
				 f"radial-gradient(70% 55% at {100 - lx}% {100 - ly}%,{_rgba(p['primary'], .6)},transparent 72%)")
		blend, op = "screen", (.85 if cine else .6)
	else:  # on a light ground: tinted shade in two corners, like light falling across paper
		pools = (f"radial-gradient(55% 45% at {100 - lx}% {100 - ly}%,{_rgba(base.mix(p['primary'], '#ffffff', .55), .55)},transparent 72%),"
				 f"radial-gradient(45% 38% at {lx}% {ly}%,{_rgba(base.mix(p['accent'], '#ffffff', .5), .45)},transparent 70%)")
		blend, op = "multiply", (.8 if cine else .65)
	html = [f'<div class="fx fx-pools"></div>']
	css = [".fx{position:absolute;inset:0;pointer-events:none}",
		   f".fx-pools{{background:{pools};mix-blend-mode:{blend};opacity:{op}}}"]
	if cine:
		bx = rnd.choice((58, 64, 72))
		html.append('<div class="fx fx-beam"></div>')
		css.append(f".fx-beam{{background:linear-gradient({rnd.choice((112, 118, 124))}deg,transparent {bx - 18}%,rgba(255,255,255,.16) {bx}%,transparent {bx + 14}%);"
				   "mix-blend-mode:screen;filter:blur(6px)}")
		html.append('<div class="fx fx-flare"></div>')
		fy = rnd.choice((24, 32, 68))
		css.append(f".fx-flare{{background:radial-gradient(50% 1.6% at 50% {fy}%,{_rgba(base.mix(p['accent'], '#ffffff', .5), .55)},transparent 100%);"
				   "mix-blend-mode:screen;opacity:.7}")
		html.append(f'<div class="fx fx-bokeh">{_bokeh(p, w, h, seed, 12 if dark else 6)}</div>')
		css.append(".fx-bokeh svg{display:block;mix-blend-mode:screen}")
	vig = (.62 if cine else .38) if dark else (.16 if cine else .1)
	html.append('<div class="fx fx-vignette"></div>')
	css.append(f".fx-vignette{{background:radial-gradient(120% 95% at 50% 45%,transparent 52%,rgba(0,0,0,{vig}) 100%)}}")
	html.append('<div class="fx fx-grain"></div>')
	css.append(f".fx-grain{{background:{_GRAIN};background-size:260px;mix-blend-mode:overlay;opacity:{.16 if cine else .1}}}")
	# richer photos, headlines lifted off the background (drop-shadow works with gold / gradient text too)
	css.append(f".post .ph{{filter:saturate({1.14 if cine else 1.07}) contrast({1.08 if cine else 1.04})}}"
			   + (f".post h1{{filter:drop-shadow(0 8px {28 if cine else 20}px rgba(0,0,0,{.45 if cine else .3}))}}" if dark else
				  ".post h1{filter:drop-shadow(0 6px 18px rgba(0,0,0,.10))}"))
	return "".join(html), "".join(css)
