"""
More showcase directions (PROJ-0012 S10, second set) — twenty compositions on the same parts as showcase.py (the CSS
phone with the owner's real screenshot, headline, points, chips, number, steps, button), so each is a different
arrangement, not a recolour. Registered into showcase.DIRECTIONS / LAYOUTS; the catalogue gives each a library template.

Same rules: content in, HTML out; flex / grid at 1080 wide; square, portrait, story and the wide sizes; nothing written
on the screenshot, nothing invented (a direction that needs a number, steps, chips or problems is offered only when the
owner gave them).
"""

import math

from qtt_platform.design import base
from qtt_platform.design.layouts import Ctx, esc
from qtt_platform.design.showcase import (_backdrop, _chip_css, _chips, _cta, _feats, _feats_css, _head, _head_css, _phone,
										  _phone_css, _side, _sizes, _top)

DIRECTIONS = {
	"tilt_premium": ("Premium 3D phone", "A strongly angled phone on a reflective floor", {}),
	"screen_pop": ("Screen pops out", "Your screen breaking out of the phone frame", {}),
	"ui_orbit": ("Points in orbit", "Your points as cards circling the phone", {"items": 3}),
	"big_type": ("Oversized headline", "A huge headline with a small phone", {}),
	"full_phone": ("Full-height phone", "The phone fills the poster, bold words behind it", {}),
	"split_benefits": ("Split screen", "Your points on one side, the screen on the other", {"items": 2}),
	"diagonal_layers": ("Diagonal layers", "A diagonal band, the phone and stacked cards", {"items": 2}),
	"glass_cards": ("Glass cards", "Frosted-glass cards over soft colour", {"items": 2}),
	"swiss_grid": ("Swiss grid", "A strict grid, big type, thin rules", {}),
	"cinematic": ("Cinematic light", "One beam of light, deep shadows", {}),
	"product_stage": ("On stage", "The phone standing on a lit stage", {}),
	"connected_chips": ("Connected chips", "Your points joined to the screen by lines", {"items": 3}),
	"stat_badge": ("Number badge", "A big round badge with your number, and your points", {"stat": 1}),
	"timeline_steps": ("Three-step guide", "Your steps down a line, the app beside them", {"steps": 3}),
	"problem_solution_ui": ("Problem and solution", "The problems you name, then your app as the answer", {"problems": 2}),
	"globe_reach": ("Global reach", "A globe behind the phone, your languages or places around it", {"list": 3}),
	"pill_rows": ("Language pills", "Rows of your languages or categories sliding behind the phone", {"list": 4}),
	"open_book": ("Open book", "The phone on an open book — for learning, faith and reading", {}),
	"color_blocks": ("Colour blocks", "Bold geometric shapes in your colours", {}),
	"magazine_cover": ("Magazine cover", "Your name as a masthead, cover lines and the phone as the cover", {"items": 2}),
}


# ---- shared ---------------------------------------------------------------------------------------------------------
def _frame(x: Ctx, text: str, visual: str, *, side: bool | None = None, tflex: float = 1.1, vflex: float = 1, pad: int | None = None,
		   center: bool = False, reverse: bool = False) -> tuple[str, str]:
	"""Text and a visual: side by side (wide, square) or one above the other (portrait, story)."""
	hs, p = _sizes(x)
	pad = p if pad is None else pad
	side = _side(x) if side is None else side
	order = (visual + text) if reverse else (text + visual)
	html = f'<div class="fw {"fr" if side else "fc"}">{order}</div>'
	css = (f".fw{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:{20 if x.wide else 30}px}}.fr{{flex-direction:row;align-items:stretch}}"
		   f".fc{{flex-direction:column;{'align-items:center;' if center else ''}}}.ft2{{flex:{tflex};display:flex;flex-direction:column;justify-content:center;"
		   f"gap:{14 if x.wide else 22}px;min-width:0}}.fc .ft2{{flex:none}}.fc .fv{{width:100%}}.fv{{flex:{vflex};min-height:0;min-width:0;display:flex;justify-content:center;"
		   f"align-items:center;position:relative}}.fv.pw{{container-type:size}}.top,.cta{{flex:none}}.fc .cta{{align-self:{'center' if center else 'flex-start'}}}")
	return html, css


def _text(x: Ctx, *, align: str = "left", size: int | None = None, upper: bool = False, light: bool | None = None, extra: str = "",
		  cta_tone: str = "accent") -> str:
	hs, _p = _sizes(x)
	return f'<div class="ft2">{_top(x, light=light)}{_head(x, size or hs, align=align, upper=upper)}{extra}{_cta(x, tone=cta_tone)}</div>'


def _items(x: Ctx, limit: int = 4) -> list[dict]:
	return [i for i in (x.content.get("items") or []) if str(i.get("title") or "").strip()][:limit]


def _txt(it: dict) -> str:
	return f"<span>{esc(it.get('text'))}</span>" if it.get("text") else ""


def _ink_on(bg: str, x: Ctx) -> str:
	return base.on(bg, dark=x.p["dark"])


def _hl_on(bg: str, x: Ctx) -> str:
	"""The highlight that reads on this background: the accent, else the main colour, else plain ink."""
	for c in (x.p["accent"], x.p["primary"]):
		if base.contrast(c, bg) >= 2.6:
			return c
	return _ink_on(bg, x)


