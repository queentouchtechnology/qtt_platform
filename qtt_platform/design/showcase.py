"""
Showcase layouts (PROJ-0012 S10 — Marketing Poster Variations): a product's real screenshots (an app, a website, a
dashboard) or photos in designed compositions — each layout one creative direction. Same rules as every layout
(layouts.py): content in, HTML out, at 1080 wide, flex only, so every size works — square, portrait, story and the wide
ones (16:9, 3:2), where text and the device sit side by side.

The screenshot is the source of truth: it is placed as it is, inside a device frame drawn in CSS — never redrawn, never
written on. Without one (library pictures, nightly check) a plain sample screen in the brand's colours stands in.

Content: the usual slots (layouts.py) plus
  stat, stat_label   one number the owner gave ("159+", "Bible modules") — never made up
  list               short chips (languages, platforms, categories) — the owner's own
  steps              2–4 short steps ("Search", "Download", "Read offline")
  backdrop           a picture behind everything (the owner's photo or a Photo Lab AI scene), file name beside the page
  photos             the screenshots, in order
"""

from qtt_platform.design import base
from qtt_platform.design.layouts import Ctx, esc

# key: (label, what it is, what it needs) — the creative directions offered in Studio › Poster variations
DIRECTIONS = {
	"ui_showcase": ("Product UI showcase", "Your real screen in a phone, with your main points beside it", {}),
	"device_tilt": ("3D product showcase", "An angled phone with depth and glow, your points floating around it", {}),
	"pop_cards": ("Pop-out cards", "Your points as cards popping out of the phone", {"items": 2}),
	"minimal_device": ("Minimal premium", "Clean type, lots of space, one phone", {}),
	"bold_promo": ("Bold promotional", "A big headline, a strong colour and a call to act", {}),
	"stat_hero": ("Feature in numbers", "One number you give, big — with the phone", {"stat": 1}),
	"steps_flow": ("How it works", "Your steps in a row, then the app", {"steps": 2}),
	"chips_cloud": ("Floating chips", "Your languages, platforms or categories floating around the phone", {"list": 3}),
	"editorial": ("Editorial", "Magazine-style: numbered points beside the phone", {"items": 2}),
	"scene_device": ("In context", "The phone over a photo or an AI background", {}),
	"duo_screens": ("Two screens", "Two of your screens side by side", {"shots": 2}),
}


def can_use(key: str, content: dict, shots: int) -> bool:
	"""Does the owner's content have what this direction needs (2 points, a number, steps, chips, 2 screens)?"""
	need = DIRECTIONS[key][2]
	if shots < need.get("shots", 0):
		return False
	if need.get("stat") and not str(content.get("stat") or "").strip():
		return False
	for slot in ("items", "steps", "list", "problems"):
		if len(content.get(slot) or []) < need.get(slot, 0):
			return False
	return True


# ---- shared parts --------------------------------------------------------------------------------------------------
def _skeleton(x: Ctx) -> str:
	"""A plain sample screen in the brand's colours (when there's no screenshot): a header, a search bar, list rows."""
	rows = "".join(f'<div class="skr"><span></span><p><b style="width:{w}%"></b><i></i></p><em></em></div>' for w in (62, 48, 70, 54, 40))
	return f'<div class="sk"><div class="skh"><b></b><i></i><u></u></div><div class="skb">{rows}</div></div>'


def _phone(x: Ctx, i: int = 0, cls: str = "") -> str:
	shot = x.photos[i % len(x.photos)] if x.photos else None
	screen = f'<img class="shot" src="{esc(shot)}">' if shot else _skeleton(x)
	return f'<div class="phone {cls}" data-piece><div class="scr">{screen}</div><i class="notch"></i></div>'


