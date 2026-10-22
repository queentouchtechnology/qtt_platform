"""
More layouts for the template library (PROJ-0012 S2, premium upgrade) — the creative directions and trades the first
sixteen didn't cover: customer reviews, minimal editorial, luxury, travel, personal brands, product spotlights,
typography-led offers, fitness and automotive energy, menus, geometric blocks and results.

Same contract as archetypes.py: layout(ctx, variant) → (body, css) at 1080 wide, flex / grid only so square, portrait
and story all work and long words push what follows instead of covering it. Design rules: docs/design/studio-design-rules.md
— body text never under 20 px, small print never under 18 px; text that can't fit at its smallest size (data-min) is
reported by the audit and in Studio, never shrunk into unreadability. Nothing is invented: an empty slot is left out.
"""

from qtt_platform.design import base
from qtt_platform.design.layouts import Ctx, esc


def _contact_line(x: Ctx, n: int = 2, sep: str = " · ") -> str:
	return sep.join(esc(v) for _, v in x.contact_bits()[:n])


def _stars(n: int, colour: str, size: int = 40) -> str:
	star = "M50 6l13 29 31 3-24 21 7 31-27-16-27 16 7-31L6 38l31-3z"
	return "".join(f'<svg width="{size}" height="{size}" viewBox="0 0 100 100"><path d="{star}" fill="{colour}"/></svg>' for _ in range(max(0, min(5, n))))


# ---- 17. testimonial (a customer's words: big quote, stars, who said it) — typography-led ----------------------------
def testimonial(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	try:
		stars = int(str(c.get("rating") or "0").strip()[:1] or 0)
	except ValueError:
		stars = 0
	who = ""
	if x.has("person"):
		pic = f'<div class="av ph" style="background-image:url({esc(ph)})"></div>' if ph and v.get("photo", True) else ""
		who = f'<div class="who">{pic}<div><b>{x.t("person")}</b>' + (f'<small>{x.t("role")}</small>' if x.has("role") else "") + "</div></div>"
	kick = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	body = (f'<div class="layer">{x.pattern(v.get("pattern", "frame_lines"))}</div>'
			f'<div class="wrap"><div class="top">{x.logo(64)}{kick}</div><div class="mid"><div class="mark">“</div>'
			+ (f'<div class="stars">{_stars(stars, x.p["accent"] if base.contrast(x.p["accent"], x.bg) >= 2 else x.hl)}</div>' if stars else "")
			+ f'<div class="q fit" data-fit data-min="30">{x.m("quote")}</div>{who}</div>'
			f'<div class="foot">{_contact_line(x)}</div></div>')
	qs = 64 if x.tall else 54
	css = (f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:60px 72px}}"
		   f".top{{display:flex;justify-content:space-between;align-items:center;gap:24px}}"
		   f".kick{{font:700 20px var(--font-body);letter-spacing:3px;text-transform:uppercase;color:{x.hl}}}"
		   f".mid{{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0}}"
		   f".mark{{font:400 220px/0.7 Georgia,serif;color:{x.hl};opacity:.9;height:110px}}.stars{{display:flex;gap:8px;margin:6px 0 22px}}"
		   f".q{{font:600 {qs}px/1.22 var(--font-heading);max-height:{900 if x.tall else 520}px}}.q em{{color:{x.hl}}}"
		   f".who{{display:flex;align-items:center;gap:20px;margin-top:40px}}.av{{width:96px;height:96px;border-radius:50%;flex:none;"
		   f"box-shadow:0 0 0 4px {x.bg},0 0 0 6px {x.hl}}}.who b{{display:block;font:700 30px var(--font-heading)}}"
		   f".who small{{display:block;font:500 22px var(--font-body);color:{x.soft};margin-top:2px}}"
		   f".foot{{font:600 22px var(--font-body);color:{x.soft}}}")
	return body, css


