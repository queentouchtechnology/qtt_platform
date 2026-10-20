"""
Showcase directions with other devices (PROJ-0012 S10 follow-up, TASK-2026-00220): a website or dashboard on a laptop,
an app on a tablet, and a before-and-after with two labelled screens. Same rules as showcase.py: the owner's real
screenshots, placed as they are inside devices drawn in CSS (never redrawn, nothing written on them); every size works
(square, portrait, story, 16:9, 3:2); the screenshot's part shown follows the owner's choice (top / middle / bottom /
whole — showcase.shot_img).
"""

from qtt_platform.design import base
from qtt_platform.design.layouts import Ctx, esc
from qtt_platform.design.showcase import _cta, _head, _head_css, _side, _sizes, _top, shot_img

DIRECTIONS = {
	"laptop_showcase": ("Website on a laptop", "Your website or dashboard on a laptop screen", {}),
	"tablet_showcase": ("On a tablet", "Your screen on a tablet, with your main points", {}),
	"before_after": ("Before and after", "Two of your screens, labelled Before and After", {"shots": 2}),
}


def _text(x: Ctx, *, align: str = "left", light: bool = False) -> str:
	hs, _p = _sizes(x)
	return f'<div class="dt">{_top(x, light=light)}{_head(x, hs, align=align)}{_cta(x)}</div>'


def _frame_css(x: Ctx, side: bool, pad: int, center: bool) -> str:
	return (f".dw{{position:absolute;inset:0;padding:{pad}px;display:flex;gap:{24 if x.wide else 34}px;"
			f"flex-direction:{'row' if side else 'column'};{'' if side else 'align-items:center;'}}}"
			f".dt{{flex:{'1' if side else 'none'};display:flex;flex-direction:column;justify-content:center;gap:{16 if x.wide else 24}px;min-width:0;"
			f"{'width:100%;' if not side else ''}}}"
			f".dv{{flex:{1.35 if side else 1};min-height:0;min-width:0;width:100%;display:flex;justify-content:center;align-items:center;container-type:size}}"
			f".top,.cta{{flex:none}}.dt .cta{{align-self:{'flex-start' if side or not center else 'center'}}}")


def _shot_css() -> str:
	# the same part-of-screen choices as the phone (showcase.shot_img): top / middle / bottom / whole (letterboxed on a
	# soft blurred copy of itself)
	return (".scrn{position:relative;overflow:hidden;background:#fff}"
			".scrn .shot{width:100%;height:100%;object-fit:cover;display:block}"
			".scrn .shot.pos-top{object-position:top center}.scrn .shot.pos-middle{object-position:center}.scrn .shot.pos-bottom{object-position:bottom center}"
			".scrn .shot.whole{object-fit:contain;position:relative;z-index:1}"
			".scrn .shot.blurfill{position:absolute;inset:0;object-fit:cover;filter:blur(22px) brightness(.9);transform:scale(1.12)}")


# ---- laptop ------------------------------------------------------------------------------------------------------------
def _laptop(x: Ctx, i: int = 0) -> str:
	return (f'<div class="lap" data-piece><div class="lid"><i class="cam"></i><div class="scrn">{shot_img(x, i)}</div></div>'
			f'<div class="deck"><i class="notch2"></i></div></div>')


def _laptop_css() -> str:
	# the lid holds a 16:10 screen; the deck is a little wider than the lid, like a real laptop seen from the front
	return (".lap{position:relative;width:min(100cqw,calc(100cqh * 1.48));display:flex;flex-direction:column;align-items:center;flex:none}"
			".lid{position:relative;box-sizing:border-box;width:86%;aspect-ratio:1.6;background:#0d0e13;border-radius:22px 22px 6px 6px;padding:3.2% 2.8% 3.6%;overflow:hidden;"
			"box-shadow:0 0 0 2px #2a2c36 inset,0 40px 80px rgba(0,0,0,.35)}"
			".lid .scrn{width:100%;height:100%;border-radius:6px}"
			".cam{position:absolute;top:1.3%;left:50%;width:1%;aspect-ratio:1;border-radius:50%;background:#2c2f3a;transform:translateX(-50%)}"
			".deck{position:relative;width:100%;height:auto;aspect-ratio:30;background:linear-gradient(#d9dbe1,#a9adb8);border-radius:0 0 30px 30px;"
			"box-shadow:0 26px 40px rgba(0,0,0,.28)}"
			".notch2{position:absolute;top:0;left:50%;width:16%;height:45%;transform:translateX(-50%);background:#8e929d;border-radius:0 0 12px 12px}")