def _phone_css(x: Ctx) -> str:
	p = x.p
	return (
		".pw,.p1,.p2,.stage.box{container-type:size}"
		".phone{position:relative;box-sizing:border-box;aspect-ratio:.49;height:min(100cqh,calc(100cqw / .49));width:auto;flex:none;border-radius:62px;background:#0c0d12;"
		"padding:14px;box-shadow:0 50px 90px rgba(0,0,0,.38),0 0 0 2px rgba(255,255,255,.07) inset}"
		".phone .scr{width:100%;height:100%;border-radius:50px;overflow:hidden;background:#fff}"
		".phone .shot{width:100%;height:100%;object-fit:cover;object-position:top center;display:block}"
		".phone .notch{position:absolute;top:22px;left:50%;transform:translateX(-50%);width:24%;height:26px;background:#0c0d12;border-radius:20px}"
		f".sk{{height:100%;display:flex;flex-direction:column;background:{p['light']};font-size:0}}"
		f".skh{{background:{p['dark']};padding:70px 26px 30px}}.skh b{{display:block;width:60%;height:26px;border-radius:8px;background:rgba(255,255,255,.9)}}"
		".skh i{display:block;width:80%;height:12px;margin-top:12px;border-radius:6px;background:rgba(255,255,255,.45)}"
		".skh u{display:block;height:44px;margin-top:22px;border-radius:22px;background:rgba(255,255,255,.14)}"
		".skb{flex:1;padding:18px 16px;overflow:hidden}"
		".skr{display:flex;align-items:center;gap:14px;background:#fff;border-radius:18px;padding:16px;margin-bottom:14px;box-shadow:0 4px 14px rgba(0,0,0,.06)}"
		f".skr span{{width:54px;height:54px;border-radius:14px;background:{p['primary']};flex:none}}.skr p{{flex:1;margin:0}}"
		f".skr p b{{display:block;height:14px;border-radius:7px;background:{p['dark']};opacity:.8}}.skr p i{{display:block;width:40%;height:10px;margin-top:9px;border-radius:5px;background:{p['dark']};opacity:.25}}"
		f".skr em{{width:84px;height:36px;border-radius:12px;background:{p['accent']};flex:none}}"
	)


def _head(x: Ctx, size: int, *, align: str = "left", upper: bool = False, kick_tone: str | None = None) -> str:
	kick = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	sub = f'<p class="sub">{x.m("subline")}</p>' if x.has("subline") else ""
	return (f'<div class="head" style="text-align:{align}">{kick}<h1 class="fit" data-fit style="font-size:{size}px;max-height:{round(size * 2.3)}px;'
			f'{"text-transform:uppercase;" if upper else ""}">{x.m("headline")}</h1>{sub}</div>')


def readable(colour: str, bg: str, ink: str, need: float) -> str:
	"""The colour, moved toward the text colour until it reads on the background (need: 4.5 small text, 3 large)."""
	if not (str(colour).startswith("#") and len(colour) == 7 and str(bg).startswith("#") and len(bg) == 7):
		return colour  # white at an opacity on a dark layer (a layout's own, already readable)
	if base.contrast(colour, bg) >= need:
		return colour
	if base.contrast(ink, "#000000") < base.contrast(ink, "#ffffff"):
		return ink  # dark text: a darkened highlight looks muddy — plain text colour reads cleanly
	c = colour
	for k in range(1, 8):  # light text: a lighter tint of the colour keeps its hue
		c = base.mix(colour, ink, k / 7)
		if base.contrast(c, bg) >= need:
			return c
	return ink


def _head_css(x: Ctx, *, ink: str | None = None, hl: str | None = None, kick: str | None = None, soft: str | None = None,
			  bg: str | None = None) -> str:
	ink = ink or x.ink
	bg = bg or _bg_of(x, ink)
	hl = readable(hl or x.hl, bg, ink, 3)
	kick = readable(kick or hl, bg, ink, 4.5)
	k, sb = (17, 21) if x.wide else (24, 28)
	return (f".head{{color:{ink}}}.head h1{{font-family:var(--font-heading);font-weight:800;line-height:1.04;margin:0;letter-spacing:-.5px}}"
			f".head h1 em{{color:{hl or x.hl}}}.kick{{font:700 {k}px var(--font-body);letter-spacing:3px;text-transform:uppercase;"
			f"color:{kick or x.hl};margin-bottom:{8 if x.wide else 14}px}}.sub{{font:400 {sb}px/1.4 var(--font-body);color:{soft or x.soft};margin:{10 if x.wide else 18}px 0 0}}"
			f".sub em{{color:{hl or x.hl};font-weight:700}}")


def _bg_of(x: Ctx, ink: str) -> str:
	"""The background the text sits on, as far as a layout tells: dark text → the light colour, light text → the dark one."""
	return x.p["light"] if base.contrast(ink, "#ffffff") > base.contrast(ink, "#000000") else x.p["dark"]


def _feats(x: Ctx, limit: int = 4, tone: str = "primary") -> str:
	return "".join(f'<div class="ft">{x.el("icon_tile", 58, 58, text=it.get("icon") or "icon_check", tone=tone)}'
				   f'<div><b>{esc(it.get("title"))}</b>{f"<span>{esc(it.get(chr(116) + chr(101) + chr(120) + chr(116)))}</span>" if it.get("text") else ""}</div></div>'
				   for it in (x.content.get("items") or [])[:limit])


