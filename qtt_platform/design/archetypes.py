"""
The layouts the template library is built from (PROJ-0011 C) — each one follows a family of the owner's reference
posts (docs/design/*-post-references.md). layout(ctx, variant) → (body, css) at 1080 wide; flex / grid only, so every
format (square, portrait, story) and any text length works. Variant keys each layout understands are listed in VARIANTS.
"""

from qtt_platform.design import base
from qtt_platform.design.layouts import Ctx, esc


# ---- shared parts ---------------------------------------------------------------------------------------------------
def _band(x: Ctx, kind: str, *, colour: str | None = None) -> tuple[str, str]:
	"""The bottom band: pillars (icon + word), contact (phone, website…) or a tagline; '' when there's nothing for it."""
	c = x.content
	bg = colour or x.p["dark"]
	fg = base.on(bg, dark=x.p["dark"])
	css = (f".band{{background:{bg};color:{fg};display:flex;align-items:center;gap:30px;padding:26px 56px;min-height:120px}}"
		   f".band .tag{{flex:1;font:500 22px/1.3 var(--font-body)}}.band .tag em{{color:{x.p['accent'] if base.contrast(x.p['accent'], bg) > 2.4 else fg}}}"
		   f".band .pil{{display:flex;flex-direction:column;align-items:center;gap:8px;font:700 15px var(--font-body);letter-spacing:1px;"
		   f"padding-left:30px;border-left:1px solid {base.mix(bg, fg, .25)};text-transform:uppercase;text-align:center}}"
		   f".band .ct{{display:flex;align-items:center;gap:12px;font:700 24px var(--font-heading)}}.band .ct small{{display:block;font:500 15px var(--font-body);opacity:.8}}"
		   f".band .ct + .ct{{padding-left:26px;border-left:1px solid {base.mix(bg, fg, .25)}}}")
	white = {**x.p, "accent": fg, "on_accent": bg}
	if kind == "pillars" and c.get("pillars"):
		tag = f'<div class="tag">{x.m("tagline")}</div>' if x.has("tagline") else '<div class="tag"></div>'
		pils = "".join(f'<div class="pil">{x.el(i, 40, 40, palette=white)}<span>{esc(t)}</span></div>' for i, t in c["pillars"][:5])
		return f'<div class="band">{tag}{pils}</div>', css
	if kind in ("contact", "pillars"):
		bits = x.contact_bits()[:3]
		if not bits:
			return "", ""
		cts = "".join(f'<div class="ct">{x.el("icon_tile", 54, 54, text=i, tone="primary")}<div>{esc(v)}</div></div>' for i, v in bits)
		return f'<div class="band">{cts}</div>', css
	if kind == "tagline" and x.has("tagline"):
		return f'<div class="band"><div class="tag" style="text-align:center;font-size:26px">{x.m("tagline")}</div></div>', css
	return "", ""


def _rows(x: Ctx, *, tile: str = "primary", size: int = 66, limit: int = 5) -> str:
	return "".join(
		f'<div class="row">{x.el("icon_tile", size, size, text=it.get("icon") or "icon_check", tone=tile)}'
		f'<div><b>{esc(it.get("title"))}</b>{f"<span>{esc(it.get(chr(116) + chr(101) + chr(120) + chr(116)))}</span>" if it.get("text") else ""}</div></div>'
		for it in (x.content.get("items") or [])[:limit])


def _rows_css(x: Ctx, size: int = 66) -> str:
	return (f".row{{display:flex;gap:18px;align-items:center;margin:0 0 16px}}.row b{{display:block;font:700 23px/1.2 var(--font-heading);color:{x.ink}}}"
			f".row span{{display:block;font:400 17px/1.35 var(--font-body);color:{x.soft}}}.row svg{{flex:0 0 {size}px}}")


# ---- 1. hero split (technology: benefits + a device or photo, a band) -------------------------------------------------
def hero_split(x: Ctx, v: dict) -> tuple[str, str]:
	dark = x.look != "light"
	bgp = v.get("pattern") or ("glow_rings" if dark else "sweep")
	hero = v.get("hero", "device")
	band, band_css = _band(x, v.get("band", "pillars"))
	ph = x.photo(0)
	stack = x.tall
	if hero == "device":
		lw, lh = (800, 510) if stack else (400, 255)
		screen = f'<div class="screen ph" style="background-image:url({esc(ph)})"></div>' if ph else ""
		tiles = "".join(f'<div class="chip c{k}">{x.el("icon_tile", s, s, text=i, tone=t)}</div>'
						for k, (i, s, t) in enumerate((("icon_cloud", 96, "primary"), ("icon_shield", 84, "primary"), (v.get("chip3", "icon_chart"), 74, "accent"))))
		hero_html = f'<div class="dev"><div class="lap">{x.el("device_laptop", lw, lh)}{screen}</div>{tiles}</div>'
		hero_css = (f".dev{{position:relative;width:{lw + 60}px;height:{lh + 220}px}}.lap{{position:absolute;left:30px;bottom:30px;width:{lw}px;height:{lh}px}}"
					f".screen{{position:absolute;left:{lw * .115:.0f}px;top:{lh * .86 * .06:.0f}px;width:{lw * .77:.0f}px;height:{lh * .86 * .86:.0f}px;border-radius:3px}}"
					f".chip{{position:absolute;filter:drop-shadow(0 12px 22px rgba(0,0,0,.25))}}.c0{{left:70px;top:10px}}.c1{{right:20px;top:60px}}.c2{{right:0;bottom:6px}}")
	else:
		fr = base.FRAMES.get(v.get("frame", "rounded"), "")
		hero_html = f'<div class="photo ph" style="background-image:url({esc(ph)});{fr}"></div>' if ph else ""
		hero_css = f".photo{{width:{'100%' if stack else '440px'};height:{'560px' if stack else '560px'};box-shadow:0 24px 50px rgba(0,0,0,.22)}}"
	kicker = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	sub = f'<div class="sub fit" data-fit>{x.m("subline")}</div>' if x.has("subline") else ""
	cta = f'<div class="cta">{x.el("cta", 420, 74, text=x.content.get("cta"), tone="primary")}</div>' if x.has("cta") else ""
	dots = "" if stack else f'<div class="layer">{x.pattern("dot_corners", transparent=True)}</div>'  # never behind the text
	body = (f'<div class="layer">{x.pattern(bgp)}</div>{dots}'
			f'<div class="wrap"><div class="top">{x.logo(84)}</div><div class="main">'
			f'<div class="text">{kicker}<h1 class="h fit" data-fit>{x.m("headline")}</h1><div class="rule"></div>{sub}'
			f'<div class="rows">{_rows(x)}</div>{cta}</div><div class="hero">{hero_html}</div></div>{band}</div>')
	css = (f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column}}.top{{padding:48px 56px 0}}"
		   f".main{{flex:1;display:{'flex;flex-direction:column' if stack else 'grid;grid-template-columns:540px 1fr'};gap:24px;padding:28px 56px 30px;min-height:0}}"
		   f".rows{{min-height:0;overflow:hidden}}"
		   f".text{{display:flex;flex-direction:column;min-height:0}}.kick{{font:700 22px var(--font-body);letter-spacing:3px;text-transform:uppercase;color:{x.hl};margin-bottom:10px}}"
		   f"h1{{font-weight:800;font-size:{88 if stack else 74}px;line-height:1.02;text-transform:uppercase;max-height:{420 if stack else 360}px}}h1 em{{color:{x.hl}}}"
		   f".rule{{width:90px;height:5px;border-radius:3px;background:{x.hl};margin:20px 0}}"
		   f".sub{{font:400 25px/1.4 var(--font-body);color:{x.soft};max-height:110px;margin-bottom:22px}}.sub em{{color:{x.hl};font-weight:700}}"
		   f".hero{{display:flex;align-items:center;justify-content:center;min-height:0;{'flex:1' if stack else ''}}}.cta{{margin-top:6px}}"
		   + _rows_css(x) + hero_css + band_css)
	return body, css