def laptop_showcase(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	dark = x.look != "light"
	bg = x.p["dark"] if dark else "#f5f6f8"
	glow = (f'<div class="layer" style="background:radial-gradient(ellipse at 60% 70%,{base.mix(x.p["primary"], bg, .45)} 0,transparent 60%)"></div>')
	side = _side(x) and x.wide
	html = f'<div class="dw">{_text(x, align="left" if side else "center", light=dark)}<div class="dv">{_laptop(x)}</div></div>'
	ink = "#ffffff" if dark else x.p["dark"]
	css = (_frame_css(x, side, pad, center=not side) + _laptop_css() + _shot_css()
		   + _head_css(x, ink=ink, soft="rgba(255,255,255,.8)" if dark else base.mix(x.p["dark"], "#ffffff", .3), bg=bg)
		   + f".post{{background:{bg}}}")
	return glow + html, css


# ---- tablet ------------------------------------------------------------------------------------------------------------
def _tablet(x: Ctx, i: int = 0, landscape: bool = False) -> str:
	return f'<div class="tab {"land" if landscape else ""}" data-piece><div class="scrn">{shot_img(x, i)}</div></div>'


def _tablet_css() -> str:
	return (".tab{position:relative;box-sizing:border-box;aspect-ratio:.75;height:min(100cqh,calc(100cqw / .75));flex:none;background:#101117;"
			"border-radius:46px;padding:3.6%;box-shadow:0 0 0 2px #2b2d37 inset,0 44px 90px rgba(0,0,0,.38)}"
			".tab.land{aspect-ratio:1.333;height:min(100cqh,calc(100cqw / 1.333))}"
			".tab .scrn{width:100%;height:100%;border-radius:20px}")


def tablet_showcase(x: Ctx, v: dict) -> tuple[str, str]:
	hs, pad = _sizes(x)
	bg = x.p["light"] if x.look == "light" else x.bg
	ink = x.p["dark"] if x.look == "light" else x.ink
	side = _side(x)
	items = [i for i in (x.content.get("items") or []) if str(i.get("title") or "").strip()][: (2 if x.wide else 3)]
	pts = "".join(f'<div class="tp">{x.el("icon_tile", 48, 48, text=it.get("icon") or "icon_check", tone="primary")}<b>{esc(it.get("title"))}</b></div>'
				  for it in items)
	text = (f'<div class="dt">{_top(x, light=x.look != "light")}{_head(x, hs, align="left" if side else "center")}'
			f'{f"<div class=tps>{pts}</div>" if pts else ""}{_cta(x)}</div>')
	html = f'<div class="dw">{text}<div class="dv">{_tablet(x, landscape=x.wide)}</div></div>'
	css = (_frame_css(x, side, pad, center=not side) + _tablet_css() + _shot_css() + _head_css(x, ink=ink, bg=bg)
		   + f".post{{background:{bg}}}.tps{{display:flex;flex-direction:column;gap:12px}}"
			 f".tp{{display:flex;align-items:center;gap:14px}}.tp svg{{flex:none}}.tp b{{font:700 {20 if x.wide else 26}px/1.2 var(--font-heading);color:{ink}}}"
			 + ("" if side else ".tps{align-self:center}"))
	return html, css


# ---- before and after ------------------------------------------------------------------------------------------------
def before_after(x: Ctx, v: dict) -> tuple[str, str]:
	"""Two of the owner's screens side by side: Before (muted) → After (lit), with their labels (the owner's words, or
	Before / After)."""
	hs, pad = _sizes(x)
	bg = x.p["dark"] if x.look != "light" else "#f3f4f7"
	ink = "#ffffff" if x.look != "light" else x.p["dark"]
	before = esc(x.content.get("before_label") or "Before")
	after = esc(x.content.get("after_label") or "After")
	accent = x.p["accent"] if base.contrast(x.p["accent"], bg) > 2.2 else x.p["primary"]
	pair = (f'<div class="pair"><div class="sd b"><span class="lb">{before}</span><div class="ph pw2">{_mini_phone(x, 0)}</div></div>'
			'<div class="arrow">→</div>'
			f'<div class="sd a"><span class="lb">{after}</span><div class="ph pw2">{_mini_phone(x, 1)}</div></div></div>')
	side = x.wide
	html = f'<div class="dw">{_text(x, align="left" if side else "center", light=x.look != "light")}<div class="dv">{pair}</div></div>'
	css = (_frame_css(x, side, pad, center=not side) + _shot_css() + _head_css(x, ink=ink, bg=bg) + f".post{{background:{bg}}}"
		   ".pair{width:100%;height:100%;display:flex;align-items:center;justify-content:center;gap:2%}"
		   ".sd{flex:1;height:100%;display:flex;flex-direction:column;align-items:center;gap:14px;min-width:0}"
		   ".pw2{flex:1;min-height:0;width:100%;display:flex;justify-content:center;container-type:size}"
		   f".lb{{flex:none;font:800 {20 if x.wide else 28}px var(--font-body);letter-spacing:2px;text-transform:uppercase;padding:8px 20px;border-radius:999px}}"
		   f".b .lb{{background:{base.mix(ink, bg, .8)};color:{base.mix(ink, bg, .25)}}}.a .lb{{background:{accent};color:{base.on(accent, dark=x.p['dark'])}}}"
		   ".b .mph{filter:saturate(.35) brightness(.92);opacity:.85}"
		   f".arrow{{flex:none;font:900 {44 if x.wide else 64}px var(--font-heading);color:{accent}}}"
		   ".mph{position:relative;box-sizing:border-box;aspect-ratio:.49;height:min(100cqh,calc(100cqw / .49));flex:none;border-radius:44px;background:#0c0d12;"
		   "padding:10px;box-shadow:0 34px 60px rgba(0,0,0,.32)}.mph .scrn{width:100%;height:100%;border-radius:36px}")
	return html, css


def _mini_phone(x: Ctx, i: int) -> str:
	return f'<div class="mph" data-piece><div class="scrn">{shot_img(x, i)}</div></div>'


LAYOUTS = {"laptop_showcase": laptop_showcase, "tablet_showcase": tablet_showcase, "before_after": before_after}