def _feats_css(x: Ctx, *, card: str = "rgba(255,255,255,.08)", ink: str | None = None, border: str = "rgba(255,255,255,.14)") -> str:
	zoom = "zoom:.72;" if x.wide else ""
	return (f".ft{{{zoom}display:flex;align-items:center;gap:16px;background:{card};border:1px solid {border};border-radius:22px;padding:14px 20px 14px 14px;"
			f"margin-bottom:14px}}.ft svg{{flex:none}}.ft b{{display:block;font:700 24px/1.2 var(--font-heading);color:{ink or x.ink}}}"
			f".ft span{{display:block;font:400 18px/1.3 var(--font-body);color:{ink or x.ink};opacity:.75}}")


def _cta(x: Ctx, w: int = 440, h: int = 92, tone: str = "accent") -> str:
	if x.wide:
		w, h = min(w, 320), min(h, 68)
	return f'<div class="cta">{x.el("cta", w, h, text=x.content.get("cta"), tone=tone)}</div>' if x.has("cta") else ""


def _chips(x: Ctx, limit: int = 8) -> list[str]:
	return [f'<span class="chip">{esc(c)}</span>' for c in (x.content.get("list") or [])[:limit] if str(c).strip()]


def _chip_css(x: Ctx, bg: str = "#ffffff", ink: str | None = None) -> str:
	return (f".chip{{display:inline-block;background:{bg};color:{ink or x.p['dark']};font:700 26px var(--font-body);padding:14px 26px;"
			"border-radius:999px;box-shadow:0 14px 30px rgba(0,0,0,.22);white-space:nowrap}")


def _stat(x: Ctx, size: int = 200) -> str:
	if not x.has("stat"):
		return ""
	label = f'<div class="sl">{x.t("stat_label")}</div>' if x.has("stat_label") else ""
	return f'<div class="stat"><div class="sv" style="font-size:{size}px">{x.t("stat")}</div>{label}</div>'


def _stat_css(x: Ctx, colour: str | None = None, ink: str | None = None) -> str:
	return (f".stat .sv{{font-family:var(--font-heading);font-weight:900;line-height:.9;color:{colour or x.hl};letter-spacing:-3px}}"
			f".stat .sl{{font:700 30px var(--font-body);color:{ink or x.ink};margin-top:10px}}")


def _top(x: Ctx, *, light: bool | None = None) -> str:
	return f'<div class="top">{x.logo(52 if x.wide else 72, light=light)}</div>'


def _backdrop(x: Ctx, shade: str) -> str:
	b = x.content.get("backdrop")
	if not b:
		return ""
	return (f'<div class="layer" style="background:url({esc(b)}) center/cover no-repeat"></div>'
			f'<div class="layer" style="background:{shade}"></div>')


def _sizes(x: Ctx) -> tuple[int, int]:
	"""(headline size, padding) for the format."""
	if x.wide:
		return 50, 40
	return (104, 72) if x.tall else (74, 56)


def _side(x: Ctx) -> bool:
	"""Text and device side by side: the wide sizes and the square (a column leaves the phone too small there)."""
	return x.wide or x.h <= 1080


# ---- 1. product UI showcase -------------------------------------------------------------------------------------------
def ui_showcase(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	dark = x.look != "light"
	bg = x.p["dark"] if dark else x.p["light"]
	glow = (f'<div class="layer" style="background:radial-gradient(circle at 78% 62%,{base.mix(x.p["primary"], bg, .35)} 0,transparent 55%),'
			f'radial-gradient(circle at 8% 0%,{base.mix(x.p["accent"], bg, .7)} 0,transparent 40%)"></div>')
	feats = f'<div class="feats">{_feats(x, 2 if x.wide else (4 if x.tall else 3))}</div>' if x.content.get("items") else ""
	if _side(x):
		comp = (f'<div class="wrap row"><div class="txt">{_top(x)}{_head(x, hs)}{feats}{_cta(x, 380, 80)}</div>'
				f'<div class="pw">{_phone(x)}</div></div>')
	else:
		comp = (f'<div class="wrap col">{_top(x)}{_head(x, hs)}<div class="pw">{_phone(x)}</div>'
				f'{feats.replace("feats", "feats under")}{_cta(x)}</div>')
	body = glow + comp
	ink = "#ffffff" if dark else x.p["dark"]
	css = (_phone_css(x) + _head_css(x, ink=ink) + _feats_css(x, card="rgba(255,255,255,.07)" if dark else "#ffffff", ink=ink,
																border="rgba(255,255,255,.12)" if dark else base.mix(x.p["primary"], "#ffffff", .8))
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:28px}}.col{{flex-direction:column}}"
			 f".row{{flex-direction:row;align-items:stretch}}.txt{{flex:1.15;display:flex;flex-direction:column;justify-content:center;gap:{14 if x.wide else 22}px}}"
			 ".mid{flex:1;min-height:0;display:flex;gap:26px;align-items:stretch}.feats{flex:1;display:flex;flex-direction:column;justify-content:center}"
			 ".pw{flex:1;min-height:0;min-width:0;display:flex;justify-content:center;align-items:center}"
			 ".row .pw{flex:.85}.cta{flex:none}.top{flex:none}"
			 ".feats.under{flex:none;display:grid;grid-template-columns:1fr 1fr;gap:0 14px}.col .cta{align-self:center}")
	return body, css