# ---- 18. editorial (white space, one photo, a serif headline, thin rules) — minimal and editorial --------------------
def editorial(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	kick = f'<span>{x.t("kicker")}</span>' if x.has("kicker") else "<span></span>"
	sub = f'<div class="sub fit" data-fit data-min="22">{x.m("subline")}</div>' if x.has("subline") else ""
	cta = f'<div class="cta">{x.t("cta")} →</div>' if x.has("cta") else ""
	ink = x.p["dark"]
	body = (f'<div class="wrap"><div class="bar">{x.logo(56, light=False)}{kick}</div>'
			f'<div class="pic ph" style="background-image:url({esc(ph)});{x.photo_style()}"></div>'
			f'<div class="txt"><h1 class="fit" data-fit data-min="48">{x.m("headline")}</h1>{sub}<div class="rule"></div>'
			f'<div class="low"><div class="ct">{_contact_line(x)}</div>{cta}</div></div></div>')
	css = (f".post{{background:{x.p['light']};color:{ink}}}"
		   f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:52px 60px 50px}}"
		   f".bar{{display:flex;justify-content:space-between;align-items:center;padding-bottom:20px;border-bottom:1.5px solid {base.mix(ink, x.p['light'], .75)}}}"
		   f".bar span{{font:600 19px var(--font-body);letter-spacing:4px;text-transform:uppercase;color:{base.mix(ink, x.p['light'], .3)}}}"
		   f".pic{{flex:1;min-height:{360 if x.tall else 300}px;margin:28px 0;border-radius:4px}}"
		   f".txt{{flex:none}}h1{{font:600 {84 if x.tall else 68}px/1.04 var(--font-heading);letter-spacing:-1px;max-height:{330 if x.tall else 230}px}}"
		   f"h1 em{{font-style:italic;color:{x.p['primary'] if base.contrast(x.p['primary'], x.p['light']) >= 3 else ink}}}"
		   f".sub{{font:400 26px/1.45 var(--font-body);color:{base.mix(ink, x.p['light'], .25)};margin-top:16px;max-height:120px}}"
		   f".rule{{height:1.5px;background:{base.mix(ink, x.p['light'], .75)};margin:26px 0 18px}}"
		   f".low{{display:flex;justify-content:space-between;align-items:center;gap:20px}}.ct{{font:500 20px var(--font-body);color:{base.mix(ink, x.p['light'], .25)}}}"
		   f".cta{{font:700 22px var(--font-body);letter-spacing:2px;text-transform:uppercase;color:{x.p['primary'] if base.contrast(x.p['primary'], x.p['light']) >= 3 else ink};white-space:nowrap}}")
	return body, css


# ---- 19. luxury frame (a fine double frame, an arch photo, centred serif) — premium luxury ---------------------------
def luxury_frame(x: Ctx, v: dict) -> tuple[str, str]:
	ph = x.photo(0)
	gold = x.p["accent"] if base.contrast(x.p["accent"], x.p["dark"]) >= 3 else "#d9b977"
	kick = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	sub = f'<div class="sub fit" data-fit data-min="22">{x.m("subline")}</div>' if x.has("subline") else ""
	cta = f'<div class="cta">{x.t("cta")}</div>' if x.has("cta") else ""
	body = (f'<div class="frame"></div><div class="frame f2"></div>'
			f'<div class="wrap"><div class="lg">{x.logo(70, light=True)}</div>{kick}'
			f'<div class="pic ph" style="background-image:url({esc(ph)});{x.photo_style("arch")}"></div>'
			f'<h1 class="fit" data-fit data-min="44">{x.m("headline")}</h1>{sub}{cta}<div class="foot">{_contact_line(x)}</div></div>')
	css = (f".post{{background:radial-gradient(120% 80% at 50% 30%,{base.mix(x.p['dark'], x.p['primary'], .35)},{x.p['dark']} 70%);color:#fff}}"
		   f".frame{{position:absolute;inset:34px;border:1.5px solid {gold};opacity:.85}}.f2{{inset:46px;opacity:.45}}"
		   f".wrap{{position:absolute;inset:70px 80px 64px;display:flex;flex-direction:column;align-items:center;text-align:center}}"
		   f".kick{{font:400 21px 'Cinzel',var(--font-heading);letter-spacing:7px;text-transform:uppercase;color:{gold};margin-top:18px}}"
		   f".pic{{width:{520 if x.tall else 400}px;flex:1;max-height:{820 if x.tall else 430}px;min-height:240px;margin:24px 0 26px;"
		   f"box-shadow:0 30px 60px rgba(0,0,0,.45);outline:1.5px solid {gold};outline-offset:10px}}"
		   f"h1{{font:500 {86 if x.tall else 68}px/1.05 'Cinzel',var(--font-heading);letter-spacing:2px;max-height:{260 if x.tall else 160}px;width:100%;"
		   f"background:linear-gradient(180deg,#fff,{base.mix(gold, '#ffffff', .35)});-webkit-background-clip:text;background-clip:text;color:transparent}}"
		   f"h1 em{{font-style:normal}}.sub{{font:400 25px/1.45 var(--font-body);opacity:.85;margin-top:12px;max-height:110px;max-width:760px}}"
		   f".cta{{margin-top:22px;border:1.5px solid {gold};color:{gold};padding:12px 40px;font:600 21px var(--font-body);letter-spacing:4px;text-transform:uppercase}}"
		   f".foot{{margin-top:auto;padding-top:18px;font:500 20px var(--font-body);letter-spacing:1px;opacity:.8}}")
	return body, css