# ---- 2. center hero (agency / food: a big centred title, the photo in the middle, notes around it) ------------------
def center_hero(x: Ctx, v: dict) -> tuple[str, str]:
	bgp = v.get("pattern", "spotlight")
	script = v.get("script", "Kaushan Script")
	ph = x.photo(0)
	fr = base.FRAMES.get(v.get("frame", "circle"), "")
	white = {**x.p, "accent": x.ink}
	kicker = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	note = (f'<div class="note n1"><div class="hand">{x.t("tagline")}</div>{x.el("dashed_arrow", 170, 150, palette=white)}</div>'
			if x.has("tagline") else "")
	badge = (f'<div class="note n2">{x.el("speech_cloud", 250, 220, text=x.content.get("badge"), tone="primary")}</div>' if x.has("badge") else "")
	price = (f'<div class="note n3">{x.el("scribble_circle", 230, 150, text=x.content.get("price"), palette=white)}'
			 f'<div class="pl">{x.t("price_label")}</div></div>' if x.has("price") else "")
	foot_left = "".join(f'<div class="fl">{esc(val)}</div>' for _, val in x.contact_bits()[:2])
	cta = x.el("cta", 330, 80, text=x.content.get("cta") or "", tone="accent") if x.has("cta") else ""
	body = (f'<div class="layer">{x.pattern(bgp)}</div>'
			+ (f'<div class="layer">{x.pattern("rays", transparent=True)}</div>' if v.get("rays", True) else "")
			+ f'<div class="wrap"><div class="top">{x.logo(78)}</div>{kicker}<h1 class="fit" data-fit>{x.m("headline")}</h1>'
			f'<div class="mid"><div class="ph hero" style="background-image:url({esc(ph)});{x.photo_style(fr)}"></div>{note}{badge}{price}</div>'
			f'<div class="foot"><div>{foot_left}</div>{cta}</div></div>')
	hs = 150 if not x.tall else 170
	css = (f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:40px 56px 46px}}"
		   f".top{{align-self:flex-start}}.kick{{font:400 64px '{script}', var(--font-heading);color:{x.p['accent'] if x.look != 'light' else x.hl};margin-top:-6px;text-align:center}}"
		   f"h1{{font:400 {hs}px/1 '{script}', var(--font-heading);color:{x.ink};text-align:center;width:100%;max-height:{hs * 1.25:.0f}px;white-space:nowrap}}h1 em{{color:{x.p['accent']}}}"
		   f".mid{{flex:1;position:relative;width:100%;display:flex;align-items:center;justify-content:center;min-height:0}}"
		   f".hero{{width:{620 if x.tall else 560}px;height:{620 if x.tall else 520}px;max-height:100%;box-shadow:0 30px 60px rgba(0,0,0,.35)}}"
		   f".note{{position:absolute}}.n1{{left:0;top:12%;text-align:center}}.hand{{font:700 42px/1.05 'Caveat', var(--font-heading);color:{x.ink};transform:rotate(-8deg);margin-bottom:6px}}"
		   f".n2{{right:-10px;top:4%}}.n3{{right:0;bottom:6%;text-align:center}}.pl{{font:700 22px var(--font-body);color:{x.ink}}}"
		   f".foot{{width:100%;display:flex;align-items:flex-end;justify-content:space-between}}.fl{{font:800 38px var(--font-heading);color:{x.ink}}}"
		   f".fl + .fl{{font:500 20px var(--font-body);opacity:.85}}")
	return body, css