# ---- 2. 3D product showcase -------------------------------------------------------------------------------------------
def device_tilt(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	bg = x.p["dark"]
	chips = _chips(x, 6)
	spots = [("8%", "30%"), ("62%", "24%"), ("4%", "58%"), ("66%", "54%"), ("12%", "80%"), ("60%", "82%")]
	floating = "".join(f'<div class="fl" style="left:{l};top:{t}">{c}</div>' for c, (l, t) in zip(chips, spots))
	if not floating and x.content.get("items"):
		floating = "".join(f'<div class="fl" style="left:{l};top:{t}"><span class="chip">{esc(it.get("title"))}</span></div>'
						   for it, (l, t) in zip(x.content["items"][:4], spots))
	stage = f'<div class="stage"><div class="pw">{_phone(x, cls="tilt")}</div>{floating}</div>'
	if x.wide:
		comp = f'<div class="wrap row"><div class="txt">{_top(x, light=True)}{_head(x, hs)}{_cta(x, 380, 80)}</div>{stage}</div>'
	else:
		comp = f'<div class="wrap col">{_top(x, light=True)}{_head(x, hs, align="center")}{stage}{_cta(x)}</div>'
	glow = (f'<div class="layer" style="background:radial-gradient(ellipse at 50% 70%,{base.mix(x.p["primary"], bg, .25)} 0,transparent 60%),'
			f'linear-gradient(160deg,{base.mix(x.p["primary"], bg, .75)},{bg} 60%)"></div>')
	css = (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.78)",
									 hl=x.p["accent"] if base.contrast(x.p["accent"], bg) > 2.4 else "#ffffff",
									 kick=x.p["accent"] if base.contrast(x.p["accent"], bg) > 2.4 else "#ffffff") + _chip_css(x)
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:26px}}.col{{flex-direction:column;align-items:center}}"
			 ".row{flex-direction:row}.txt{flex:1;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none;align-self:flex-start}"
			 ".stage{position:relative;flex:1;min-height:0;width:100%;perspective:1800px}.row .stage{flex:1}"
			 ".pw{position:absolute;inset:4% 0 0;display:flex;justify-content:center}"
			 ".phone.tilt{transform:rotateY(-22deg) rotateX(8deg) rotateZ(5deg);box-shadow:-40px 60px 90px rgba(0,0,0,.55),0 0 0 2px rgba(255,255,255,.08) inset}"
			 ".fl{position:absolute;transform:translate(-10%,-50%)}.cta{flex:none}")
	return glow + comp, css