# ---- 20. travel postcard (the place fills the post; dates, price, call) — cinematic ----------------------------------
def travel_postcard(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	kick = f'<div class="chip">{x.t("kicker")}</div>' if x.has("kicker") else "<div></div>"
	info = []
	if x.has("date"):
		info.append(f'<div class="in"><small>{esc(c.get("date_label") or "When")}</small><b>{x.t("date")}</b></div>')
	if x.has("price"):
		info.append(f'<div class="in"><small>{x.t("price_label") or "From"}</small><b>{x.t("price")}</b></div>')
	cta = f'<div class="cta">{x.t("cta")}</div>' if x.has("cta") else ""
	body = (f'<div class="layer ph bg" style="background-image:url({esc(ph)})"></div>'
			f'<div class="layer shade"></div><div class="wrap"><div class="top">{x.logo(66, light=True)}{kick}</div>'
			f'<div class="low">' + (f'<div class="pre">{x.t("subline")}</div>' if x.has("subline") else "")
			+ f'<h1 class="fit" data-fit data-min="56">{x.m("headline")}</h1>'
			+ (f'<div class="info">{"".join(info)}{cta}</div>' if info or cta else "")
			+ f'<div class="ct">{_contact_line(x, 3)}</div></div></div>')
	css = (f".post{{background:{x.p['dark']};color:#fff}}.bg{{background-position:center 40%}}"
		   ".shade{background:linear-gradient(180deg,rgba(0,0,0,.45) 0%,rgba(0,0,0,0) 26%,rgba(0,0,0,.08) 46%,rgba(0,0,0,.78) 100%)}"
		   f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:space-between;padding:52px 60px 50px}}"
		   f".top{{display:flex;justify-content:space-between;align-items:center;gap:20px}}"
		   f".chip{{background:rgba(255,255,255,.16);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.35);padding:10px 22px;border-radius:40px;"
		   f"font:700 20px var(--font-body);letter-spacing:2px;text-transform:uppercase}}"
		   f".pre{{font:400 46px 'Dancing Script',var(--font-heading);color:{base.mix(x.p['accent'], '#ffffff', .3)};margin-bottom:-6px}}"
		   f"h1{{font:800 {150 if x.tall else 124}px/0.95 var(--font-heading);text-transform:uppercase;letter-spacing:-2px;max-height:{420 if x.tall else 260}px;"
		   f"text-shadow:0 8px 40px rgba(0,0,0,.45)}}h1 em{{color:{base.mix(x.p['accent'], '#ffffff', .15)}}}"
		   f".info{{display:flex;align-items:stretch;gap:14px;margin-top:22px;flex-wrap:wrap}}"
		   f".in{{background:rgba(255,255,255,.14);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.28);border-radius:18px;padding:12px 22px}}"
		   f".in small{{display:block;font:600 18px var(--font-body);letter-spacing:2px;text-transform:uppercase;opacity:.8}}.in b{{font:800 34px var(--font-heading)}}"
		   f".cta{{background:{x.p['accent']};color:{x.p['on_accent']};border-radius:18px;padding:0 30px;display:flex;align-items:center;font:800 26px var(--font-heading)}}"
		   f".ct{{margin-top:18px;font:500 21px var(--font-body);opacity:.9}}")
	return body, css