# ---- 1. premium 3D phone on a reflective floor ----------------------------------------------------------------------
def tilt_premium(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["light"] if x.look == "light" else x.p["dark"]
	ink = _ink_on(bg, x)
	visual = f'<div class="fv pw stagep">{_phone(x, cls="t3")}</div>'
	html, css = _frame(x, _text(x, light=ink == "#ffffff"), visual, side=_side(x), vflex=1.1, reverse=not x.wide and not x.tall)
	floor = (f'<div class="layer" style="background:linear-gradient(180deg,{bg} 0,{bg} 62%,{base.mix(bg, x.p["primary"], .12)} 62%,{base.mix(bg, x.p["primary"], .22)} 100%)"></div>')
	css += (_phone_css(x) + _head_css(x, ink=ink, hl=_hl_on(bg, x), kick=_hl_on(bg, x)) + f".post{{background:{bg}}}.stagep{{perspective:1600px}}"
			".phone.t3{height:min(92cqh,calc(92cqw / .49));transform:rotateY(-32deg) rotateX(14deg) rotateZ(6deg);"
			"-webkit-box-reflect:below 6px linear-gradient(transparent 70%,rgba(255,255,255,.28));"
			"box-shadow:-60px 80px 90px rgba(0,0,0,.35),0 0 0 2px rgba(255,255,255,.08) inset}")
	return floor + html, css


# ---- 2. the screen pops out of its frame ----------------------------------------------------------------------------
def screen_pop(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["dark"]
	shot = x.photos[0] if x.photos else None
	pop = f'<img class="popshot" src="{esc(shot)}">' if shot else ""
	visual = f'<div class="fv pw"><div class="popwrap" data-piece>{_phone(x, cls="ghost")}{pop}</div></div>'
	html, css = _frame(x, _text(x, light=True, align="left" if _side(x) else "center"), visual, center=True)
	glow = f'<div class="layer" style="background:radial-gradient(circle at 60% 55%,{base.mix(x.p["primary"], bg, .3)} 0,transparent 55%)"></div>'
	css += (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.8)", hl=_hl_on(bg, x), kick=_hl_on(bg, x)) + f".post{{background:{bg}}}"
			".popwrap{position:relative;aspect-ratio:.49;height:min(86cqh,calc(86cqw / .49))}.popwrap .phone{height:100%}"
			".phone.ghost .scr{background:#15161d}.phone.ghost .shot{opacity:.18;filter:blur(2px)}"
			".popshot{position:absolute;left:4%;top:-6%;width:104%;height:auto;max-height:104%;object-fit:cover;object-position:top;border-radius:34px;"
			"transform:rotate(-4deg) translate(6%,-2%);box-shadow:0 60px 90px rgba(0,0,0,.55),0 0 0 3px rgba(255,255,255,.9)}")
	return glow + html, css


# ---- 3. points in orbit around the phone ----------------------------------------------------------------------------
def ui_orbit(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.bg
	items = _items(x, 4)
	spots = [("2%", "14%"), ("62%", "30%"), ("0%", "62%"), ("60%", "78%")]
	cards = "".join(f'<div class="ob" style="left:{l};top:{t}">{x.el("icon_tile", 48, 48, text=it.get("icon") or "icon_check", tone="primary")}'
					f'<b>{esc(it.get("title"))}</b></div>' for it, (l, t) in zip(items, spots))
	visual = (f'<div class="fv orbit"><div class="ring"></div><div class="pw ph2">{_phone(x)}</div>{cards}</div>')
	html, css = _frame(x, _text(x, align="center" if not _side(x) else "left"), visual, center=True, vflex=1.3)
	css += (_phone_css(x) + _head_css(x) + f".post{{background:{bg}}}"
			f".orbit{{width:100%}}.ring{{position:absolute;inset:6% 8%;border:3px dashed {base.mix(x.p['primary'], bg, .55)};border-radius:50%}}"
			".ph2{position:absolute;inset:8% 22%;display:flex;justify-content:center;align-items:center;container-type:size}"
			f".ob{{position:absolute;display:flex;align-items:center;gap:12px;background:#fff;border-radius:999px;padding:10px 22px 10px 10px;"
			f"box-shadow:0 18px 40px rgba(0,0,0,.18);z-index:2;max-width:46%}}.ob svg{{flex:none}}"
			f".ob b{{font:700 {19 if x.wide else 23}px/1.15 var(--font-heading);color:{x.p['dark']}}}")
	return html, css


# ---- 4. oversized headline, small phone -----------------------------------------------------------------------------
def big_type(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["primary"] if x.look == "brand" else x.bg
	ink = _ink_on(bg, x)
	size = 92 if x.wide else (190 if x.tall else 150)
	kick = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	sub = f'<p class="sub">{x.m("subline")}</p>' if x.has("subline") else ""
	body = (f'<div class="bt">{_top(x, light=ink == "#ffffff")}{kick}<h1 class="fit" data-fit style="font-size:{size}px">{x.m("headline")}</h1>'
			f'<div class="btlow"><div class="btl">{sub}{_cta(x, tone="dark" if x.look != "dark" else "accent")}</div><div class="pw small">{_phone(x)}</div></div></div>')
	css = (_phone_css(x) + _head_css(x, ink=ink, hl=_hl_on(bg, x), kick=_hl_on(bg, x), soft=base.mix(ink, bg, .25)) + f".post{{background:{bg}}}"
		   f".bt{{position:absolute;inset:0;padding:{40 if x.wide else 64}px;display:flex;flex-direction:column;gap:{12 if x.wide else 20}px;color:{ink}}}"
		   f".bt h1{{font-family:var(--font-heading);font-weight:900;line-height:.92;letter-spacing:-3px;margin:0;max-height:{int(size * 3.1)}px;"
		   f"{'width:68%' if x.wide else ''}}}.bt h1 em{{color:{_hl_on(bg, x)}}}"
		   ".btlow{flex:1;min-height:0;display:flex;align-items:flex-end;gap:30px}.btl{flex:1;display:flex;flex-direction:column;gap:20px;padding-bottom:10px}"
		   f".pw.small{{flex:none;width:{30 if x.wide else 34}%;height:100%;container-type:size;display:flex;justify-content:flex-end;align-items:flex-end}}"
		   + (".bt h1{position:relative;z-index:1}.btlow{position:absolute;right:40px;top:40px;bottom:40px;width:30%}.btl{display:none}"
			  ".btlow .pw.small{width:100%}" if x.wide else "")
		   + (f".bt h1 em{{color:{x.p['dark']};background:{x.p['accent']};padding:0 .12em;box-decoration-break:clone;-webkit-box-decoration-break:clone}}"
			  if base.contrast(x.p["accent"], bg) < 2.6 and _hl_on(bg, x) == ink else ""))
	return body, css


# ---- 5. full-height phone with bold words behind --------------------------------------------------------------------
def full_phone(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["dark"]
	word = (x.content.get("headline") or "").replace("*", "").split()
	big = " ".join(word[:3]) if word else ""
	back = f'<div class="bgword">{esc(big)}</div>'
	head = _head(x, 52 if x.wide else (78 if x.tall else 60), align="center")
	body = (f'{back}<div class="fp">{_top(x, light=True)}<div class="pw fpp">{_phone(x)}</div>{head}{_cta(x)}</div>')
	if x.wide:
		body = (f'{back}<div class="fp fpw"><div class="fptext">{_top(x, light=True)}{_head(x, 52)}{_cta(x)}</div><div class="pw fpp">{_phone(x)}</div></div>')
	css = (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.8)", hl=_hl_on(bg, x), kick=_hl_on(bg, x)) + f".post{{background:{bg}}}"
		   f".bgword{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;font:900 {200 if x.tall else 170}px/.86 var(--font-heading);"
		   f"text-transform:uppercase;color:transparent;-webkit-text-stroke:3px {base.mix(x.p['primary'], bg, .35)};letter-spacing:-4px;padding:0 20px;word-break:break-word}}"
		   f".fp{{position:absolute;inset:0;padding:{36 if x.wide else 50}px;display:flex;flex-direction:column;align-items:center;gap:20px}}.fp .top{{align-self:flex-start}}"
		   ".fpp{flex:1;min-height:0;width:100%;display:flex;justify-content:center;container-type:size}"
		   ".fpw{flex-direction:row;align-items:stretch}.fptext{flex:1;display:flex;flex-direction:column;justify-content:center;gap:16px}.fpw .fpp{flex:.8}"
		   ".fp .phone{box-shadow:0 0 0 2px rgba(255,255,255,.08) inset,0 0 120px " + base.mix(x.p["primary"], bg, .3) + "}")
	return body, css


# ---- 6. split screen: points on one side, the screen on the other ---------------------------------------------------
def split_benefits(x: Ctx, v: dict) -> tuple[str, str]:
	a, b = x.p["primary"], x.p["light"]
	ink_a = _ink_on(a, x)
	side = x.wide or x.h <= 1350
	pts = "".join(f'<div class="sp">{x.el("icon_tile", 54, 54, text=it.get("icon") or "icon_check", tone="accent")}<div><b>{esc(it.get("title"))}</b>{_txt(it)}</div></div>'
				  for it in _items(x, 4 if x.tall else 3))
	left = f'<div class="sa">{_top(x, light=ink_a == "#ffffff")}{_head(x, _sizes(x)[0] - 6)}<div class="sps">{pts}</div>{_cta(x, tone="accent")}</div>'
	right = f'<div class="sb pw">{_phone(x)}</div>'
	body = f'<div class="split {"sr" if side else "sc"}">{left}{right}</div>'
	pad = 40 if x.wide else 56
	css = (_phone_css(x) + _head_css(x, ink=ink_a, hl=_hl_on(a, x), kick=_hl_on(a, x), soft=base.mix(ink_a, a, .2)) + f".post{{background:{b}}}"
		   f".split{{position:absolute;inset:0;display:flex}}.sr{{flex-direction:row}}.sc{{flex-direction:column}}"
		   f".sa{{background:{a};padding:{pad}px;display:flex;flex-direction:column;justify-content:center;gap:{14 if x.wide else 22}px}}.sr .sa{{flex:1.15}}.sc .sa{{flex:none}}"
		   f".sb{{flex:1;min-height:0;padding:{pad}px;display:flex;justify-content:center;align-items:center;container-type:size;"
		   f"background:radial-gradient(circle at 50% 50%,{base.mix(a, b, .8)} 0,{b} 60%)}}"
		   f".sp{{display:flex;align-items:center;gap:16px;margin-bottom:{10 if x.wide else 16}px}}.sp svg{{flex:none}}"
		   f".sp b{{display:block;font:700 {20 if x.wide else 25}px/1.2 var(--font-heading);color:{ink_a}}}.sp span{{display:block;font:400 18px/1.3 var(--font-body);color:{ink_a};opacity:.8}}"
		   f".sa .top,.sa .cta{{flex:none}}")
	return body, css


# ---- 7. diagonal band, tilted phone, stacked cards ------------------------------------------------------------------
def diagonal_layers(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["light"]
	band = x.p["primary"]
	cards = "".join(f'<div class="dc" style="--i:{k}"><b>{esc(it.get("title"))}</b>{_txt(it)}</div>' for k, it in enumerate(_items(x, 3)))
	visual = f'<div class="fv pw dv">{_phone(x, cls="dg")}<div class="dcs">{cards}</div></div>'
	html, css = _frame(x, _text(x), visual, vflex=1.2)
	layer = f'<div class="layer" style="background:linear-gradient(115deg,{bg} 0 46%,{band} 46% 72%,{x.p["dark"]} 72%)"></div>'
	if not _side(x):
		layer = f'<div class="layer" style="background:linear-gradient(160deg,{bg} 0 38%,{band} 38% 70%,{x.p["dark"]} 70%)"></div>'
	css += (_phone_css(x) + _head_css(x, ink=x.p["dark"], hl=_hl_on(bg, x)) + f".post{{background:{bg}}}"
			".dv{justify-content:flex-start}.phone.dg{height:min(94cqh,calc(94cqw / .49));transform:rotate(-12deg);margin-left:6%}"
			".dcs{position:absolute;right:0;top:12%;display:flex;flex-direction:column;gap:18px;width:52%}"
			f".dc{{background:#fff;border-radius:20px;padding:18px 22px;box-shadow:0 22px 40px rgba(0,0,0,.25);transform:rotate(-12deg) translateX(calc(var(--i) * 26px));"
			f"border-left:8px solid {x.p['accent']}}}.dc b{{display:block;font:800 {19 if x.wide else 24}px/1.15 var(--font-heading);color:{x.p['dark']}}}"
			f".dc span{{display:block;font:400 17px/1.3 var(--font-body);color:{base.mix(x.p['dark'], '#ffffff', .35)}}}")
	return layer + html, css


# ---- 8. glass cards ------------------------------------------------------------------------------------------------------
def glass_cards(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["dark"]
	blobs = (f'<div class="layer" style="background:radial-gradient(circle at 15% 20%,{x.p["primary"]} 0,transparent 38%),'
			 f'radial-gradient(circle at 85% 30%,{x.p["accent"]} 0,transparent 32%),radial-gradient(circle at 60% 90%,{x.p["secondary"]} 0,transparent 40%);filter:blur(30px)"></div>')
	cards = "".join(f'<div class="gc">{x.el("icon_tile", 50, 50, text=it.get("icon") or "icon_check", tone="accent")}<div><b>{esc(it.get("title"))}</b>{_txt(it)}</div></div>'
					for it in _items(x, 3))
	visual = f'<div class="fv gv"><div class="pw gp">{_phone(x)}</div><div class="gcs">{cards}</div></div>'
	html, css = _frame(x, _text(x, light=True, align="left" if _side(x) else "center"), visual, center=True, vflex=1.25)
	css += (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.82)", hl="#ffffff", kick="rgba(255,255,255,.85)") + f".post{{background:{bg}}}"
			".gv{width:100%}.gp{position:absolute;inset:0 0 0 36%;display:flex;justify-content:center;container-type:size}"
			".gcs{position:absolute;left:0;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:16px;width:48%;z-index:2}"
			".gc{display:flex;align-items:center;gap:14px;padding:18px 20px;border-radius:24px;background:rgba(255,255,255,.14);"
			"border:1.5px solid rgba(255,255,255,.35);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 20px 40px rgba(0,0,0,.25)}"
			f".gc svg{{flex:none}}.gc b{{display:block;font:700 {19 if x.wide else 24}px/1.15 var(--font-heading);color:#fff}}"
			".gc span{display:block;font:400 17px/1.3 var(--font-body);color:rgba(255,255,255,.8)}")
	return blobs + html, css


# ---- 9. Swiss grid ---------------------------------------------------------------------------------------------------
def swiss_grid(x: Ctx, v: dict) -> tuple[str, str]:
	bg = "#f4f3ef" if x.look != "dark" else x.p["dark"]
	ink = _ink_on(bg, x)
	red = x.p["accent"] if base.contrast(x.p["accent"], bg) > 2 else x.p["primary"]
	idx = "".join(f'<div class="sg"><i>{k + 1:02d}</i><b>{esc(it.get("title"))}</b></div>' for k, it in enumerate(_items(x, 3)))
	size = 64 if x.wide else (120 if x.tall else 96)
	head = f'<h1 class="fit" data-fit style="font-size:{size}px">{x.m("headline")}</h1>'
	kick = f'<div class="sk2">{x.t("kicker")}</div>' if x.has("kicker") else ""
	cols = "1.3fr 1fr" if _side(x) else "1fr"
	body = (f'<div class="sw" style="grid-template-columns:{cols}"><div class="sgt">{_top(x, light=ink == "#ffffff")}{kick}{head}'
			f'{"<p class=sub2>" + x.m("subline") + "</p>" if x.has("subline") else ""}<div class="sgi">{idx}</div>{_cta(x, tone="dark")}</div>'
			f'<div class="pw sgp">{_phone(x)}</div></div><div class="sq"></div>')
	css = (_phone_css(x) + f".post{{background:{bg};color:{ink}}}"
		   f".sw{{position:absolute;inset:0;padding:{40 if x.wide else 64}px;display:grid;gap:40px;{'grid-template-rows:auto 1fr;' if not _side(x) else ''}}}"
		   f".sgt{{display:flex;flex-direction:column;gap:{12 if x.wide else 18}px;justify-content:flex-end}}"
		   f".sk2{{font:700 {16 if x.wide else 22}px var(--font-body);text-transform:uppercase;letter-spacing:4px;border-top:4px solid {ink};padding-top:12px}}"
		   f".sgt h1{{font-family:var(--font-heading);font-weight:800;line-height:.95;letter-spacing:-2px;margin:0;max-height:{int(size * 3.2)}px}}.sgt h1 em{{color:{red}}}"
		   f".sub2{{font:400 {20 if x.wide else 26}px/1.4 var(--font-body);margin:0;opacity:.8}}"
		   f".sg{{display:grid;grid-template-columns:60px 1fr;padding:{8 if x.wide else 12}px 0;border-top:1px solid {base.mix(ink, bg, .75)}}}"
		   f".sg i{{font:700 {16 if x.wide else 20}px var(--font-body);color:{red};font-style:normal}}.sg b{{font:700 {18 if x.wide else 24}px/1.2 var(--font-heading)}}"
		   ".sgp{min-height:0;display:flex;justify-content:center;align-items:flex-end;container-type:size}.sgt .cta,.sgt .top{flex:none}"
		   f".sq{{position:absolute;right:0;top:0;width:{90 if x.wide else 140}px;height:{90 if x.wide else 140}px;background:{red}}}")
	return body, css


# ---- 10. cinematic light -------------------------------------------------------------------------------------------
def cinematic(x: Ctx, v: dict) -> tuple[str, str]:
	bg = "#050608"
	beam = (f'<div class="layer" style="background:conic-gradient(from 160deg at 50% -10%,transparent 0deg,{base.mix(x.p["primary"], "#ffffff", .55)}55 10deg,'
			f'#ffffff22 20deg,transparent 40deg),radial-gradient(ellipse at 50% 92%,{base.mix(x.p["primary"], bg, .5)} 0,transparent 45%)"></div>')
	head = _head(x, 46 if x.wide else (70 if x.tall else 56), align="center")
	body = (f'{beam}<div class="cn">{_top(x, light=True)}<div class="pw cnp">{_phone(x)}</div>{head}{_cta(x)}</div>')
	if x.wide:
		body = f'{beam}<div class="cn cnw"><div class="cnt">{_top(x, light=True)}{_head(x, 48)}{_cta(x)}</div><div class="pw cnp">{_phone(x)}</div></div>'
	css = (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.7)", hl=_hl_on(bg, x), kick="rgba(255,255,255,.6)") + f".post{{background:{bg}}}"
		   f".cn{{position:absolute;inset:0;padding:{36 if x.wide else 56}px;display:flex;flex-direction:column;align-items:center;gap:22px}}.cn .top{{align-self:flex-start}}"
		   ".head h1{letter-spacing:2px;font-weight:700}.kick{letter-spacing:8px}"
		   ".cnp{flex:1;min-height:0;width:100%;display:flex;justify-content:center;container-type:size}"
		   ".cnp .phone{box-shadow:0 90px 120px rgba(0,0,0,.9),0 -30px 80px rgba(255,255,255,.12),0 0 0 2px rgba(255,255,255,.12) inset}"
		   ".cnw{flex-direction:row;align-items:stretch}.cnt{flex:1;display:flex;flex-direction:column;justify-content:center;gap:16px}.cnw .cnp{flex:.8}")
	return body, css


# ---- 11. on a lit stage ---------------------------------------------------------------------------------------------
def product_stage(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["dark"]
	visual = (f'<div class="fv stg"><div class="spot"></div><div class="pod"></div><div class="pw stp">{_phone(x)}</div></div>')
	html, css = _frame(x, _text(x, light=True, align="left" if _side(x) else "center"), visual, center=True, vflex=1.2)
	css += (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.8)", hl=_hl_on(bg, x), kick=_hl_on(bg, x))
			+ f".post{{background:radial-gradient(ellipse at 50% 30%,{base.mix(x.p['primary'], bg, .55)},{bg} 70%)}}"
			".stg{width:100%}.spot{position:absolute;left:10%;right:10%;top:0;bottom:8%;background:radial-gradient(ellipse at 50% 100%,rgba(255,255,255,.22),transparent 60%)}"
			f".pod{{position:absolute;left:18%;right:18%;bottom:0;height:12%;border-radius:50%;background:linear-gradient(180deg,{base.mix(x.p['primary'], '#ffffff', .4)},{x.p['primary']});"
			f"box-shadow:0 30px 60px rgba(0,0,0,.6),0 -6px 0 {base.mix(x.p['primary'], '#ffffff', .65)} inset}}"
			".stp{position:absolute;left:0;right:0;top:0;bottom:6%;display:flex;justify-content:center;align-items:flex-end;container-type:size}")
	return html, css


# ---- 12. points joined to the screen by lines ------------------------------------------------------------------------
def connected_chips(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.bg
	items = _items(x, 4)
	ys = [14, 38, 62, 86][:len(items)]
	left = [(it, y) for k, (it, y) in enumerate(zip(items, ys)) if k % 2 == 0]
	right = [(it, y) for k, (it, y) in enumerate(zip(items, ys)) if k % 2 == 1]
	lines = "".join(f'<line x1="{30 if k % 2 == 0 else 70}" y1="{y}" x2="{43 if k % 2 == 0 else 57}" y2="{y}" />' for k, y in enumerate(ys))
	dots = "".join(f'<circle cx="{43 if k % 2 == 0 else 57}" cy="{y}" r=".9" />' for k, y in enumerate(ys))

	def chip(it, y, side):
		return (f'<div class="cch {side}" style="top:{y}%">{x.el("icon_tile", 44, 44, text=it.get("icon") or "icon_check", tone="primary")}'
				f'<b>{esc(it.get("title"))}</b></div>')

	svg = (f'<svg class="lines" viewBox="0 0 100 100" preserveAspectRatio="none"><g stroke="{x.p["primary"]}" stroke-width=".35" stroke-dasharray="1 .8" fill="none">{lines}</g>'
		   f'<g fill="{x.p["accent"]}">{dots}</g></svg>')
	visual = (f'<div class="fv conn">{svg}<div class="pw cnph">{_phone(x)}</div>'
			  + "".join(chip(it, y, "l") for it, y in left) + "".join(chip(it, y, "r") for it, y in right) + "</div>")
	html, css = _frame(x, _text(x, align="center" if not _side(x) else "left"), visual, center=True, vflex=1.5, side=x.wide)
	css += (_phone_css(x) + _head_css(x) + f".post{{background:{bg}}}"
			".conn{width:100%}.lines{position:absolute;inset:0;width:100%;height:100%}"
			".cnph{position:absolute;left:31%;right:31%;top:0;bottom:0;display:flex;justify-content:center;align-items:center;container-type:size}"
			f".cch{{position:absolute;transform:translateY(-50%);display:flex;align-items:center;gap:10px;background:#fff;border-radius:16px;padding:8px 16px 8px 8px;"
			f"box-shadow:0 14px 30px rgba(0,0,0,.16);width:29%;box-sizing:border-box}}.cch.l{{left:0}}.cch.r{{right:0}}.cch svg{{flex:none}}"
			f".cch b{{font:700 {17 if x.wide else 21}px/1.15 var(--font-heading);color:{x.p['dark']}}}")
	return html, css


# ---- 13. a big number badge with your points -------------------------------------------------------------------------
def stat_badge(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["light"] if x.look == "light" else x.p["dark"]
	ink = _ink_on(bg, x)
	ring = x.p["accent"]
	badge = (f'<div class="sbg" data-piece><div class="sbv">{x.t("stat")}</div><div class="sbl">{x.t("stat_label")}</div></div>' if x.has("stat") else "")
	pts = f'<div class="feats">{_feats(x, 3)}</div>' if _items(x) else ""
	visual = f'<div class="fv pw sbp">{_phone(x)}{badge}</div>'
	html, css = _frame(x, _text(x, light=ink == "#ffffff", extra=pts), visual, vflex=1)
	d = 150 if x.wide else 250
	css += (_phone_css(x) + _head_css(x, ink=ink, hl=_hl_on(bg, x)) + _feats_css(x, card="#ffffff" if ink != "#ffffff" else "rgba(255,255,255,.08)", ink=ink,
																				border=base.mix(ink, bg, .85))
			+ f".post{{background:{bg}}}.sbp{{overflow:visible;justify-content:flex-end}}.sbp .phone{{height:min(100cqh,calc(78cqw / .49))}}"
			f".sbg{{position:absolute;left:0;bottom:6%;width:{d}px;height:{d}px;border-radius:50%;background:{ring};color:{_ink_on(ring, x)};display:flex;flex-direction:column;"
			f"align-items:center;justify-content:center;text-align:center;box-shadow:0 30px 60px rgba(0,0,0,.3),0 0 0 {d // 22}px {base.mix(ring, '#ffffff', .6)};z-index:3}}"
			f".sbv{{font:900 {int(d * .36)}px/1 var(--font-heading);letter-spacing:-2px}}.sbl{{font:700 {int(d * .085)}px/1.2 var(--font-body);padding:0 14%;margin-top:4px}}")
	return html, css


# ---- 14. three steps down a line -------------------------------------------------------------------------------------
def timeline_steps(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.bg
	steps = [s for s in (x.content.get("steps") or []) if str(s).strip()][:4]
	icons = x.content.get("step_icons") or ["icon_check"]
	tl = "".join(f'<div class="tls"><div class="tln">{k + 1}</div>{x.el("icon_tile", 56, 56, text=icons[k % len(icons)], tone="primary")}<b>{esc(s)}</b></div>'
				 for k, s in enumerate(steps))
	text = f'<div class="ft2">{_top(x)}{_head(x, _sizes(x)[0] - 8)}<div class="tl">{tl}</div>{_cta(x)}</div>'
	html, css = _frame(x, text, f'<div class="fv pw">{_phone(x)}</div>', side=True, tflex=1.25, vflex=.85)
	css += (_phone_css(x) + _head_css(x) + f".post{{background:{bg}}}"
			f".tl{{position:relative;display:flex;flex-direction:column;gap:{10 if x.wide else 22}px;padding-left:4px}}"
			f".tl:before{{content:'';position:absolute;left:21px;top:20px;bottom:20px;width:4px;border-radius:2px;background:{base.mix(x.p['primary'], bg, .6)}}}"
			f".tls{{position:relative;display:flex;align-items:center;gap:16px}}.tln{{width:42px;height:42px;border-radius:50%;flex:none;background:{x.p['accent']};"
			f"color:{x.p['on_accent']};display:flex;align-items:center;justify-content:center;font:800 22px var(--font-heading);z-index:1}}"
			f".tls svg{{flex:none}}.tls b{{font:700 {20 if x.wide else 27}px/1.2 var(--font-heading);color:{x.ink}}}")
	return html, css


# ---- 15. problem and solution ----------------------------------------------------------------------------------------
def problem_solution_ui(x: Ctx, v: dict) -> tuple[str, str]:
	bad = "#dc2626"
	probs = [p for p in (x.content.get("problems") or []) if str(p).strip()][:3]
	plist = "".join(f'<div class="pb"><i>✕</i><span>{esc(p)}</span></div>' for p in probs)
	sols = "".join(f'<div class="pg"><i>✓</i><span>{esc(it.get("title"))}</span></div>' for it in _items(x, 3))
	side = _side(x)
	left = f'<div class="ps1"><div class="pst">{x.t("kicker") or ""}</div>{plist}</div>'
	right = (f'<div class="ps2">{_top(x)}<h1 class="fit" data-fit style="font-size:{_sizes(x)[0] - 10}px">{x.m("headline")}</h1>{sols}'
			 f'<div class="pw psp">{_phone(x)}</div>{_cta(x)}</div>')
	body = f'<div class="ps {"psr" if side else "psc"}">{left}{right}</div>'
	pad = 36 if x.wide else 52
	css = (_phone_css(x) + f".post{{background:{x.p['light']}}}.ps{{position:absolute;inset:0;display:flex}}.psr{{flex-direction:row}}.psc{{flex-direction:column}}"
		   f".ps1{{background:#1f2937;color:#fff;padding:{pad}px;display:flex;flex-direction:column;justify-content:center;gap:16px}}.psr .ps1{{flex:.8}}.psc .ps1{{flex:none}}"
		   f".pst{{font:700 {16 if x.wide else 22}px var(--font-body);letter-spacing:3px;text-transform:uppercase;opacity:.7}}"
		   f".pb{{display:flex;gap:14px;align-items:flex-start;font:600 {19 if x.wide else 26}px/1.25 var(--font-body);opacity:.9}}"
		   f".pb i{{color:{bad};font-style:normal;font-weight:900;flex:none}}.pb span{{text-decoration:line-through;text-decoration-color:{bad}88}}"
		   f".ps2{{flex:1;min-height:0;padding:{pad}px;display:flex;flex-direction:column;gap:{10 if x.wide else 16}px;color:{x.p['dark']}}}"
		   f".ps2 h1{{font-family:var(--font-heading);font-weight:800;line-height:1.05;margin:0;max-height:{(_sizes(x)[0] - 10) * 2.4:.0f}px}}.ps2 h1 em{{color:{x.p['primary']}}}"
		   f".pg{{display:flex;gap:12px;font:700 {18 if x.wide else 24}px/1.25 var(--font-heading)}}.pg i{{color:#16a34a;font-style:normal;flex:none}}"
		   ".psp{flex:1;min-height:0;display:flex;justify-content:center;container-type:size}.ps2 .top,.ps2 .cta{flex:none}")
	return body, css


# ---- 16. global reach: a globe behind the phone ----------------------------------------------------------------------
def _globe(x: Ctx, colour: str) -> str:
	lines = "".join(f'<ellipse cx="50" cy="50" rx="{r}" ry="48" />' for r in (48, 36, 22, 8))
	lats = "".join(f'<line x1="{50 - w}" y1="{y}" x2="{50 + w}" y2="{y}" />' for y, w in ((20, 38), (35, 46), (50, 48), (65, 46), (80, 38)))
	return (f'<svg class="globe" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48" fill="{colour}" fill-opacity=".14"/>'
			f'<g fill="none" stroke="{colour}" stroke-opacity=".55" stroke-width=".5">{lines}{lats}</g></svg>')


def globe_reach(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["dark"]
	chips = _chips(x, 8)
	angles = [(-150, 1), (-30, 1), (160, 1), (20, 1), (-100, .9), (100, .9), (-60, .95), (60, .95)]
	placed = "".join(f'<div class="gl" style="left:{50 + 44 * a * math.cos(math.radians(t)):.1f}%;top:{50 + 40 * a * math.sin(math.radians(t)):.1f}%">{c}</div>'
					 for c, (t, a) in zip(chips, angles))
	visual = f'<div class="fv gw">{_globe(x, base.mix(x.p["accent"], "#ffffff", .3))}<div class="pw gph">{_phone(x)}</div>{placed}</div>'
	html, css = _frame(x, _text(x, light=True, align="left" if _side(x) else "center"), visual, center=True, vflex=1.4)
	css += (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.8)", hl=_hl_on(bg, x), kick=_hl_on(bg, x)) + _chip_css(x)
			+ f".post{{background:radial-gradient(circle at 50% 60%,{base.mix(x.p['primary'], bg, .45)},{bg} 70%)}}"
			".gw{width:100%;container-type:size}.globe{position:absolute;left:50%;top:50%;width:min(98cqh,100cqw);height:min(98cqh,100cqw);transform:translate(-50%,-50%)}"
			".gph{position:absolute;inset:6% 30%;display:flex;justify-content:center;align-items:center;container-type:size}"
			f".gl{{position:absolute;transform:translate(-50%,-50%);z-index:2}}.gl .chip{{font-size:{19 if x.wide else 24}px;padding:10px 20px}}")
	return html, css


# ---- 17. rows of pills sliding behind the phone ----------------------------------------------------------------------
def pill_rows(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["primary"]
	words = [esc(c) for c in (x.content.get("list") or []) if str(c).strip()][:10]
	rows = ""
	for r in range(5 if x.tall else 4):
		seq = (words[r % max(1, len(words)):] + words[:r % max(1, len(words))]) * 3
		rows += f'<div class="pr" style="margin-left:{-(r * 90) % 300}px">' + "".join(f'<span class="pl{(k + r) % 3}">{w}</span>' for k, w in enumerate(seq)) + "</div>"
	body = (f'<div class="prs">{rows}</div><div class="prw {"prr" if _side(x) else "prc"}"><div class="prt">{_top(x, light=_ink_on(bg, x) == "#ffffff")}'
			f'{_head(x, _sizes(x)[0])}{_cta(x, tone="dark")}</div><div class="pw prp">{_phone(x)}</div></div>')
	ink = _ink_on(bg, x)
	css = (_phone_css(x) + _head_css(x, ink=ink, hl=_hl_on(bg, x), kick=ink, soft=base.mix(ink, bg, .2)) + f".post{{background:{bg}}}"
		   ".prs{position:absolute;inset:-10% -20%;display:flex;flex-direction:column;justify-content:space-around;transform:rotate(-12deg);opacity:.95}"
		   ".pr{display:flex;gap:18px;white-space:nowrap}"
		   f".pr span{{font:800 {26 if x.wide else 34}px var(--font-heading);padding:12px 28px;border-radius:999px}}"
		   f".pl0{{background:{base.mix(bg, '#ffffff', .82)};color:{x.p['dark']}}}.pl1{{background:{base.mix(bg, x.p['dark'], .35)};color:#fff}}"
		   f".pl2{{background:transparent;color:{base.mix(bg, '#ffffff', .6)};box-shadow:0 0 0 2px {base.mix(bg, '#ffffff', .5)} inset}}"
		   f".prw{{position:absolute;inset:0;padding:{40 if x.wide else 56}px;display:flex;gap:30px}}.prr{{flex-direction:row}}.prc{{flex-direction:column}}"
		   f".prt{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:18px;background:{bg};border-radius:28px;padding:28px;"
		   f"box-shadow:0 20px 60px rgba(0,0,0,.25)}}.prc .prt{{flex:none}}.prt .top,.prt .cta{{flex:none}}"
		   ".prp{flex:1;min-height:0;display:flex;justify-content:center;align-items:center;container-type:size}.prr .prp{flex:.8}")
	return body, css


# ---- 18. open book (learning, faith, reading) ------------------------------------------------------------------------
def open_book(x: Ctx, v: dict) -> tuple[str, str]:
	bg = "#1b1410" if x.look != "light" else "#fbf6ec"
	paper = "#fbf3e2"
	page_lines = "".join(f'<i style="top:{18 + k * 9}%"></i>' for k in range(7))
	book = (f'<div class="bk"><div class="pg l">{page_lines}</div><div class="pg r">{page_lines}</div><div class="spine"></div></div>')
	visual = f'<div class="fv bkv">{_backdrop(x, "rgba(0,0,0,.35)")}{book}<div class="pw bkp">{_phone(x)}</div></div>'
	dark = x.look != "light"
	html, css = _frame(x, _text(x, light=dark, align="left" if _side(x) else "center"), visual, center=True, vflex=1.35)
	glow = f'<div class="layer" style="background:radial-gradient(ellipse at 50% 70%,{"#f5c76b55" if dark else "#f5c76b40"} 0,transparent 55%)"></div>'
	ink = "#ffffff" if dark else "#2a1d12"
	css += (_phone_css(x) + _head_css(x, ink=ink, soft=base.mix(ink, bg, .25), hl=x.p["accent"] if base.contrast(x.p["accent"], bg) > 2.4 else "#d4a72c",
									 kick="#d4a72c") + f".post{{background:{bg}}}"
			".bkv{width:100%}.bk{position:absolute;left:4%;right:4%;bottom:0;height:34%;perspective:900px}"
			f".pg{{position:absolute;bottom:0;width:50%;height:100%;background:linear-gradient(180deg,{paper},#ead8b5);box-shadow:0 30px 50px rgba(0,0,0,.45)}}"
			".pg.l{left:0;transform:rotateX(55deg) skewY(4deg);transform-origin:bottom right;border-radius:14px 0 0 8px}"
			".pg.r{right:0;transform:rotateX(55deg) skewY(-4deg);transform-origin:bottom left;border-radius:0 14px 8px 0}"
			".pg i{position:absolute;left:12%;right:12%;height:3px;background:#b9a27a66;border-radius:2px}"
			".spine{position:absolute;left:50%;bottom:0;width:6px;height:100%;transform:translateX(-50%);background:#8b6b3d}"
			".bkp{position:absolute;inset:0 0 14%;display:flex;justify-content:center;align-items:flex-end;container-type:size}")
	return glow + html, css


# ---- 19. bold colour blocks -------------------------------------------------------------------------------------------
def color_blocks(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["light"]
	shapes = (f'<div class="layer"><div class="cb1" style="background:{x.p["primary"]}"></div><div class="cb2" style="background:{x.p["accent"]}"></div>'
			  f'<div class="cb3" style="border-bottom-color:{x.p["dark"]}"></div><div class="cb4" style="background:{x.p["secondary"]}"></div></div>')
	visual = f'<div class="fv pw">{_phone(x)}</div>'
	html, css = _frame(x, _text(x, cta_tone="dark"), visual, reverse=False)
	css += (_phone_css(x) + _head_css(x, ink=x.p["dark"], hl=x.p["primary"] if base.contrast(x.p["primary"], bg) > 2.4 else x.p["dark"]) + f".post{{background:{bg}}}"
			".cb1{position:absolute;right:-12%;top:-10%;width:70%;aspect-ratio:1;border-radius:50%}"
			".cb2{position:absolute;right:28%;bottom:-6%;width:30%;height:34%}"
			".cb3{position:absolute;left:4%;bottom:6%;width:0;height:0;border-left:90px solid transparent;border-right:90px solid transparent;border-bottom:150px solid}"
			".cb4{position:absolute;right:4%;bottom:10%;width:14%;aspect-ratio:1;border-radius:50%}"
			".ft2{background:#fff;border-radius:6px;padding:30px;box-shadow:14px 14px 0 " + x.p["dark"] + ";align-self:center}")
	return shapes + html, css


# ---- 20. magazine cover ----------------------------------------------------------------------------------------------
def magazine_cover(x: Ctx, v: dict) -> tuple[str, str]:
	bg = x.p["light"] if x.look == "light" else x.p["primary"]
	ink = _ink_on(bg, x)
	name = esc(x.content.get("business") or "")
	lines = "".join(f'<div class="cl"><b>{esc(it.get("title"))}</b>{_txt(it)}</div>' for it in _items(x, 3))
	size = 60 if x.wide else (120 if x.tall else 104)
	body = (f'<div class="mg"><div class="mast fit" data-fit style="font-size:{size}px;max-height:{int(size * 1.1)}px">{name}</div>'
			f'<div class="mrow"><div class="mcol">{"<div class=iss>" + x.t("kicker") + "</div>" if x.has("kicker") else ""}'
			f'<h1 class="fit" data-fit>{x.m("headline")}</h1>{lines}{_cta(x, tone="dark" if ink != "#ffffff" else "accent")}</div>'
			f'<div class="pw mph">{_phone(x)}</div></div></div>')
	hl = _hl_on(bg, x)
	css = (_phone_css(x) + f".post{{background:{bg};color:{ink}}}"
		   f".mg{{position:absolute;inset:0;padding:{30 if x.wide else 50}px;display:flex;flex-direction:column}}"
		   f".mast{{font-family:var(--font-heading);font-weight:900;line-height:.9;letter-spacing:-3px;text-transform:uppercase;border-bottom:4px solid {ink};padding-bottom:10px;"
		   f"white-space:nowrap;overflow:hidden}}.mrow{{flex:1;min-height:0;display:flex;gap:24px;margin-top:20px}}"
		   f".mcol{{flex:1;display:flex;flex-direction:column;justify-content:flex-start;gap:{10 if x.wide else 16}px}}"
		   f".iss{{display:inline-block;align-self:flex-start;background:{hl};color:{_ink_on(hl, x)};font:800 {14 if x.wide else 20}px var(--font-body);text-transform:uppercase;letter-spacing:2px;padding:6px 14px}}"
		   f".mcol h1{{font:800 {38 if x.wide else 58}px/1.02 var(--font-heading);margin:0;max-height:{120 if x.wide else 250}px}}.mcol h1 em{{color:{hl}}}"
		   f".cl{{border-left:5px solid {hl};padding-left:14px}}.cl b{{display:block;font:800 {17 if x.wide else 25}px/1.15 var(--font-heading)}}"
		   f".cl span{{display:block;font:400 {14 if x.wide else 18}px/1.3 var(--font-body);opacity:.8}}.mcol .cta{{flex:none;margin-top:auto}}"
		   ".mph{flex:1.05;min-height:0;display:flex;justify-content:flex-end;align-items:flex-end;container-type:size}")
	return body, css


LAYOUTS = {"tilt_premium": tilt_premium, "screen_pop": screen_pop, "ui_orbit": ui_orbit, "big_type": big_type, "full_phone": full_phone,
		   "split_benefits": split_benefits, "diagonal_layers": diagonal_layers, "glass_cards": glass_cards, "swiss_grid": swiss_grid,
		   "cinematic": cinematic, "product_stage": product_stage, "connected_chips": connected_chips, "stat_badge": stat_badge,
		   "timeline_steps": timeline_steps, "problem_solution_ui": problem_solution_ui, "globe_reach": globe_reach, "pill_rows": pill_rows,
		   "open_book": open_book, "color_blocks": color_blocks, "magazine_cover": magazine_cover}