# ---- 3. pop-out cards ---------------------------------------------------------------------------------------------------
def pop_cards(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	items = (x.content.get("items") or [])[:3]
	spots = [("left:-18%;top:18%", "-4deg"), ("right:-20%;top:44%", "3deg"), ("left:-14%;top:72%", "-2deg")]
	cards = "".join(f'<div class="card" style="{pos};transform:rotate({rot})">{x.el("icon_tile", 56, 56, text=it.get("icon") or "icon_check", tone="primary")}'
					f'<div><b>{esc(it.get("title"))}</b>{f"<span>{esc(it.get(chr(116) + chr(101) + chr(120) + chr(116)))}</span>" if it.get("text") else ""}</div></div>'
					for it, (pos, rot) in zip(items, spots))
	stage = f'<div class="stage"><div class="holder">{_phone(x)}{cards}</div></div>'
	if _side(x):
		comp = f'<div class="wrap row"><div class="txt">{_top(x)}{_head(x, hs)}{_cta(x, 380, 80)}</div>{stage}</div>'
	else:
		comp = f'<div class="wrap col">{_top(x)}{_head(x, hs, align="center")}{stage}{_cta(x)}</div>'
	bg = x.bg
	deco = (f'<div class="layer" style="background:radial-gradient(circle at 50% 75%,{base.mix(x.p["primary"], bg, .55)} 0,transparent 50%)"></div>')
	css = (_phone_css(x) + _head_css(x)
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:26px}}.col{{flex-direction:column;align-items:center}}"
			 ".row{flex-direction:row}.txt{flex:1;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none;align-self:flex-start}"
			 ".stage{flex:1;min-height:0;width:100%;display:flex;justify-content:center;align-items:center;container-type:size}"
			 ".holder{position:relative;aspect-ratio:.49;height:min(100cqh,calc(100cqw / .49))}.holder .phone{height:100%}"
			 f".card{{position:absolute;display:flex;align-items:center;gap:14px;background:#fff;border-radius:24px;padding:16px 22px 16px 16px;"
			 f"box-shadow:0 26px 50px rgba(0,0,0,.28);max-width:440px;z-index:2}}.card svg{{flex:none}}"
			 f".card b{{display:block;font:800 26px/1.15 var(--font-heading);color:{x.p['dark']}}}.card span{{display:block;font:400 18px/1.3 var(--font-body);color:{base.mix(x.p['dark'], '#ffffff', .35)}}}"
			 ".cta{flex:none}")
	return deco + comp, css


# ---- 4. minimal premium -------------------------------------------------------------------------------------------------
def minimal_device(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	bg = "#fafaf7" if x.look == "light" else x.bg
	ink = x.p["dark"] if x.look == "light" else x.ink
	if x.wide:
		comp = (f'<div class="wrap row"><div class="txt">{_top(x)}{_head(x, hs - 6)}{_cta(x, 340, 76, tone="dark")}</div>'
				f'<div class="pw low">{_phone(x)}</div></div>')
	else:
		comp = (f'<div class="wrap col">{_top(x)}{_head(x, hs - 8, align="center")}{_cta(x, 360, 80, tone="dark")}'
				f'<div class="pw low">{_phone(x)}</div></div>')
	css = (_phone_css(x) + _head_css(x, ink=ink, hl=x.p["primary"] if base.contrast(x.p["primary"], bg) > 2.4 else ink, kick=base.mix(ink, bg, .45))
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad + 20}px {pad + 20}px 0;display:flex;gap:30px}}"
			 ".col{flex-direction:column;align-items:center}.row{flex-direction:row;padding-bottom:0}.txt{flex:1;display:flex;flex-direction:column;justify-content:center;gap:26px;padding-bottom:40px}"
			 ".top{flex:none;align-self:flex-start}.head h1{font-weight:700;letter-spacing:-1px}"
			 ".pw{flex:1;min-height:0;width:100%;display:flex;justify-content:center;overflow:hidden}.row .pw{flex:.8}"
			 ".pw.low{align-items:flex-start}.pw.low .phone{height:112cqh;box-shadow:0 30px 70px rgba(0,0,0,.18)}.cta{flex:none}")
	return comp, css


# ---- 5. bold promotional ----------------------------------------------------------------------------------------------
def bold_promo(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	bg = x.p["primary"]
	ink = x.p["on_primary"]
	hl = x.p["accent"] if base.contrast(x.p["accent"], bg) >= 2 else ink
	badge = f'<div class="bdg">{x.el("badge", 190, 190, text=x.content.get("badge"), tone="accent")}</div>' if x.has("badge") else ""
	if x.wide:
		comp = (f'<div class="wrap row"><div class="txt">{_top(x)}{_head(x, hs + 6, upper=True)}{_cta(x, 400, 84, tone="dark")}</div>'
				f'<div class="pw">{_phone(x, cls="lean")}</div></div>{badge}')
	else:
		comp = (f'<div class="wrap col">{_top(x)}{_head(x, hs + 14, upper=True)}{_cta(x, 400, 88, tone="dark")}'
				f'<div class="pw wide-pw">{_phone(x, cls="lean")}</div></div>{badge}')
	stripes = (f'<div class="layer" style="background:repeating-linear-gradient(-35deg,transparent 0 80px,{base.mix(bg, "#ffffff", .9)}10 80px 82px),'
			   f'linear-gradient(140deg,{bg},{base.mix(bg, x.p["dark"], .35)})"></div>')
	css = (_phone_css(x) + _head_css(x, ink=ink, hl=hl, kick=hl, soft=base.mix(ink, bg, .2))
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px {pad}px 0;display:flex;gap:24px}}.col{{flex-direction:column}}"
			 ".row{flex-direction:row}.txt{flex:1.2;display:flex;flex-direction:column;justify-content:center;gap:24px;padding-bottom:40px}.top{flex:none}"
			 ".head h1{font-weight:900;letter-spacing:-1px}.low{flex:1;min-height:0;display:flex;align-items:flex-end;gap:20px}"
			 ".ctaw{flex:1;align-self:center}.pw{flex:1;min-height:0;height:100%;display:flex;justify-content:flex-end;overflow:hidden}"
			 ".phone.lean{height:min(112cqh,calc(100cqw / .49));transform:rotate(-8deg) translateY(6%);transform-origin:bottom center}"
			 ".bdg{position:absolute;right:46px;top:40px}.col .cta{flex:none}.pw.wide-pw{flex:1;width:100%;justify-content:center;overflow:visible}")
	return stripes + comp, css