# ---- 21. creator card (a personal brand: the person, their name, what they talk about) -------------------------------
def creator_card(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	topics = "".join(f'<span>{esc(t)}</span>' for t in (c.get("list") or [])[:5])
	handle = f'<div class="hd">{x.t("website")}</div>' if x.has("website") else ""
	cta = f'<div class="cta">{x.el("cta", 340, 72, text=c.get("cta"), tone="accent")}</div>' if x.has("cta") else ""
	body = (f'<div class="layer side"></div><div class="ph pic" style="background-image:url({esc(ph)});{x.photo_style()}"></div>'
			f'<div class="wrap"><div class="lg">{x.logo(56, light=True)}</div><div class="txt">'
			+ (f'<div class="role">{x.t("role")}</div>' if x.has("role") else "")
			+ f'<div class="nm fit" data-fit data-min="48">{x.t("person") or x.t("business")}</div>'
			f'<div class="h fit" data-fit data-min="26">{x.m("headline")}</div>'
			+ (f'<div class="tp">{topics}</div>' if topics else "") + f'{cta}{handle}</div></div>')
	split = 56 if not x.tall else 100
	css = (f".post{{background:{x.p['light']};color:#fff}}"
		   f".side{{background:linear-gradient(160deg,{x.p['primary']},{x.p['primary_deep']});{'' if x.tall else f'right:{100 - split}%'};{'top:52%' if x.tall else ''}}}"
		   f".pic{{position:absolute;{'left:0;right:0;top:0;height:52%' if x.tall else f'left:{split}%;right:0;top:0;bottom:0'};background-position:center 25%}}"
		   f".wrap{{position:absolute;{'left:0;right:0;top:52%;bottom:0' if x.tall else f'left:0;top:0;bottom:0;right:{100 - split}%'};display:flex;flex-direction:column;padding:50px 56px}}"
		   f".lg{{{'position:absolute;top:-' + str(int(1920 * .52) - 40) + 'px;left:56px' if x.tall else ''}}}"
		   f".txt{{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0;color:{x.p['on_primary']}}}"
		   f".role{{font:700 20px var(--font-body);letter-spacing:4px;text-transform:uppercase;opacity:.85}}"
		   f".nm{{font:800 {96 if x.tall else 78}px/1 var(--font-heading);margin:8px 0 18px;max-height:{220 if x.tall else 170}px}}"
		   f".h{{font:500 32px/1.3 var(--font-body);max-height:{200 if x.tall else 170}px}}.h em{{color:{x.p['accent'] if base.contrast(x.p['accent'], x.p['primary']) >= 2.4 else x.p['on_primary']};font-weight:700}}"
		   f".tp{{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}}.tp span{{border:1.5px solid {base.mix(x.p['on_primary'], x.p['primary'], .45)};"
		   f"border-radius:40px;padding:8px 18px;font:600 20px var(--font-body)}}.cta{{margin-top:26px}}"
		   f".hd{{margin-top:18px;font:600 22px var(--font-body);opacity:.85}}")
	return body, css


# ---- 22. product spotlight (the product on a lit podium; price and three features) — product-focused ---------------
def product_spotlight(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	feats = "".join(f'<div class="ft">{x.el("icon_tile", 52, 52, text=it.get("icon") or "icon_check", tone="primary")}<span>{esc(it.get("title"))}</span></div>'
					for it in (c.get("items") or [])[:3])
	price = (f'<div class="pr"><small>{x.t("price_label")}</small><b>{x.t("price")}</b></div>' if x.has("price") else "")
	badge = f'<div class="bd">{x.t("badge")}</div>' if x.has("badge") else ""
	cta = f'<div class="cta">{x.el("cta", 330, 76, text=c.get("cta"), tone="primary")}</div>' if x.has("cta") else ""
	kick = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	cut = x.cut
	body = (f'<div class="layer glow"></div><div class="wrap"><div class="top">{x.logo(60, light=False)}{badge}</div><div class="main">'
			f'<div class="txt">{kick}<h1 class="fit" data-fit data-min="44">{x.m("headline")}</h1>'
			+ (f'<div class="fts">{feats}</div>' if feats else "") + f'{price}{cta}</div>'
			f'<div class="stage"><div class="pod"></div><div class="ph prod" style="background-image:url({esc(ph)});{x.photo_style("rounded")}"></div></div></div>'
			f'<div class="foot">{_contact_line(x, 3)}</div></div>')
	css = (f".post{{background:linear-gradient(180deg,{x.p['light']},{base.mix(x.p['light'], x.p['primary'], .14)});color:{x.p['dark']}}}"
		   f".glow{{background:radial-gradient(45% 40% at {50 if x.tall else 70}% {66 if x.tall else 56}%,{base.mix(x.p['primary'], '#ffffff', .55)}aa,transparent 70%)}}"
		   f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:50px 58px 44px}}.top{{display:flex;justify-content:space-between;align-items:center}}"
		   f".bd{{background:{x.p['accent']};color:{x.p['on_accent']};font:800 22px var(--font-heading);padding:10px 22px;border-radius:40px;text-transform:uppercase}}"
		   f".main{{flex:1;display:{'flex;flex-direction:column' if x.tall else 'grid;grid-template-columns:470px 1fr'};gap:20px;align-items:center;min-height:0}}"
		   f".txt{{display:flex;flex-direction:column;min-height:0}}.kick{{font:700 20px var(--font-body);letter-spacing:3px;text-transform:uppercase;color:{x.hl}}}"
		   f"h1{{font:800 {80 if x.tall else 66}px/1.02 var(--font-heading);margin:8px 0 20px;max-height:{300 if x.tall else 230}px}}h1 em{{color:{x.hl}}}"
		   f".fts{{display:flex;flex-direction:column;gap:12px}}.ft{{display:flex;align-items:center;gap:14px;font:600 24px/1.2 var(--font-body)}}.ft svg{{flex:none}}"
		   f".pr{{margin-top:22px}}.pr small{{display:block;font:600 20px var(--font-body);color:{x.soft};text-transform:uppercase;letter-spacing:2px}}"
		   f".pr b{{font:900 72px/1 var(--font-heading);color:{x.hl}}}.cta{{margin-top:20px}}"
		   f".stage{{position:relative;width:100%;height:100%;min-height:{560 if x.tall else 0}px}}"
		   f".pod{{position:absolute;left:8%;right:8%;bottom:4%;height:16%;border-radius:50%;background:radial-gradient(closest-side,{base.mix(x.p['dark'], '#000000', .2)}55,transparent);filter:blur(6px)}}"
		   f".prod{{position:absolute;left:6%;right:6%;top:4%;bottom:12%;{'' if cut else 'box-shadow:0 34px 60px rgba(0,0,0,.28)'}}}"
		   f".foot{{font:600 20px var(--font-body);color:{x.soft};margin-top:10px}}")
	return body, css