# ---- 3. listing (real estate / product details: photo, brush banners, specs, price, a strip, amenities) ---------------
def listing(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	red = v.get("swipe", "#dc2626")
	ph = x.photo(0)
	strip = "".join(f'<div class="sp ph" style="background-image:url({esc(x.photo(k + 1))})"><span>{esc(lbl)}</span></div>'
					for k, lbl in enumerate((c.get("list") or [])[:4]))
	ams = "".join(f'<div class="am">{x.el(i, 34, 34, palette={**x.p, "accent": "#ffffff"})}<span>{esc(t)}</span></div>' for i, t in (c.get("pillars") or [])[:5])
	place = x.el("brush_banner", 470, 88, text=c.get("place"), tone="primary") if x.has("place") else ""
	kick = (f'<div class="sw">{x.el("brush_swipe", 420, 112, palette={**x.p, "primary": red, "on_primary": "#ffffff"}, tone="primary")}'
			f'<span>{x.t("kicker")}</span></div>') if x.has("kicker") else ""
	price = (f'<div class="pr">{x.el("brush_badge", 440, 150, tone="accent")}<div class="pt"><small>{x.t("price_label")}</small>'
			 f'<b class="fit" data-fit>{x.t("price")}</b></div></div>') if x.has("price") else ""
	phone = (f'<div class="call">{x.el("icon_tile", 64, 64, text="icon_phone", tone="accent")}<span>{x.t("phone")}</span></div>' if x.has("phone") else "")
	body = (f'<div class="wrap"><div class="upper"><div class="house ph" style="background-image:url({esc(ph)})"><div class="lg">{x.logo(70, light=False)}</div></div>'
			f'<div class="right">{place}{kick}<div class="specs">{_rows(x, size=72, limit=4)}</div>{price}</div></div>'
			+ (f'<div class="strip">{strip}</div>' if strip else "") + (f'<div class="ams">{ams}</div>' if ams else "")
			+ f'<div class="foot"><div><div class="nm">{x.t("business")}</div><div class="sv">{x.t("tagline")}</div></div>{phone}</div></div>')
	css = (f".post{{background:#ffffff;color:{x.p['dark']}}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column}}"
		   f".upper{{flex:1;display:grid;grid-template-columns:{'1fr' if x.tall else '540px 1fr'};min-height:0}}"
		   f".house{{position:relative;min-height:{'560px' if x.tall else '0'}}}.lg{{position:absolute;left:26px;top:24px;background:rgba(255,255,255,.93);padding:10px 16px;border-radius:14px}}"
		   f".right{{padding:22px 24px 10px;display:flex;flex-direction:column;align-items:flex-start;min-height:0}}"
		   f".sw{{position:relative;margin-top:-4px}}.sw span{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font:400 60px 'Kaushan Script', var(--font-heading);color:#fff}}"
		   f".specs{{margin-top:14px}}.pr{{position:relative;margin-top:4px}}.pt{{position:absolute;inset:6px 40px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#b91c1c}}"
		   f".pt small{{font:700 24px var(--font-body);color:{x.p['dark']}}}.pt b{{font:900 62px/1.05 var(--font-heading);max-width:100%;white-space:nowrap}}"
		   f".strip{{display:flex;gap:12px;padding:14px 20px}}.sp{{flex:1;height:{220 if x.tall else 170}px;border-radius:14px;position:relative}}"
		   f".sp span{{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);background:{x.p['primary']};color:{x.p['on_primary']};font:700 16px var(--font-body);padding:4px 16px;border-radius:20px;white-space:nowrap}}"
		   f".ams{{background:{x.p['primary']};display:flex;justify-content:space-around;align-items:center;min-height:74px;padding:0 10px}}"
		   f".am{{display:flex;gap:10px;align-items:center;color:{x.p['on_primary']};font:600 16px var(--font-body)}}"
		   f".foot{{background:{x.p['dark']};display:flex;align-items:center;justify-content:space-between;padding:22px 40px;min-height:140px}}"
		   f".nm{{font:400 46px 'Kaushan Script', var(--font-heading);color:{x.p['accent']}}}.sv{{color:#fff;font:500 17px var(--font-body)}}"
		   f".call{{display:flex;align-items:center;gap:14px;color:#fff;font:800 50px var(--font-heading)}}"
		   + _rows_css(x, 72).replace(f"color:{x.ink}", f"color:{x.p['dark']}").replace(f"color:{x.soft}", "color:#475569")
		   + ".row b{font-size:34px}")
	return body, css


# ---- 4. event (worship / concert / seminar: stage lights, big gold title, who, when, where, QR) ----------------------
def event(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ts = v.get("title_style", "gold")
	title_face = v.get("title_face", "Bebas Neue")
	ph = x.photo(0)
	person = (f'<div class="who">' + (f'<div class="pic ph" style="background-image:url({esc(ph)});{base.FRAMES["circle"]}"></div>' if ph and v.get("speaker_photo", True) else "")
			  + (f'<small>{x.t("role")}</small>' if x.has("role") else "") + f'<b>{x.t("person")}</b></div>') if x.has("person") else ""
	date = f'<div class="date">{x.el("date_block", 150, 170, text=c.get("date"), tone="primary")}</div>' if x.has("date") else "<div></div>"
	qr = (f'<div class="qr">{esc(c.get("qr_label") or "Scan for location")}<br>{x.el("qr", 150, 150, text=c.get("qr"))}</div>' if x.has("qr") else "<div></div>")
	body = (f'<div class="layer">{x.pattern(v.get("pattern", "stage_glow"), base_="dark")}</div>'
			+ (f'<div class="layer ph bgph" style="background-image:url({esc(x.photo(1) if len(x.photos) > 1 else "")})"></div>'
			   f'<div class="layer" style="background:linear-gradient(180deg,rgba(0,0,0,.55),rgba(0,0,0,.25) 40%,rgba(0,0,0,.7))"></div>' if len(x.photos) > 1 else "")
			+ f'<div class="wrap"><div class="top">{x.logo(70, light=True)}</div><h1 class="fit" data-fit>{x.m("headline")}</h1>'
			f'{person}<div class="time">{x.t("time")}</div><div class="place">{x.t("place")}</div>'
			f'<div class="addr">{x.t("address")}</div><div class="low">{date}{qr}</div></div>')
	css = (f".post{{background:{x.p['dark']};color:#fff}}.bgph{{opacity:.5}}h1{{margin-top:16px}}"
		   f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:40px 50px 44px;text-align:center}}"
		   f".top{{align-self:flex-start}}h1{{font:400 {190 if x.tall else 160}px/0.92 '{title_face}', var(--font-heading);letter-spacing:6px;text-transform:uppercase;"
		   f"max-height:{420 if x.tall else 320}px;width:100%;{base.text_style(ts, x.p)}}}"
		   f".who{{margin-top:auto;display:flex;flex-direction:column;align-items:center}}.pic{{width:{300 if x.tall else 200}px;height:{300 if x.tall else 200}px;margin-bottom:14px;"
		   f"border:5px solid {x.p['accent']}}}.who small{{font:600 16px var(--font-body);letter-spacing:6px;opacity:.85;text-transform:uppercase}}.who b{{font:700 40px 'Cinzel', var(--font-heading)}}"
		   f".time{{margin-top:14px;font:800 {96 if x.tall else 84}px var(--font-heading);{base.text_style('gold', x.p)}}}"
		   f".place{{font:700 30px var(--font-heading);letter-spacing:3px;text-transform:uppercase}}.addr{{font:400 38px 'Bebas Neue', var(--font-heading);letter-spacing:2px;opacity:.95}}"
		   f".low{{width:100%;display:flex;justify-content:space-between;align-items:flex-end;margin-top:{'auto' if x.tall else '10px'}}}"
		   f".qr{{font:400 22px 'Bebas Neue', var(--font-heading);letter-spacing:1px}}")
	return body, css