# ---- 6. feature in numbers --------------------------------------------------------------------------------------------
def stat_hero(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	dark = x.look != "light"
	bg = x.p["dark"] if dark else x.p["light"]
	ink = "#ffffff" if dark else x.p["dark"]
	big = 104 if x.wide else (260 if x.tall else 190)
	if x.wide or not x.tall:
		comp = (f'<div class="wrap row"><div class="txt">{_top(x, light=dark)}{_stat(x, big)}{_head(x, hs - 14)}{_cta(x, 380, 80)}</div>'
				f'<div class="pw">{_phone(x)}</div></div>')
	else:
		comp = (f'<div class="wrap col">{_top(x, light=dark)}<div class="duo">{_stat(x, big)}</div>{_head(x, hs - 10)}'
				f'<div class="pw">{_phone(x)}</div>{_cta(x)}</div>')
	ring = (f'<div class="layer" style="background:radial-gradient(circle at 18% 30%,{base.mix(x.p["accent"], bg, .72)} 0,transparent 38%),'
			f'radial-gradient(circle at 85% 85%,{base.mix(x.p["primary"], bg, .6)} 0,transparent 45%)"></div>')
	css = (_phone_css(x) + _head_css(x, ink=ink) + _stat_css(x, ink=ink)
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:30px}}.col{{flex-direction:column}}"
			 ".row{flex-direction:row}.txt{flex:1.1;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none}"
			 ".pw{flex:1;min-height:0;min-width:0;display:flex;justify-content:center;align-items:center}.row .pw{flex:.8}.cta{flex:none}")
	return ring + comp, css


# ---- 7. how it works (steps) ------------------------------------------------------------------------------------------
def steps_flow(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	steps = [s for s in (x.content.get("steps") or []) if str(s).strip()][:4]
	icons = (x.content.get("step_icons") or ["icon_check"] * 4)
	row = "".join(f'<div class="st"><div class="num">{x.el("icon_tile", 84, 84, text=icons[k % len(icons)], tone="primary")}</div>'
				  f'<b>{k + 1}. {esc(s)}</b></div>' + ('<div class="arr">→</div>' if k < len(steps) - 1 else "")
				  for k, s in enumerate(steps))
	flow = f'<div class="flow">{row}</div>'
	if x.wide:
		comp = f'<div class="wrap row"><div class="txt">{_top(x)}{_head(x, hs - 8)}{flow}</div><div class="pw">{_phone(x)}</div></div>'
	else:
		comp = f'<div class="wrap col">{_top(x)}{_head(x, hs - 10, align="center")}{flow}<div class="pw low">{_phone(x)}</div></div>'
	bg = x.bg
	css = (_phone_css(x) + _head_css(x)
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px {pad}px 0;display:flex;gap:30px}}.col{{flex-direction:column;align-items:center}}"
			 ".row{flex-direction:row}.txt{flex:1.2;display:flex;flex-direction:column;justify-content:center;gap:30px;padding-bottom:40px}.top{flex:none;align-self:flex-start}"
			 f".flow{{display:flex;align-items:flex-start;justify-content:center;gap:10px;flex:none}}.st{{display:flex;flex-direction:column;align-items:center;gap:12px;width:200px;text-align:center}}"
			 f".st b{{font:700 24px/1.2 var(--font-heading);color:{x.ink}}}.arr{{font:700 44px var(--font-body);color:{x.hl};margin-top:16px}}"
			 ".pw{flex:1;min-height:0;width:100%;display:flex;justify-content:center;overflow:hidden}.row .pw{flex:.7}"
			 ".pw.low{align-items:flex-start}.pw.low .phone{height:115cqh}")
	return comp, css