# ---- 23. bold type (the words fill the post; a strip with the photo and the call) — typography-led, bold ------------
def bold_type(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	cta = f'<div class="cta">{x.t("cta")} →</div>' if x.has("cta") else ""
	badge = f'<div class="bd fit" data-fit data-min="40">{x.m("badge")}</div>' if x.has("badge") else ""
	body = (f'<div class="wrap"><div class="top">{x.logo(62)}<div class="kick">{x.t("kicker")}</div></div>'
			f'<div class="hw"><h1 class="fit" data-fit data-min="80">{x.m("headline")}</h1></div>{badge}'
			f'<div class="strip">' + (f'<div class="ph pic" style="background-image:url({esc(ph)})"></div>' if ph else "")
			+ f'<div class="sub">' + (f'<div class="s fit" data-fit data-min="22">{x.m("subline")}</div>' if x.has("subline") else "")
			+ f'<div class="ct">{_contact_line(x)}</div></div>{cta}</div></div>')
	ink = x.ink
	css = (f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:52px 56px 50px}}"
		   f".top{{display:flex;justify-content:space-between;align-items:center;gap:20px}}"
		   f".kick{{font:700 21px var(--font-body);letter-spacing:4px;text-transform:uppercase;color:{x.hl}}}"
		   f".hw{{flex:1;display:flex;align-items:center;min-height:0;margin:10px 0}}"
		   f"h1{{width:100%;font:900 {340 if x.tall else 290}px/0.86 var(--font-heading);text-transform:uppercase;letter-spacing:-6px;"
		   f"max-height:{x.h - 500}px}}h1 em{{color:{x.hl}}}"
		   f".bd{{font:900 96px/1 var(--font-heading);color:{x.hl};max-height:110px;white-space:nowrap;margin-bottom:16px}}.bd em{{color:{ink}}}"
		   f".strip{{display:flex;align-items:center;gap:22px;border-top:3px solid {ink};padding-top:22px}}"
		   f".pic{{width:130px;height:130px;border-radius:50%;flex:none}}.sub{{flex:1;min-width:0}}"
		   f".s{{font:600 26px/1.3 var(--font-body);max-height:72px}}.s em{{color:{x.hl}}}.ct{{font:500 20px var(--font-body);color:{x.soft};margin-top:4px}}"
		   f".cta{{background:{x.hl};color:{base.on(x.hl, dark=x.p['dark'])};padding:20px 30px;border-radius:14px;font:800 24px var(--font-heading);white-space:nowrap}}")
	return body, css