# ---- 5. tribute (rest in peace: mono portrait, small caps, a script name, years, lines) -----------------------------
def tribute(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	ink = "#ffffff"
	body = (f'<div class="layer">{x.pattern("spotlight", base_="dark")}</div>'
			f'<div class="wrap"><div class="top">{x.logo(64, light=True)}</div>'
			f'<div class="pic ph" style="background-image:url({esc(ph)});{base.FRAMES["mono"]}"></div>'
			f'<div class="rip"><i></i>{x.t("kicker") or "REST IN PEACE"}<i></i></div><div class="name fit" data-fit>{x.t("person")}</div>'
			f'<div class="role">{x.t("role")}</div><div class="yrs">{x.t("years")}</div><div class="q">{x.t("quote")}</div>'
			f'<div class="orn">{x.el("flourish", 260, 30, palette={**x.p, "accent": "#cbd5e1"})}</div></div>')
	css = (f".post{{background:#0a0a0a;color:{ink}}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:44px 60px 50px;text-align:center}}"
		   f".top{{align-self:flex-end}}.pic{{width:{620 if x.tall else 470}px;flex:1;max-height:{900 if x.tall else 560}px;min-height:300px;"
		   f"-webkit-mask-image:linear-gradient(180deg,#000 70%,transparent);mask-image:linear-gradient(180deg,#000 70%,transparent)}}"
		   f".rip{{display:flex;align-items:center;gap:22px;font:400 22px 'Cinzel', var(--font-heading);letter-spacing:8px;margin-top:-20px}}.rip i{{width:90px;height:1px;background:#cbd5e1}}"
		   f".name{{font:400 120px/1.1 'Great Vibes', var(--font-heading);width:100%;max-height:150px;white-space:nowrap}}"
		   f".role{{font:400 22px 'Cinzel', var(--font-heading);letter-spacing:6px;text-transform:uppercase}}.yrs{{font:500 24px var(--font-body);margin-top:10px;opacity:.9}}"
		   f".q{{font:italic 400 26px/1.45 Georgia,serif;margin-top:18px;max-width:760px;opacity:.9}}.orn{{margin-top:16px}}")
	return body, css


# ---- 6. quote / tip (text only: a big line on a pattern, the logo, a small footer) ----------------------------------
def quote_tip(x: Ctx, v: dict) -> tuple[str, str]:
	bgp = v.get("pattern", "corner_circles")
	mark = x.el("quote", 140, 120, tone="primary" if x.look == "light" else "accent") if v.get("quote_mark", True) else ""
	kicker = f'<div class="pill">{x.el("pill", 300, 60, text=x.content.get("kicker"), tone="accent")}</div>' if x.has("kicker") else ""
	foot = " · ".join(esc(val) for _, val in x.contact_bits()[:2])
	body = (f'<div class="layer">{x.pattern(bgp)}</div><div class="wrap"><div class="top">{x.logo(70)}</div>{kicker}'
			f'<div class="mid">{mark}<div class="big fit" data-fit>{x.m("headline")}</div>'
			+ (f'<div class="sub">{x.m("subline")}</div>' if x.has("subline") else "") + f'</div><div class="foot">{foot}</div></div>')
	css = (f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:56px 76px}}.pill{{margin-top:30px}}"
		   f".mid{{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0}}"
		   f".big{{font:800 {78 if x.tall else 66}px/1.15 var(--font-heading);max-height:{900 if x.tall else 560}px}}.big em{{color:{x.hl}}}"
		   f".sub{{font:400 28px/1.45 var(--font-body);color:{x.soft};margin-top:26px}}.foot{{font:600 22px var(--font-body);color:{x.soft}}}")
	return body, css