# ---- 8. floating chips ------------------------------------------------------------------------------------------------
def chips_cloud(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	chips = _chips(x, 8)
	left, right = chips[0::2], chips[1::2]

	def col(cs, side):
		return f'<div class="cc {side}">' + "".join(f'<div class="cw" style="--d:{k}">{c}</div>' for k, c in enumerate(cs)) + "</div>"

	more = f'<div class="more">{x.t("tagline")}</div>' if x.has("tagline") else ""
	stage = f'<div class="stage">{col(left, "l")}<div class="pw">{_phone(x)}</div>{col(right, "r")}</div>'
	if _side(x):
		comp = f'<div class="wrap row"><div class="txt">{_top(x, light=True)}{_head(x, hs)}{_cta(x, 380, 80)}</div>{stage}</div>'
	else:
		comp = f'<div class="wrap col">{_top(x, light=True)}{_head(x, hs, align="center")}{stage}{more}{_cta(x)}</div>'
	bg = x.p["primary_deep"]
	sky = _backdrop(x, f"linear-gradient(180deg,{bg}cc,{bg}66 50%,{bg}ee)") or (
		f'<div class="layer" style="background:radial-gradient(circle at 50% 60%,{base.mix(x.p["primary"], "#ffffff", .25)} 0,transparent 55%),'
		f'linear-gradient(180deg,{bg},{x.p["dark"]})"></div>')
	css = (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.82)", hl=x.p["accent"] if base.contrast(x.p["accent"], bg) > 2.2 else "#ffffff",
									 kick="#ffffff") + _chip_css(x)
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:26px}}.col{{flex-direction:column;align-items:center}}"
			 ".row{flex-direction:row}.txt{flex:1;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none;align-self:flex-start}"
			 ".stage{flex:1;min-height:0;width:100%;display:flex;align-items:center;justify-content:center;gap:18px}.row .stage{flex:1.1}"
			 ".pw{flex:1;min-width:0;height:100%;display:flex;justify-content:center}"
			 ".cc{flex:none;display:flex;flex-direction:column;justify-content:space-around;height:86%;gap:16px}.cc.l{align-items:flex-end}.cc.r{align-items:flex-start}"
			 ".cc.l .cw{transform:translateX(calc(var(--d) * -14px))}.cc.r .cw{transform:translateX(calc(var(--d) * 14px))}"
			 ".more{flex:none;font:600 26px var(--font-body);color:#fff;opacity:.85}.cta{flex:none}")
	return sky + comp, css


# ---- 9. editorial -----------------------------------------------------------------------------------------------------
def editorial(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	bg = "#f7f4ee" if x.look == "light" else x.bg
	ink = x.p["dark"] if x.look == "light" else x.ink
	items = (x.content.get("items") or [])[:4]
	nums = "".join(f'<div class="ed"><div class="n">{k + 1:02d}</div><div><b>{esc(it.get("title"))}</b>'
				   f'{f"<span>{esc(it.get(chr(116) + chr(101) + chr(120) + chr(116)))}</span>" if it.get("text") else ""}</div></div>'
				   for k, it in enumerate(items))
	text = f'<div class="txt">{_top(x)}{_head(x, hs - 8)}<div class="eds">{nums}</div>{_cta(x, 360, 80, tone="dark")}</div>'
	comp = f'<div class="wrap {"row" if (x.wide or not x.tall) else "col"}">{text}<div class="pw">{_phone(x)}</div></div>'
	rule = base.mix(ink, bg, .8)
	css = (_phone_css(x) + _head_css(x, ink=ink, hl=x.p["primary"] if base.contrast(x.p["primary"], bg) > 2.4 else ink, kick=base.mix(ink, bg, .4))
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px 0 {pad}px {pad}px;display:flex;gap:36px}}"
			 f".row{{flex-direction:row}}.col{{flex-direction:column;padding-right:{pad}px}}"
			 ".txt{flex:1.3;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none}"
			 ".head h1{font-weight:700;font-style:normal}"
			 f".ed{{display:flex;gap:22px;align-items:baseline;padding:16px 0;border-top:2px solid {rule}}}"
			 f".ed .n{{font:800 34px var(--font-heading);color:{x.p['primary'] if base.contrast(x.p['primary'], bg) > 2.4 else ink}}}"
			 f".ed b{{display:block;font:700 26px/1.2 var(--font-heading);color:{ink}}}.ed span{{display:block;font:400 19px/1.35 var(--font-body);color:{base.mix(ink, bg, .3)}}}"
			 ".pw{flex:1;min-height:0;min-width:0;display:flex;justify-content:flex-start;overflow:hidden}"
			 ".row .pw .phone{height:100cqh}.col .pw{justify-content:center}.col .txt{flex:none}.cta{flex:none}")
	return comp, css