# ---- 24. fitness power (slanted energy, a photo cut on a diagonal, big numbers) — gyms, sports, automotive ----------
def fitness_power(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	stats = "".join(f'<div class="st"><b>{esc(it.get("title"))}</b><span>{esc(it.get("text"))}</span></div>' for it in (c.get("items") or [])[:3])
	cta = f'<div class="cta">{x.t("cta")}</div>' if x.has("cta") else ""
	kick = f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else ""
	body = (f'<div class="ph pic" style="background-image:url({esc(ph)})"></div><div class="layer slash"></div><div class="layer slash s2"></div>'
			f'<div class="wrap"><div class="top">{x.logo(62, light=True)}</div><div class="txt">{kick}<h1 class="fit" data-fit data-min="56">{x.m("headline")}</h1>'
			+ (f'<div class="sub">{x.m("subline")}</div>' if x.has("subline") else "") + (f'<div class="sts">{stats}</div>' if stats else "")
			+ f'{cta}</div><div class="ct">{_contact_line(x, 3)}</div></div>')
	acc = x.p["accent"] if base.contrast(x.p["accent"], x.p["dark"]) >= 3 else x.p["primary"]
	css = (f".post{{background:{x.p['dark']};color:#fff}}"
		   f".pic{{position:absolute;{'left:0;right:0;top:0;height:50%' if x.tall else 'top:0;bottom:0;right:0;width:58%'};"
		   f"clip-path:{'polygon(0 0,100% 0,100% 82%,0 100%)' if x.tall else 'polygon(37.9% 0,100% 0,100% 100%,13.8% 100%)'};filter:contrast(1.1) saturate(1.1)}}"
		   f".slash{{background:{acc};clip-path:{'polygon(0 49%,100% 41%,100% 43%,0 51%)' if x.tall else 'polygon(62.5% 0,64.5% 0,50.5% 100%,48.5% 100%)'}}}"
		   f".s2{{opacity:.45;clip-path:{'polygon(0 52.5%,100% 44.5%,100% 45.3%,0 53.3%)' if x.tall else 'polygon(66% 0,66.8% 0,52.8% 100%,52% 100%)'}}}"
		   f".wrap{{position:absolute;{'left:0;right:0;top:50%;bottom:0' if x.tall else 'left:0;top:0;bottom:0;width:50%'};display:flex;flex-direction:column;padding:50px 30px 50px 56px}}"
		   f".top{{{'position:absolute;top:-' + str(int(1920 * .5) - 46) + 'px;left:56px' if x.tall else ''}}}"
		   f".txt{{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0}}"
		   f".kick{{font:800 24px var(--font-body);letter-spacing:5px;text-transform:uppercase;color:{acc}}}"
		   f"h1{{font:900 italic {120 if x.tall else 88}px/0.9 var(--font-heading);text-transform:uppercase;margin:10px 0 16px;max-height:{330 if x.tall else 300}px}}"
		   f"h1 em{{color:{acc}}}.sub{{font:500 26px/1.35 var(--font-body);opacity:.88;max-width:560px}}"
		   f".sts{{display:flex;gap:22px;margin-top:24px;flex-wrap:wrap}}.st b{{display:block;font:900 48px/1 var(--font-heading);color:{acc}}}.st span{{font:600 19px var(--font-body);opacity:.85;text-transform:uppercase;letter-spacing:1px}}"
		   f".cta{{align-self:flex-start;margin-top:26px;background:{acc};color:{base.on(acc, dark=x.p['dark'])};padding:16px 34px;font:900 italic 26px var(--font-heading);"
		   f"text-transform:uppercase;transform:skewX(-10deg)}}.ct{{font:600 20px var(--font-body);opacity:.85}}")
	return body, css


# ---- 25. menu board (a menu with leaders and prices, a round photo, leaves) — organic, cafés and restaurants --------
def menu_board(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	rows = "".join(f'<div class="mi"><b>{esc(it.get("title"))}</b><i></i><span>{esc(it.get("text"))}</span></div>' for it in (c.get("items") or [])[:8])
	ink = x.p["dark"]
	body = (f'<div class="layer">{x.pattern(v.get("pattern", "leaves"), base_="light")}</div>'
			f'<div class="wrap"><div class="top">{x.logo(64, light=False)}' + (f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else "") + "</div>"
			f'<h1 class="fit" data-fit data-min="56">{x.m("headline")}</h1>' + (f'<div class="sub">{x.t("subline")}</div>' if x.has("subline") else "")
			+ f'<div class="main"><div class="menu">{rows}</div>' + (f'<div class="ph pic" style="background-image:url({esc(ph)});{x.photo_style("circle")}"></div>' if ph else "")
			+ f'</div><div class="foot">{_contact_line(x, 3)}</div></div>')
	css = (f".post{{background:{x.p['light']};color:{ink}}}.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:50px 60px 46px}}"
		   f".top{{display:flex;justify-content:space-between;align-items:center}}.kick{{font:700 20px var(--font-body);letter-spacing:3px;text-transform:uppercase;color:{x.hl}}}"
		   f"h1{{font:400 {130 if x.tall else 112}px/1 'Satisfy','Dancing Script',var(--font-heading);color:{x.hl};text-align:center;margin-top:10px;max-height:{160 if x.tall else 140}px;white-space:nowrap}}"
		   f"h1 em{{color:{ink}}}.sub{{text-align:center;font:600 22px var(--font-body);letter-spacing:4px;text-transform:uppercase;color:{base.mix(ink, x.p['light'], .3)}}}"
		   f".main{{flex:1;display:{'flex;flex-direction:column-reverse' if x.tall else 'grid;grid-template-columns:1fr 340px'};gap:30px;align-items:center;margin-top:24px;min-height:0}}"
		   f".menu{{width:100%;display:flex;flex-direction:column;gap:{20 if x.tall else 14}px}}"
		   f".mi{{display:flex;align-items:baseline;gap:12px;font:700 {32 if x.tall else 28}px var(--font-heading)}}.mi b{{font-weight:700;max-width:70%}}"
		   f".mi i{{flex:1;border-bottom:3px dotted {base.mix(ink, x.p['light'], .55)};transform:translateY(-6px)}}.mi span{{color:{x.hl};white-space:nowrap}}"
		   f".pic{{width:{520 if x.tall else 340}px;height:{520 if x.tall else 340}px;flex:none;box-shadow:0 24px 50px rgba(0,0,0,.22);border:10px solid #fff}}"
		   f".foot{{text-align:center;font:600 21px var(--font-body);color:{base.mix(ink, x.p['light'], .2)};margin-top:16px}}")
	return body, css


# ---- 26. geometric blocks (colour blocks, a photo block, a circle, a list) — contemporary geometric -----------------
def geo_blocks(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	ph = x.photo(0)
	lst = "".join(f"<li>{esc(t)}</li>" for t in (c.get("list") or [])[:5])
	cta = f'<div class="cta">{x.t("cta")} →</div>' if x.has("cta") else ""
	body = (f'<div class="grid"><div class="b1"><div>{x.logo(56, light=True)}</div>' + (f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else "")
			+ f'<h1 class="fit" data-fit data-min="44">{x.m("headline")}</h1></div>'
			f'<div class="b2 ph" style="background-image:url({esc(ph)})"></div><div class="b3"><div class="ring"></div></div>'
			f'<div class="b4">' + (f'<b>{x.t("list_title")}</b>' if x.has("list_title") else "") + (f"<ul>{lst}</ul>" if lst else (f'<div class="s">{x.m("subline")}</div>' if x.has("subline") else ""))
			+ f'{cta}<div class="ct">{_contact_line(x)}</div></div></div>')
	p = x.p
	css = (f".post{{background:{p['light']}}}.grid{{position:absolute;inset:0;display:grid;gap:0;"
		   f"grid-template-columns:{'1fr' if x.tall else '1.15fr 1fr'};grid-template-rows:{'1.1fr .9fr .55fr 1fr' if x.tall else '1.25fr 1fr'}}}"
		   f".b1{{background:{p['primary']};color:{p['on_primary']};padding:50px 54px;display:flex;flex-direction:column;justify-content:space-between;min-height:0}}"
		   f".kick{{font:700 20px var(--font-body);letter-spacing:4px;text-transform:uppercase;opacity:.85;margin-top:auto}}"
		   f"h1{{font:800 {84 if x.tall else 70}px/1 var(--font-heading);max-height:{300 if x.tall else 300}px;margin-top:10px}}h1 em{{color:{p['accent'] if base.contrast(p['accent'], p['primary']) >= 2.4 else p['on_primary']}}}"
		   f".b2{{min-height:0}}.b3{{background:{p['accent']};position:relative;overflow:hidden;{'display:none' if not x.tall else ''}}}"
		   f".ring{{position:absolute;width:420px;height:420px;border-radius:50%;border:56px solid {base.mix(p['accent'], '#ffffff', .35)};right:-120px;top:-150px}}"
		   f".b4{{background:{p['dark']};color:#fff;padding:44px 50px;display:flex;flex-direction:column;justify-content:center;gap:10px;{'grid-column:1 / -1' if not x.tall else ''};min-height:0}}"
		   f".b4 b{{font:800 30px var(--font-heading)}}.b4 ul{{list-style:none;display:grid;grid-template-columns:{'1fr' if x.tall else '1fr 1fr'};gap:8px 30px;font:500 24px var(--font-body)}}"
		   f".b4 li::before{{content:'';display:inline-block;width:12px;height:12px;background:{p['accent']};margin-right:12px;transform:rotate(45deg)}}"
		   f".s{{font:500 26px/1.4 var(--font-body)}}.cta{{align-self:flex-start;margin-top:8px;color:{p['accent'] if base.contrast(p['accent'], p['dark']) >= 3 else '#fff'};font:800 24px var(--font-heading);text-transform:uppercase;letter-spacing:1px}}"
		   f".ct{{font:500 20px var(--font-body);opacity:.8}}")
	return body, css


# ---- 27. growth stats (results: a big number, three figures, rising bars) — corporate, agencies --------------------
def growth_stats(x: Ctx, v: dict) -> tuple[str, str]:
	c = x.content
	figs = "".join(f'<div class="fg"><b>{esc(it.get("title"))}</b><span>{esc(it.get("text"))}</span></div>' for it in (c.get("items") or [])[:3])
	big = (f'<div class="big"><b class="fit" data-fit data-min="90">{x.t("stat")}</b><span>{x.t("stat_label")}</span></div>' if x.has("stat") else "")
	bars = "".join(f'<i style="height:{h}%"></i>' for h in (28, 40, 36, 52, 61, 74, 92))
	body = (f'<div class="layer">{x.pattern(v.get("pattern", "grid"))}</div><div class="wrap"><div class="top">{x.logo(60)}'
			+ (f'<div class="kick">{x.t("kicker")}</div>' if x.has("kicker") else "") + "</div>"
			f'<h1 class="fit" data-fit data-min="44">{x.m("headline")}</h1><div class="main">{big}<div class="bars">{bars}</div></div>'
			+ (f'<div class="figs">{figs}</div>' if figs else "") + f'<div class="ct">{_contact_line(x, 3)}</div></div>')
	css = (f".wrap{{position:absolute;inset:0;display:flex;flex-direction:column;padding:52px 60px 46px}}.top{{display:flex;justify-content:space-between;align-items:center}}"
		   f".kick{{font:700 20px var(--font-body);letter-spacing:3px;text-transform:uppercase;color:{x.hl}}}"
		   f"h1{{font:800 {72 if x.tall else 60}px/1.05 var(--font-heading);margin-top:28px;max-height:{260 if x.tall else 200}px}}h1 em{{color:{x.hl}}}"
		   f".main{{flex:1;display:flex;align-items:flex-end;gap:30px;margin:20px 0;min-height:0}}"
		   f".big{{flex:none;max-width:52%}}.big b{{display:block;font:900 {230 if x.tall else 190}px/0.9 var(--font-heading);color:{x.hl};max-height:{250 if x.tall else 210}px;white-space:nowrap}}"
		   f".big span{{display:block;font:600 26px var(--font-body);color:{x.soft};margin-top:8px}}"
		   f".bars{{flex:1;height:100%;max-height:{620 if x.tall else 360}px;display:flex;align-items:flex-end;gap:12px}}"
		   f".bars i{{flex:1;border-radius:10px 10px 4px 4px;background:linear-gradient(180deg,{x.hl},{base.mix(x.hl, x.bg, .55)})}}"
		   f".figs{{display:flex;gap:16px}}.fg{{flex:1;border-top:3px solid {x.hl};padding-top:14px}}.fg b{{display:block;font:800 40px var(--font-heading)}}"
		   f".fg span{{font:500 20px/1.3 var(--font-body);color:{x.soft}}}.ct{{margin-top:18px;font:600 20px var(--font-body);color:{x.soft}}}")
	return body, css


LAYOUTS = {"testimonial": testimonial, "editorial_minimal": editorial, "luxury_frame": luxury_frame, "travel_postcard": travel_postcard,
		   "creator_card": creator_card, "product_spotlight": product_spotlight, "bold_type": bold_type, "fitness_power": fitness_power,
		   "menu_board": menu_board, "geo_blocks": geo_blocks, "growth_stats": growth_stats}
