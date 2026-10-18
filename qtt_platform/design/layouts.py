"""
Post layouts (PROJ-0011 C) — the engine the template library renders with. Pure: content in, HTML out.

A layout is a function (ctx, variant) → (body_html, css), written at 1080 px wide; the page scales it to the format
(square, portrait, story…), whose height the layout fills with flex boxes, never fixed tops — so a long headline pushes
what follows instead of covering it. Text marked data-fit shrinks until it fits its box (a small script runs in the
page after the fonts load; the renderer waits for window.qttReady).

Content (the slots a template fills, from the business knowledge or the owner):
  business, logo (a file name beside the page), phone, website, email, address, tagline
  headline (*word* = the highlighted word), kicker (a small line above it), subline, cta
  items [{icon, title, text}] — benefit / spec / question rows; list (plain lines)
  price, price_label, badge (a short word: NEW, 20% OFF — only from the owner), date ("18 Oct"), time, place
  person, role, years, quote, qr (a link), photos [file names]
Everything is escaped; nothing is invented — an empty slot is simply left out.
"""

import html
import re
from dataclasses import dataclass, field

from qtt_platform.design import base, elements as E, patterns as P

DESIGN_W = 1080
LOOKS = ("light", "dark", "brand")

FIT_SCRIPT = (
	"<script>(async()=>{try{await document.fonts.ready}catch(e){}"
	# too big = taller than the box's max-height (big capitals spill a few px past a tight line-height, so allow 6) or
	# wider than the box (a long word / a nowrap line)
	"document.querySelectorAll('[data-fit]').forEach(el=>{const cs=getComputedStyle(el);let s=parseFloat(cs.fontSize),m=s*.42;"
	"const mh=cs.maxHeight==='none'?el.clientHeight:parseFloat(cs.maxHeight);"
	"while((el.scrollHeight>mh+6||el.scrollWidth>el.clientWidth+2)&&s>m){s-=1.5;el.style.fontSize=s+'px'}});"
	"window.qttReady=true})()</script>"
)


def esc(v) -> str:
	return html.escape(str(v or ""))


def marked(v) -> str:
	"""'Transform your *business*' → escaped, the starred words in <em>."""
	return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", esc(v)).replace("\n", "<br>")


@dataclass
class Ctx:
	"""What a layout draws with: the brand (palette, fonts), the format, the look and the content."""
	palette: dict
	fonts: dict
	height: int  # at 1080 wide
	look: str
	content: dict
	photos: list = field(default_factory=list)  # file names beside the page

	@property
	def w(self) -> int:
		return DESIGN_W

	@property
	def h(self) -> int:
		return self.height

	@property
	def tall(self) -> bool:
		return self.height >= 1500

	@property
	def wide(self) -> bool:
		return self.height < 900

	@property
	def p(self) -> dict:
		return self.palette

	@property
	def bg(self) -> str:
		return {"dark": self.p["dark"], "brand": self.p["primary"]}.get(self.look, self.p["light"])

	@property
	def ink(self) -> str:
		return {"dark": "#ffffff", "brand": self.p["on_primary"]}.get(self.look, self.p["dark"])

	@property
	def soft(self) -> str:
		return "rgba(255,255,255,.78)" if self.look in ("dark", "brand") and self.ink == "#ffffff" else (
			"rgba(17,24,39,.72)" if self.look != "light" else base.mix(self.p["dark"], self.p["light"], .3))

	@property
	def hl(self) -> str:
		"""The highlight colour for starred words: the main colour, or the accent when the background is the main colour."""
		if self.look == "brand":
			return self.p["accent"] if base.contrast(self.p["accent"], self.p["primary"]) >= 2 else self.ink
		c = self.p["primary"]
		return c if base.contrast(c, self.bg) >= 2.6 else (self.p["accent"] if base.contrast(self.p["accent"], self.bg) >= 2.6 else self.ink)

	def has(self, key: str) -> bool:
		v = self.content.get(key)
		return bool(v.strip()) if isinstance(v, str) else bool(v)

	def t(self, key: str) -> str:
		return esc(self.content.get(key))

	def m(self, key: str) -> str:
		return marked(self.content.get(key))

	def photo(self, i: int = 0) -> str | None:
		return self.photos[i % len(self.photos)] if self.photos else None

	@property
	def cut(self) -> bool:
		"""The first photo is a cut-out (its background removed): it sits on the design without a frame."""
		return bool(self.content.get("cutout"))

	def photo_style(self, frame: str = "") -> str:
		"""The CSS for the main photo: its frame — or, for a cut-out, its own shape with a soft shadow (inline, so it wins)."""
		if self.cut:
			return ("background-size:contain;background-repeat:no-repeat;background-position:center bottom;border-radius:0;border:0;"
					"box-shadow:none;-webkit-mask-image:none;mask-image:none;clip-path:none;filter:drop-shadow(0 26px 30px rgba(0,0,0,.35))")
		return base.FRAMES.get(frame, frame) if frame else ""

	def pattern(self, name: str, *, base_: str | None = None, transparent: bool = False, seed: int = 1) -> str:
		b = base_ or {"dark": "dark", "brand": "primary"}.get(self.look, "light")
		return P.pattern(name, self.p, self.w, self.h, base=b, seed=seed, transparent=transparent)

	def el(self, name: str, w: int, h: int, *, text: str = "", tone: str = "accent", palette: dict | None = None) -> str:
		return E.element(name, palette or self.p, w, h, text=text, tone=tone)

	def logo(self, height: int = 90, *, light: bool | None = None) -> str:
		"""The logo as it is (never recoloured); without one, the business name in the heading face."""
		logo = self.content.get("logo")
		if logo:
			return f'<img class="logo" src="{esc(logo)}" style="height:{height}px;max-width:{height * 3.6:.0f}px;object-fit:contain">'
		colour = self.ink if light is None else ("#ffffff" if light else self.p["dark"])
		return f'<div class="logo-name" style="font-size:{height * .42:.0f}px;color:{colour}">{self.t("business")}</div>'

	def contact_bits(self) -> list[tuple[str, str]]:
		return [(icon, self.content.get(k)) for icon, k in (("icon_phone", "phone"), ("icon_globe", "website"), ("icon_mail", "email"),
															 ("icon_pin", "address")) if self.has(k)]


def common_css(x: Ctx) -> str:
	return (
		f".post{{position:relative;width:{x.w}px;height:{x.h}px;overflow:hidden;background:{x.bg};color:{x.ink}}}"
		".layer{position:absolute;inset:0}.layer svg{display:block}"
		".h{font-family:var(--font-heading)}em{font-style:normal}"
		".logo-name{font-family:var(--font-heading);font-weight:800;line-height:1.05}"
		".fit{overflow:hidden}[data-fit]{flex:none}"  # fitted text keeps its size; the rows below give way instead
		".ph{background-size:cover;background-position:center}"
	)


def page(body: str, css: str, x: Ctx, out_w: int, out_h: int) -> str:
	"""The whole page at the format's real size (the 1080-wide design scaled to it)."""
	from qtt_platform.design.sheet import page as wrap

	scale = out_w / DESIGN_W
	inner = (f'<div class="post" style="transform:scale({scale:.5f});transform-origin:0 0">{body}</div>{FIT_SCRIPT}')
	return wrap(inner, out_w, out_h, x.fonts, extra_css=common_css(x) + css)