# ---- 10. in context (photo or AI background) ----------------------------------------------------------------------------
def scene_device(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	bg = x.p["dark"]
	back = _backdrop(x, f"linear-gradient(180deg,{bg}e6 0,{bg}55 45%,{bg}aa 100%)") or (
		f'<div class="layer" style="background:radial-gradient(ellipse at 50% 100%,{base.mix(x.p["accent"], bg, .55)} 0,transparent 60%),'
		f'linear-gradient(180deg,{base.mix(x.p["primary"], bg, .6)},{bg})"></div>')
	if x.wide:
		comp = f'<div class="wrap row"><div class="txt">{_top(x, light=True)}{_head(x, hs)}{_cta(x, 380, 80)}</div><div class="pw">{_phone(x)}</div></div>'
	else:
		comp = f'<div class="wrap col">{_top(x, light=True)}{_head(x, hs, align="center")}<div class="pw">{_phone(x)}</div>{_cta(x)}</div>'
	css = (_phone_css(x) + _head_css(x, ink="#ffffff", soft="rgba(255,255,255,.85)",
									 hl=x.p["accent"] if base.contrast(x.p["accent"], bg) > 2.2 else "#ffffff", kick="#ffffff")
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:28px}}.col{{flex-direction:column;align-items:center}}"
			 ".row{flex-direction:row}.txt{flex:1.2;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none;align-self:flex-start}"
			 ".head{text-shadow:0 4px 24px rgba(0,0,0,.45)}.pw{flex:1;min-height:0;display:flex;justify-content:center;align-items:center}.row .pw{flex:.8}"
			 ".col .pw{width:100%}"
			 ".phone{box-shadow:0 60px 120px rgba(0,0,0,.6),0 0 0 2px rgba(255,255,255,.1) inset}.cta{flex:none}")
	return back + comp, css


# ---- 11. two screens --------------------------------------------------------------------------------------------------
def duo_screens(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	stage = f'<div class="stage"><div class="p1">{_phone(x, 0)}</div><div class="p2">{_phone(x, 1)}</div></div>'
	if x.wide:
		comp = f'<div class="wrap row"><div class="txt">{_top(x)}{_head(x, hs)}{_cta(x, 380, 80)}</div>{stage}</div>'
	else:
		comp = f'<div class="wrap col">{_top(x)}{_head(x, hs, align="center")}{stage}{_cta(x)}</div>'
	bg = x.bg
	deco = (f'<div class="layer" style="background:linear-gradient(180deg,transparent 45%,{base.mix(x.p["primary"], bg, .82)} 45%)"></div>')
	css = (_phone_css(x) + _head_css(x)
		   + f".post{{background:{bg}}}.wrap{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:28px}}.col{{flex-direction:column;align-items:center}}"
			 ".row{flex-direction:row}.txt{flex:1;display:flex;flex-direction:column;justify-content:center;gap:22px}.top{flex:none;align-self:flex-start}"
			 ".stage{flex:1;min-height:0;width:100%;display:flex;justify-content:center;align-items:center}.row .stage{flex:1.2}"
			 ".p1,.p2{height:92%;width:46%;display:flex;justify-content:center}.p1{transform:rotate(-6deg) translateX(8%);z-index:1}.p2{transform:rotate(6deg) translate(-8%,6%);z-index:2}"
			 ".cta{flex:none}")
	return deco + comp, css


LAYOUTS = {"ui_showcase": ui_showcase, "device_tilt": device_tilt, "pop_cards": pop_cards, "minimal_device": minimal_device,
		   "bold_promo": bold_promo, "stat_hero": stat_hero, "steps_flow": steps_flow, "chips_cloud": chips_cloud,
		   "editorial": editorial, "scene_device": scene_device, "duo_screens": duo_screens}

# The second set of directions (showcase_more.py) — same parts, twenty more compositions
from qtt_platform.design import showcase_more as _more  # noqa: E402

DIRECTIONS.update(_more.DIRECTIONS)
LAYOUTS.update(_more.LAYOUTS)