# ---- 7. problem → solution (a photo with pain chips, then the fix and its benefits) ---------------------------------
def problem_solution(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	warn = v.get("warn", "#dc2626")
	chips = "".join(f'<div class="chip k{k}">{x.el("icon_tile", 46, 46, text=it.get("icon") or "icon_bolt", palette={**x.p, "accent": warn, "on_accent": "#fff"})}'
					f'<span>{esc(it.get("title"))}</span></div>' for k, it in enumerate((c.get("problems") or [])[:5]))
	bens = "".join(f'<div class="ben">{x.el(it.get("icon") or "icon_check", 54, 54, tone="primary")}<span>{esc(it.get("title"))}</span></div>'
				   for it in (c.get("items") or [])[:5])
	band, band_css = _band(x, "contact")
	body = (f'<div class="layer ph" style="background-image:url({esc(ph)})"></div>'
			f'<div class="layer" style="background:linear-gradient(90deg,{x.p["dark"]} 0%,{x.p["dark"]}ee 38%,{x.p["dark"]}55 70%,transparent)"></div>'
			f'<div class="wrap"><div class="top">{x.logo(76, light=True)}</div><div class="up"><div class="txt">'
			f'<h1 class="fit" data-fit>{x.m("headline")}</h1><div class="rule"></div><div class="sub fit" data-fit>{x.m("subline")}</div></div>'
			f'<div class="chips">{chips}</div></div><div class="panel"><div class="sol fit" data-fit>{x.m("kicker")}</div><div class="bens">{bens}</div></div>{band}</div>')
	css = (f".post{{color:#fff}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column}}.top{{padding:44px 56px 0}}"
		   f".up{{flex:1;display:grid;grid-template-columns:{'1fr' if x.tall else '520px 1fr'};padding:22px 56px;min-height:0}}"
		   f"h1{{font:800 {96 if x.tall else 80}px/1 var(--font-heading);text-transform:uppercase;max-height:{460 if x.tall else 350}px}}h1 em{{color:{warn}}}"
		   f".rule{{width:90px;height:5px;background:{x.p['accent']};margin:18px 0}}.sub{{font:400 24px/1.4 var(--font-body);opacity:.88;max-height:130px}}"
		   f".chips{{position:relative;min-height:{360 if x.tall else 0}px}}.chip{{position:absolute;display:flex;align-items:center;gap:12px;background:#fff;color:{x.p['dark']};"
		   f"padding:10px 18px 10px 10px;border-radius:14px;font:800 17px var(--font-heading);text-transform:uppercase;box-shadow:0 10px 24px rgba(0,0,0,.3);max-width:280px}}"
		   f".k0{{left:10%;top:6%}}.k1{{right:0;top:22%}}.k2{{left:0;top:44%}}.k3{{right:4%;top:62%}}.k4{{left:18%;top:80%}}"
		   f".panel{{margin:0 40px 26px;background:#fff;border-radius:22px;padding:22px 26px;color:{x.p['dark']};box-shadow:0 18px 40px rgba(0,0,0,.3)}}"
		   f".sol{{font:800 34px var(--font-heading);text-align:center;text-transform:uppercase;max-height:50px;white-space:nowrap}}.sol em{{color:{x.p['primary']}}}"
		   f".bens{{display:flex;justify-content:space-around;margin-top:14px}}.ben{{display:flex;flex-direction:column;align-items:center;gap:8px;"
		   f"font:700 16px var(--font-body);text-transform:uppercase;text-align:center;max-width:170px}}" + band_css)
	return body, css


# ---- 8. circles with labels (coaching / services: 4 coloured circles, a photo, a wave band with the phone) ----------
def circles_labels(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	cols = v.get("colours") or [x.p["primary"], x.p["accent"], x.p["secondary"], x.p["primary_deep"]]
	circles = "".join(f'<div class="ci">{x.el("label_circle", 210, 260, text=(it.get("icon") or "icon_check") + "|" + (it.get("title") or ""), tone="primary", palette={**x.p, "primary": cols[k % 4], "on_primary": base.on(cols[k % 4])})}</div>'
					  for k, it in enumerate((c.get("items") or [])[:4]))
	ph = x.photo(0)
	brush = (f'<div class="br">{x.el("brush_swipe", 470, 150, tone="accent")}<span class="fit" data-fit>{x.m("subline")}</span></div>' if x.has("subline") else "")
	phone = (f'<div class="call">{x.el("icon_tile", 74, 74, text="icon_phone", tone="accent")}<div><small>{esc(c.get("cta") or "Contact us")}</small>{x.t("phone")}</div></div>'
			 if x.has("phone") else "")
	body = (f'<div class="layer">{x.pattern("corner_blobs", base_="light")}</div><div class="wrap"><div class="top">{x.logo(70, light=False)}</div>'
			f'<h1 class="fit" data-fit>{x.m("headline")}</h1><div class="ul">{x.el("brush_underline", 520, 34, tone="accent")}</div>'
			f'<div class="circles">{circles}</div><div class="low"><div class="ph pic" style="background-image:url({esc(ph)});{base.FRAMES["blob"]}"></div>'
			f'<div class="side">{brush}</div></div></div>'
			f'<div class="wb">{x.el("wave_band", 1080, 230, tone="primary", palette={**x.p, "primary": x.p["dark"]})}</div><div class="wbt">{phone}</div>')
	css = (f".post{{background:#fffdf7;color:{x.p['dark']}}}.wrap{{position:absolute;left:0;right:0;top:0;bottom:170px;display:flex;flex-direction:column;align-items:center;padding:34px 40px 0}}"
		   f".top{{align-self:flex-start}}h1{{font:800 {104 if x.tall else 92}px/1 var(--font-heading);text-align:center;color:{x.p['dark']};max-height:{250 if x.tall else 200}px;width:100%}}"
		   f"h1 em{{color:{x.p['primary']}}}.ul{{margin-top:-6px}}.circles{{display:flex;gap:28px;justify-content:center;margin-top:16px}}"
		   f".low{{flex:1;width:100%;display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:center;min-height:0}}"
		   f".pic{{height:100%;max-height:{620 if x.tall else 330}px;min-height:200px}}.br{{position:relative}}.br span{{position:absolute;inset:26px 50px;display:flex;"
		   f"align-items:center;justify-content:center;text-align:center;font:400 36px/1.05 'Kaushan Script', var(--font-heading);color:{x.p['on_accent']}}}"
		   f".wb{{position:absolute;left:0;right:0;bottom:0;height:230px}}.wbt{{position:absolute;left:0;right:0;bottom:0;height:170px;display:flex;align-items:center;justify-content:center}}"
		   f".call{{display:flex;align-items:center;gap:20px;color:#fff;font:800 66px var(--font-heading)}}.call small{{display:block;font:400 30px 'Kaushan Script', var(--font-heading);color:{x.p['accent']}}}")
	return body, css


# ---- 9. question rows (coaching "is your child…": pastel pill rows, a promise band, a big call pill) -----------------
def question_rows(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	cols = v.get("colours") or [x.p["primary"], x.p["accent"], x.p["secondary"], x.p["primary_deep"]]
	rows = "".join(
		f'<div class="q" style="background:{base.mix(cols[k % 4], "#ffffff", .82)}">{x.el("icon_tile", 84, 84, text=it.get("icon") or "icon_check", tone="primary", palette={**x.p, "primary": cols[k % 4], "on_primary": base.on(cols[k % 4])})}'
		f'<div><small>{esc(it.get("text"))}</small><b style="color:{base.mix(cols[k % 4], x.p["dark"], .35)}">{esc(it.get("title"))}</b></div></div>'
		for k, it in enumerate((c.get("items") or [])[:4]))
	ph = x.photo(0)
	call = (f'<div class="call"><span class="ic">{x.el("icon_phone", 54, 54, palette={**x.p, "accent": "#fff"})}</span><span class="cn">{esc(c.get("cta") or "Call now")}</span>'
			f'<b>{x.t("phone")}</b></div>' if x.has("phone") else "")
	body = (f'<div class="wrap"><div class="head">{x.el("brush_banner", 620, 120, tone="accent")}<span class="fit" data-fit>{x.m("headline")}</span></div>'
			f'<div class="mid"><div class="qs">{rows}</div><div class="ph pic" style="background-image:url({esc(ph)});{base.FRAMES["arch"]}"></div></div>'
			f'<div class="band"><div class="fit" data-fit>{x.m("subline")}</div></div><div class="promise fit" data-fit>{x.m("kicker")}</div>{call}'
			f'<div class="lg">{x.logo(56, light=False)}</div></div>')
	css = (f".post{{background:#fffdf7;color:{x.p['dark']}}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:30px 30px 24px}}"
		   f".head{{position:relative;align-self:flex-start}}.head span{{position:absolute;inset:16px 34px;display:flex;align-items:center;font:800 58px/1 var(--font-heading);color:{x.p['on_accent']};white-space:nowrap}}"
		   f".mid{{flex:1;width:100%;display:grid;grid-template-columns:{'1fr' if x.tall else '560px 1fr'};gap:16px;margin-top:14px;min-height:0}}"
		   f".qs{{display:flex;flex-direction:column;gap:12px;justify-content:center}}.q{{display:flex;align-items:center;gap:16px;border-radius:60px;padding:10px 26px 10px 10px}}"
		   f".q small{{display:block;font:700 22px var(--font-heading)}}.q b{{display:block;font:900 32px/1.05 var(--font-heading);text-transform:uppercase}}"
		   f".pic{{min-height:{460 if x.tall else 0}px}}.band{{width:100%;background:{x.p['dark']};color:#fff;border-radius:18px;padding:16px 24px;margin-top:14px;"
		   f"font:800 30px var(--font-heading);text-align:center}}.band div{{max-height:90px}}.band em{{color:{x.p['accent']}}}"
		   f".promise{{font:800 40px/1.1 var(--font-heading);text-align:center;margin-top:12px;max-height:100px;width:100%}}.promise em{{color:{x.p['primary']}}}"
		   f".call{{display:flex;align-items:center;gap:18px;background:{x.p['secondary']};color:#fff;border-radius:60px;padding:10px 40px 10px 12px;margin-top:14px}}"
		   f".call .ic{{background:rgba(255,255,255,.2);border-radius:50%;padding:12px;display:flex}}.cn{{font:700 30px var(--font-heading)}}"
		   f".call b{{font:900 64px var(--font-heading);color:{x.p['accent']}}}.lg{{position:absolute;right:30px;top:36px}}")
	return body, css


# ---- 10. greeting (festivals, anniversaries, wishes: rays, a rosette, gold text, the business's photo frames) --------
def greeting(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ts = v.get("title_style", "gold")
	face = v.get("title_face", "Lilita One")
	pics = "".join(f'<div class="ph gp" style="background-image:url({esc(p)});{base.FRAMES["circle"]}"></div>' for p in x.photos[:3])
	date = f'<div class="date">{x.el("ribbon", 460, 86, text=c.get("date"), tone="primary")}</div>' if x.has("date") else ""
	deco = v.get("deco", "stars")
	orn = f'<div class="orn">{x.el("flourish", 360, 34, palette={**x.p, "accent": "#f5c542"})}</div>'
	body = (f'<div class="layer">{x.pattern(v.get("pattern", "rays"), base_="primary")}</div>'
			+ (f'<div class="layer">{x.pattern(deco, base_="primary", transparent=True)}</div>' if deco else "")
			+ f'<div class="wrap"><div class="top">{x.logo(70, light=True)}</div><div class="center">' + (f'<div class="pics">{pics}</div>' if pics else orn)
			+ f'<div class="kick">{x.t("kicker")}</div><h1 class="fit" data-fit>{x.m("headline")}</h1>{date}'
			f'<div class="msg fit" data-fit>{x.m("subline")}</div>{orn if pics else ""}</div>'
			f'<div class="from">{x.t("business")}{" · " + x.t("phone") if x.has("phone") else ""}</div></div>')
	css = (f".post{{background:{x.p['primary']};color:#fff}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:36px 50px 40px;text-align:center}}"
		   f".top{{align-self:flex-start}}.pics{{display:flex;gap:26px;margin-top:6px}}.gp{{width:{260 if x.tall else 210}px;height:{260 if x.tall else 210}px;border:6px solid #f5c542;"
		   f"box-shadow:0 14px 30px rgba(0,0,0,.35)}}.center{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;min-height:0}}"
		   f".orn{{margin:16px 0}}.kick{{font:400 52px 'Great Vibes', var(--font-heading);margin-top:14px}}"
		   f"h1{{font:400 {150 if x.tall else 124}px/1 '{face}', var(--font-heading);width:100%;max-height:{360 if x.tall else 270}px;{base.text_style(ts, x.p)}}}"
		   f".date{{margin-top:10px}}.msg{{font:600 30px/1.4 var(--font-body);max-width:900px;margin-top:16px;max-height:{260 if x.tall else 130}px}}"
		   f".from{{font:800 30px var(--font-heading);background:rgba(0,0,0,.25);padding:12px 30px;border-radius:40px}}")
	return body, css


# ---- 11. curve photo (consultants / agencies: a big organic curve, the photo with a curved edge, a CTA) -------------
def curve_photo(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	call = (f'<div class="call">{x.el("icon_tile", 70, 70, text="icon_phone", tone="secondary" if False else "primary")}<div><small>{esc(x.content.get("cta_note") or "Call to find out more")}</small>{x.t("phone")}</div></div>'
			if x.has("phone") else "<div></div>")
	cta = x.el("cta", 330, 78, text=x.content.get("cta"), tone="primary") if x.has("cta") else ""
	body = (f'<div class="layer">{x.pattern("organic_curve", base_="light")}</div>'
			f'<div class="ph pic" style="background-image:url({esc(ph)});{x.photo_style("curve")}"></div>'
			f'<div class="wrap"><div class="top">{x.logo(72, light=False)}</div><div class="txt"><h1 class="fit" data-fit>{x.m("headline")}</h1>'
			+ (f'<div class="q fit" data-fit>“{x.t("quote")}”</div>' if x.has("quote") else "") + f'<div class="cta">{cta}</div></div>'
			f'<div class="foot">{call}<div class="web">{x.t("website")}</div></div></div>')
	css = (f".post{{background:#fbfcf8;color:{x.p['dark']}}}.pic{{position:absolute;right:0;top:{280 if x.tall else 170}px;width:{560 if x.tall else 540}px;height:{900 if x.tall else 640}px}}"
		   f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:56px 60px}}.txt{{flex:1;display:flex;flex-direction:column;justify-content:center;width:{'520px' if not x.tall else '100%'};min-height:0}}"
		   f"h1{{font:400 {92 if x.tall else 84}px/1.02 var(--font-heading);max-height:{520 if x.tall else 360}px;{'width:470px' if x.tall else ''}}}h1 em{{display:block;font-weight:800;color:{x.p['secondary']}}}"
		   f".q{{font:italic 600 30px/1.3 var(--font-body);margin-top:20px;max-height:90px;max-width:470px}}.cta{{margin-top:26px}}"
		   f".foot{{display:flex;justify-content:space-between;align-items:flex-end}}.call{{display:flex;gap:16px;align-items:center;font:800 36px var(--font-heading)}}"
		   f".call small{{display:block;font:500 19px var(--font-body)}}.web{{font:700 26px var(--font-body);color:{x.p['on_primary']}}}")
	return body, css


# ---- 12. wave agency (a navy wave top, a person, big white heading, a topics list, a grey footer) ------------------
def wave_agency(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	topics = "".join(f"<li>{esc(t)}</li>" for t in (x.content.get("list") or [])[:5])
	foot = "".join(f'<div class="fi">{esc(val)}</div>' for _, val in x.contact_bits()[:2])
	dots = "" if x.tall else f'<div class="layer">{x.pattern("dot_corners", base_="dark", transparent=True)}</div>'
	body = (f'<div class="layer">{x.pattern("wave_split", base_="light")}</div>{dots}'
			f'<div class="ph pic" style="background-image:url({esc(ph)});{x.photo_style("blob")}"></div>'
			f'<div class="wrap"><div class="top">{x.logo(64, light=True)}</div><div class="right"><h1 class="fit" data-fit>{x.m("headline")}</h1>'
			f'<div class="sub fit" data-fit>{x.m("subline")}</div></div><div class="topics"><b>{esc(x.content.get("list_title") or "")}</b><ul>{topics}</ul></div></div>'
			f'<div class="foot">{foot}</div>')
	css = (f".post{{background:#ffffff;color:{x.p['dark']}}}.pic{{position:absolute;left:40px;top:{220 if x.tall else 170}px;width:{560 if x.tall else 470}px;height:{760 if x.tall else 560}px;"
		   f"box-shadow:0 20px 40px rgba(0,0,0,.25)}}.wrap{{position:absolute;inset:0 0 110px 0;display:flex;flex-direction:column;padding:48px 56px}}"
		   f".right{{margin-left:auto;width:{'100%' if x.tall else '480px'};{'margin-top:' + ('1010px' if x.tall else '0') }}}"
		   f"h1{{font:800 {80 if x.tall else 66}px/1.05 var(--font-heading);color:#fff;text-transform:uppercase;max-height:{300 if x.tall else 260}px;{'color:' + x.p['dark'] if x.tall else ''}}}"
		   f"h1 em{{text-decoration:underline;text-decoration-color:{x.p['accent']};text-underline-offset:10px}}"
		   f".sub{{font:400 20px/1.5 var(--font-body);color:rgba(255,255,255,.85);margin-top:14px;max-height:120px;{'color:' + x.p['dark'] if x.tall else ''}}}"
		   f".topics{{margin:auto 0 0 auto;width:{'100%' if x.tall else '420px'}}}.topics b{{font:800 28px var(--font-heading)}}.topics ul{{margin:10px 0 0 26px;font:500 23px/1.6 var(--font-body)}}"
		   f".topics li::marker{{color:{x.p['primary']}}}.foot{{position:absolute;left:0;right:0;bottom:0;height:110px;background:#eceff3;display:flex;align-items:center;justify-content:space-between;padding:0 56px}}"
		   f".fi{{font:700 24px var(--font-body)}}")
	return body, css


# ---- 13. sale (angular shards, a photo, BIG SALE · label · big percent, shop now) -----------------------------------
def sale(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	label = f'<div class="lbl">{x.t("price_label")}</div>' if x.has("price_label") else ""
	body = (f'<div class="layer">{x.pattern("shards", base_="light")}</div>'
			f'<div class="ph pic" style="background-image:url({esc(ph)})"></div>'
			f'<div class="wrap"><div class="web">{x.t("website")}</div><div class="txt"><div class="kick">{x.t("kicker")}</div><h1 class="fit" data-fit>{x.m("headline")}</h1>'
			f'{label}<div class="big fit" data-fit>{x.m("badge")}</div></div>'
			+ (f'<div class="shop">{x.t("cta")}</div>' if x.has("cta") else "") + f'<div class="lg">{x.logo(60, light=False)}</div></div>')
	css = (f".post{{background:{x.p['light']};color:{x.p['dark']}}}.pic{{position:absolute;right:0;top:{12 if x.tall else 9}%;width:{100 if x.tall else 56}%;height:{46 if x.tall else 82}%;"
		   f"clip-path:polygon(18% 0,100% 0,100% 100%,0 100%,6% 40%);{'top:auto;bottom:0' if x.tall else ''}}}"
		   f".wrap{{position:absolute;inset:0;padding:50px 60px;display:flex;flex-direction:column}}.web{{align-self:flex-end;font:500 24px var(--font-body)}}"
		   f".txt{{{'margin-top:30px' if x.tall else 'margin:auto 0'};width:{'100%' if x.tall else '470px'}}}.kick{{font:300 62px var(--font-heading);text-transform:uppercase}}"
		   f"h1{{font:800 128px/0.95 var(--font-heading);text-transform:uppercase;max-height:250px}}h1 em{{color:{x.p['primary']}}}"
		   f".lbl{{display:inline-block;background:{x.p['dark']};color:#fff;font:800 24px var(--font-heading);letter-spacing:3px;padding:6px 26px;margin:14px 0;text-transform:uppercase}}"
		   f".big{{font:400 112px/1 var(--font-heading);max-height:240px}}.big em{{font-weight:800;color:{x.p['primary']}}}"
		   f".shop{{margin-top:{'34px' if x.tall else 'auto'};align-self:flex-start;border:2px solid {x.p['dark']};border-radius:30px;padding:10px 30px;font:600 24px var(--font-body);text-transform:uppercase}}"
		   f".lg{{position:absolute;left:60px;top:48px}}")
	return body, css


# ---- 14. numbered services (big circles, a person, mixed headline, a vertical label + numbered list, contact bar) ---
def numbered_services(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	lst = "".join(f'<div class="li"><span class="n">{k + 1}</span>{esc(t)}</div>' for k, t in enumerate((x.content.get("list") or [])[:5]))
	foot = "".join(f'<div class="fi">{esc(val)}</div>' for _, val in x.contact_bits()[:2])
	cta = x.el("cta", 260, 64, text=x.content.get("cta"), tone="accent") if x.has("cta") else ""
	body = (f'<div class="layer">{x.pattern("big_circles", base_="primary")}</div>'
			+ (f'<div class="circ"></div>' if x.cut else "")
			+ f'<div class="ph pic" style="background-image:url({esc(ph)});{x.photo_style("circle")}"></div>'
			f'<div class="wrap"><div class="top">{x.logo(60, light=True)}</div><div class="right"><div class="kick">{x.t("kicker")}</div>'
			f'<h1 class="fit" data-fit>{x.m("headline")}</h1><div class="sub fit" data-fit>{x.m("subline")}</div>'
			f'<div class="svc">{x.el("vertical_label", 64, 250, text=x.content.get("list_title") or "", tone="accent")}<div class="list">{lst}</div></div></div>'
			f'<div class="foot">{cta}{foot}</div></div>')
	css = (f".circ{{position:absolute;left:50px;top:{140 if x.tall else 150}px;width:{460 if x.tall else 400}px;height:{460 if x.tall else 400}px;border-radius:50%;background:{x.p['accent']}}}"
		   f".post{{background:{x.p['primary']};color:#fff}}.pic{{position:absolute;left:50px;top:{140 if x.tall else 150}px;width:{460 if x.tall else 400}px;height:{460 if x.tall else 400}px;"
		   f"border:10px solid {x.p['accent']}}}.wrap{{position:absolute;inset:0;padding:44px 56px;display:flex;flex-direction:column}}"
		   f".right{{margin-left:auto;width:{'100%' if x.tall else '520px'};{'margin-top:560px' if x.tall else 'margin-top:40px'}}}.kick{{font:500 34px var(--font-body)}}"
		   f"h1{{font:900 {96 if x.tall else 84}px/0.98 var(--font-heading);text-transform:uppercase;max-height:{300 if x.tall else 260}px}}h1 em{{color:{x.p['accent']}}}"
		   f".sub{{font:400 20px/1.5 var(--font-body);opacity:.88;margin-top:12px;max-height:100px}}.svc{{display:flex;gap:20px;margin-top:22px;align-items:center}}"
		   f".li{{display:flex;gap:16px;align-items:center;font:600 26px var(--font-body);padding:8px 0;border-left:2px solid rgba(255,255,255,.4);padding-left:16px}}"
		   f".n{{font:800 22px var(--font-heading);color:{x.p['accent']}}}.foot{{margin-top:auto;display:flex;align-items:center;gap:30px}}"
		   f".fi{{font:800 28px var(--font-heading)}}.fi + .fi{{font:500 20px var(--font-body);opacity:.9}}")
	return body, css


# ---- 15. gallery (photography / salons: diamond and tilted frames, a service list, a % badge, a name ribbon) --------
def gallery(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	gold = x.p["accent"]
	fr = v.get("frame", "diamond")
	pics = "".join(f'<div class="g g{k} ph" style="background-image:url({esc(x.photo(k))});{base.FRAMES[fr]}"></div>' for k in range(3))
	lst = "".join(f"<li>{esc(t)}</li>" for t in (c.get("list") or [])[:6])
	badge = (f'<div class="badge">{x.el("badge", 210, 210, text=c.get("badge"), tone="accent")}</div>' if x.has("badge") else "")
	foot = "".join(f'<div class="fi">{x.el(i, 30, 30, tone="dark")}<span>{esc(val)}</span></div>' for i, val in x.contact_bits()[:3])
	body = (f'<div class="layer">{x.pattern("dot_corners", base_="dark")}</div><div class="wrap"><div class="row1"><h1 class="fit" data-fit>{x.m("headline")}</h1>'
			f'<div class="lg">{x.logo(70, light=True)}</div></div><div class="sub">{x.t("subline")}</div>'
			f'<div class="mid"><div class="pics">{pics}{badge}</div><div class="right"><div class="rib">{x.el("ribbon", 400, 70, text=c.get("kicker"), tone="accent")}</div>'
			f'<ul>{lst}</ul><div class="who"><b>{x.t("person")}</b><small>{x.t("role")}</small></div></div></div><div class="foot">{foot}</div></div>')
	css = (f".post{{background:#2b2b2e;color:#fff}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:44px 0 0}}"
		   f".row1{{display:flex;justify-content:space-between;align-items:flex-start;padding:0 56px}}h1{{font:900 96px/0.95 var(--font-heading);color:{gold};text-transform:uppercase;max-height:200px;width:640px}}"
		   f"h1 em{{color:#fff}}.sub{{padding:6px 56px 0;font:600 28px var(--font-body);letter-spacing:2px;text-transform:uppercase}}"
		   f".mid{{flex:1;display:grid;grid-template-columns:{'1fr' if x.tall else '600px 1fr'};min-height:0}}.pics{{position:relative;min-height:{700 if x.tall else 0}px}}"
		   f".g{{position:absolute;border:8px solid {gold}}}.g0{{left:40px;top:40px;width:330px;height:330px}}.g1{{left:300px;top:0;width:250px;height:250px}}"
		   f".g2{{left:310px;top:230px;width:260px;height:260px}}.badge{{position:absolute;left:150px;bottom:10px}}"
		   f".right{{padding:20px 40px 0 0;display:flex;flex-direction:column;align-items:flex-end;text-align:right}}ul{{list-style:none;margin-top:20px;font:600 27px/1.75 var(--font-body)}}"
		   f"li::after{{content:' •';color:{gold}}}.who{{margin-top:auto;background:#1c1c1f;padding:16px 26px;margin-bottom:16px}}.who b{{display:block;font:900 40px var(--font-heading)}}"
		   f".who small{{font:500 16px var(--font-body);letter-spacing:4px;text-transform:uppercase}}.foot{{background:#eceff3;color:#1f2937;display:flex;justify-content:space-around;align-items:center;min-height:110px;padding:0 30px}}"
		   f".fi{{display:flex;gap:10px;align-items:center;font:600 22px var(--font-body)}}")
	return body, css


# ---- 16. product promo (food / a product: a dark textured board, a distressed word, the price in a ring, an order bar) ----
def product_promo(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	white = {**x.p, "accent": "#ffffff"}
	price = (f'<div class="price"><small>{x.t("price_label")}</small>{x.el("scribble_circle", 220, 130, text=c.get("price"), palette=white)}</div>' if x.has("price") else "")
	order = (f'<div class="ob">{x.el("order_bar", 900, 96, text=(c.get("phone") or "") + ("   " + c["cta"] if c.get("cta") else ""), tone="accent")}</div>'
			 if x.has("phone") else "")
	body = (f'<div class="layer">{x.pattern("chalkboard", base_="dark")}</div>'
			f'<div class="sp1">{x.el("splash", 90, 70, tone="accent")}</div><div class="sp2">{x.el("splash", 80, 60, tone="accent")}</div>'
			f'<div class="wrap"><div class="row"><div>{x.logo(96, light=True)}</div>{price}</div><div class="kick">{x.t("kicker")}</div>'
			f'<h1 class="fit" data-fit>{x.m("headline")}</h1><div class="ph pic" style="background-image:url({esc(ph)});{x.photo_style()}"></div>{order}'
			f'<div class="addr">{x.t("address")}</div></div>')
	css = (f".post{{color:#fff}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;padding:40px 50px 22px}}"
		   f".row{{width:100%;display:flex;justify-content:space-between;align-items:flex-start}}.price{{text-align:center;font:800 22px var(--font-heading)}}.price small{{display:block;text-transform:uppercase}}"
		   f".kick{{font:400 58px 'Kaushan Script', var(--font-heading);color:{x.p['accent']};margin-top:-10px}}h1{{font:400 {210 if x.tall else 180}px/1 'Rubik Dirt', var(--font-heading);text-transform:uppercase;width:100%;"
		   f"text-align:center;max-height:{240 if x.tall else 200}px;white-space:nowrap}}h1 em{{color:{x.p['accent']}}}"
		   f".pic{{flex:1;width:100%;min-height:0;border-radius:28px;margin-top:10px;-webkit-mask-image:radial-gradient(ellipse at center,#000 55%,transparent 75%);"
		   f"mask-image:radial-gradient(ellipse at center,#000 55%,transparent 75%)}}.ob{{margin-top:6px}}"
		   f".addr{{font:700 26px var(--font-body);letter-spacing:1px;color:{x.p['accent']};margin-top:12px;text-align:center}}"
		   f".sp1{{position:absolute;left:40px;top:42%}}.sp2{{position:absolute;right:40px;top:30%}}")
	return body, css


LAYOUTS = {"hero_split": hero_split, "center_hero": center_hero, "listing": listing, "event": event, "tribute": tribute,
		   "quote_tip": quote_tip, "problem_solution": problem_solution, "circles_labels": circles_labels, "question_rows": question_rows,
		   "greeting": greeting, "curve_photo": curve_photo, "wave_agency": wave_agency, "sale": sale,
		   "numbered_services": numbered_services, "gallery": gallery, "product_promo": product_promo}

# Showcase layouts (S10 Poster variations): screenshots in device compositions — same engine, same rules
from qtt_platform.design import showcase as _showcase  # noqa: E402

LAYOUTS.update(_showcase.LAYOUTS)
