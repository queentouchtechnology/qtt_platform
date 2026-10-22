"""
QTT Studio › Print (PROJ-0012 S4) — visiting cards, flyers and menus / price lists as print-ready pages, in the business's
logo, colours and fonts (no Frappe; tests/test_print.py). Sizes are real millimetres; the print-shop PDF has 3 mm bleed
(colour runs past the cut) and crop marks; nothing important sits within 4 mm of the cut.

  PRODUCTS     key → (name, trim width × height mm, pages, styles)
  fields_for   what a product asks for (and fills from the business: name, contacts, offerings with their own prices)
  clean        the app's words checked (known fields, trimmed; items: name, price, details)
  page         the whole HTML for a product, a style, its words — `marks` adds the bleed and crop marks
  size_px      a page's preview size in pixels

Prices are only ever the business's own (Business › Knowledge › What you offer, or typed here) — never made up.
"""

import html
import re

from qtt_platform.design import elements

BLEED, SLUG, SAFE = 3.0, 6.0, 4.0  # mm: colour past the cut; room for the crop marks; keep words this far inside
PRODUCTS = {
	"card": ("Visiting card", 89, 51, ("front", "back"), ("band", "split", "minimal", "luxe", "gradient")),
	"flyer_a5": ("Flyer (A5)", 148, 210, ("front",), ("photo", "block", "luxe")),
	"flyer_a4": ("Flyer (A4)", 210, 297, ("front",), ("photo", "block", "luxe")),
	"menu": ("Menu / price list (A4)", 210, 297, ("front",), ("classic", "modern", "elegant", "night")),
}
STYLE_NAMES = {"band": "Colour band", "split": "Split", "minimal": "Minimal", "photo": "Big photo", "block": "Colour block",
			   "classic": "Classic", "modern": "Modern", "luxe": "Luxe", "gradient": "Gradient", "elegant": "Elegant", "night": "Night"}
GOLDISH = "#c8a96a"  # a fine champagne line for the luxe styles (beside the brand colour, never instead of it)
# field: (label, max length, multi-line)
FIELDS = {
	"card": (("person", "Name on the card", 60, False), ("role", "Role (Owner, Manager…)", 60, False), ("phone", "Phone", 30, False),
			 ("email", "Email", 80, False), ("website", "Website", 80, False), ("address", "Address", 160, True), ("tagline", "Tagline", 80, False)),
	"flyer": (("headline", "Headline (*word* in colour)", 80, False), ("subline", "A line under it", 160, True),
			  ("points", "Points (one a line, up to 5)", 400, True), ("offer", "Offer badge (only a real offer)", 30, False),
			  ("cta", "Call to action", 50, False), ("phone", "Phone", 30, False), ("website", "Website", 80, False), ("address", "Address", 160, True)),
	"menu": (("headline", "Title", 60, False), ("subline", "A line under it", 160, True), ("hours", "Opening hours", 120, True),
			 ("phone", "Phone", 30, False), ("address", "Address", 160, True), ("note", "A note at the bottom", 160, True)),
}
MAX_ITEMS = 40


def group_of(product: str) -> str:
	return "card" if product == "card" else ("menu" if product == "menu" else "flyer")


def size_px(product: str) -> tuple[int, int]:
	_, w, h, _, _ = PRODUCTS[product]
	return round(w * 96 / 25.4), round(h * 96 / 25.4)


def _e(t) -> str:
	return html.escape(str(t or ""), quote=True)


def _rich(t) -> str:
	"""Words with *stars* → the starred words in the highlight colour; new lines kept."""
	return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", _e(t)).replace("\n", "<br>")


def fields_for(product: str, *, name: str, contacts: dict, knowledge: dict, person: str = "") -> dict:
	"""The words a product starts with, filled from the business (nothing invented: empty when the business hasn't said)."""
	k = knowledge or {}
	c = contacts or {}
	offers = [o for o in k.get("offerings") or [] if o.get("active", 1) and str(o.get("item") or "").strip()]
	g = group_of(product)
	base_ = {"name": name, "phone": c.get("phone") or c.get("whatsapp") or "", "email": c.get("email") or "", "website": c.get("website") or "",
			 "address": c.get("address") or "", "tagline": k.get("tagline") or ""}
	if g == "card":
		return {**base_, "person": person, "role": ""}
	if g == "menu":
		return {**base_, "headline": "Menu" if (k.get("business_type") or "").lower() in ("restaurant", "cafe", "bakery", "hotel") else "Price list",
				"subline": k.get("tagline") or "", "hours": k.get("hours") or "", "note": "",
				"items": [{"name": o["item"], "price": str(o.get("price") or ""), "details": str(o.get("details") or "")[:120],
						   "group": o.get("kind") or ""} for o in offers[:MAX_ITEMS]]}
	return {**base_, "headline": name, "subline": k.get("about") and str(k["about"]).split(".")[0][:150] or k.get("tagline") or "",
			"points": "\n".join(o["item"] for o in offers[:5]), "offer": "", "cta": "Call us today"}


def clean(product: str, words: dict) -> dict:
	"""The app's words → only this product's fields, trimmed; items for a menu."""
	words = words if isinstance(words, dict) else {}
	out = {"name": re.sub(r"\s+", " ", str(words.get("name") or "")).strip()[:80]}
	for key, _label, n, multi in FIELDS[group_of(product)]:
		v = str(words.get(key) or "")
		v = "\n".join(x.strip() for x in v.splitlines() if x.strip()) if multi else re.sub(r"\s+", " ", v).strip()
		out[key] = v[:n]
	if product == "menu":
		items = []
		for it in (words.get("items") or [])[:MAX_ITEMS] if isinstance(words.get("items"), list) else []:
			if isinstance(it, dict) and str(it.get("name") or "").strip():
				items.append({"name": str(it["name"]).strip()[:60], "price": str(it.get("price") or "").strip()[:20],
							  "details": str(it.get("details") or "").strip()[:120], "group": str(it.get("group") or "").strip()[:40]})
		out["items"] = items
	return out


# ---- drawing ---------------------------------------------------------------------------------------------------------
def _qr(text: str, pal: dict, mm: float) -> str:
	px = round(mm * 96 / 25.4)
	return (f'<div class="qr" style="width:{mm}mm;height:{mm}mm;background:#fff;padding:1mm">'
			f'{elements.element("qr", pal, px, px, text=text)}</div>') if text else ""


def _contact_lines(w: dict) -> str:
	rows = [(k, w.get(k)) for k in ("phone", "email", "website", "address") if w.get(k)]
	icons = {"phone": "icon_phone", "email": "icon_mail", "website": "icon_globe", "address": "icon_pin"}
	return "".join(f'<div class="ln"><span class="ic">{elements.element(icons[k], {"accent": "currentColor", "on_accent": "#fff", "primary": "currentColor", "on_primary": "#fff", "dark": "currentColor", "on_dark": "#fff"}, 12, 12)}</span>'
				   f"<span>{_e(v)}</span></div>" for k, v in rows)


def _logo(logo: str | None, cls: str = "logo") -> str:
	return f'<img class="{cls}" src="{_e(logo)}">' if logo else ""


def _card(style: str, side: str, w: dict, pal: dict, logo: str | None) -> str:
	name, person, role = _e(w.get("name")), _e(w.get("person")), _e(w.get("role"))
	link = w.get("website") or (f"tel:{w['phone']}" if w.get("phone") else "")
	if side == "back":
		tag = f'<div class="tg">{_e(w.get("tagline"))}</div>' if w.get("tagline") else ""
		if style == "luxe":
			return (f'<div class="fill lx" style="background:{pal["dark"]};color:#fff"><div class="frame"></div>'
					f'<div class="center">{_logo(logo, "logo big")}<div class="bn spaced">{name}</div>{tag}</div></div>')
		if style == "gradient":
			return (f'<div class="fill" style="background:linear-gradient(135deg,{pal["primary"]},{pal["primary_deep"]});color:{pal["on_primary"]}">'
					f'<div class="center">{_logo(logo, "logo big")}<div class="bn">{name}</div>{tag}</div></div>')
		return (f'<div class="fill" style="background:{pal["primary"]};color:{pal["on_primary"]}">'
				f'<div class="center">{_logo(logo, "logo big")}<div class="bn">{name}</div>{tag}</div></div>')
	if style == "split":
		return (f'<div class="fill row"><div class="side" style="background:{pal["primary"]};color:{pal["on_primary"]}">'
				f'{_logo(logo)}<div class="bn sm">{name}</div></div>'
				f'<div class="main"><div class="pn">{person}</div><div class="rl" style="color:{pal["primary"]}">{role}</div>'
				f'<div class="ct">{_contact_lines(w)}</div></div></div>')
	if style == "minimal":
		return (f'<div class="fill pad"><div class="top">{_logo(logo)}<div class="bn sm" style="color:{pal["primary"]}">{name}</div></div>'
				f'<div class="bottom"><div><div class="pn">{person}</div><div class="rl" style="color:{pal["primary"]}">{role}</div>'
				f'<div class="ct">{_contact_lines(w)}</div></div>{_qr(link, pal, 14)}</div></div>')
	if style == "luxe":
		return (f'<div class="fill lx pad" style="background:{pal["dark"]};color:#fff"><div class="frame"></div>'
				f'<div class="top">{_logo(logo)}<div class="bn sm spaced">{name}</div></div>'
				f'<div class="bottom"><div><div class="pn">{person}</div><div class="rl gold">{role}</div><div class="ct">{_contact_lines(w)}</div></div></div></div>')
	if style == "gradient":
		return (f'<div class="fill pad" style="background:linear-gradient(135deg,{pal["primary"]} 0%,{pal["primary_deep"]} 100%);color:{pal["on_primary"]}">'
				f'<div class="top">{_logo(logo)}<div class="bn sm">{name}</div></div>'
				f'<div class="bottom"><div><div class="pn">{person}</div><div class="rl" style="opacity:.85">{role}</div><div class="ct">{_contact_lines(w)}</div></div>'
				f'{_qr(link, pal, 13)}</div></div>')
	# band
	return (f'<div class="fill"><div class="band" style="background:{pal["primary"]};color:{pal["on_primary"]}">{_logo(logo)}'
			f'<div class="bn sm">{name}</div></div><div class="pad2"><div class="pn">{person}</div>'
			f'<div class="rl" style="color:{pal["primary"]}">{role}</div><div class="ct">{_contact_lines(w)}</div></div>'
			f'<div class="stripe" style="background:{pal["secondary"]}"></div></div>')


def _flyer(style: str, w: dict, pal: dict, logo: str | None, photo: str | None) -> str:
	points = [p for p in (w.get("points") or "").splitlines() if p.strip()][:5]
	pts = "".join(f'<li><span class="dot" style="background:{pal["primary"]}"></span>{_e(p)}</li>' for p in points)
	# the owner's own accent, else a deeper shade of the main colour (a worked-out accent is the opposite colour and can clash)
	tone = "accent" if "accent" in (pal.get("owner") or []) else "secondary"
	badge = (f'<div class="badge" style="background:{pal[tone]};color:{pal["on_" + tone]}">{_e(w["offer"])}</div>' if w.get("offer") else "")
	link = w.get("website") or (f"tel:{w['phone']}" if w.get("phone") else "")
	foot = (f'<div class="foot" style="background:{pal["dark"]};color:#fff"><div class="ct">{_contact_lines(w)}</div>'
			f'{_qr(link, pal, 22)}</div>')
	head = f'<div class="head">{_logo(logo)}<div class="bn sm">{_e(w.get("name"))}</div></div>'
	cta = (f'<div class="cta" style="background:{pal["primary"]};color:{pal["on_primary"]}">{_e(w.get("cta"))}</div>' if w.get("cta") else "")
	if style == "luxe":
		pic = f'<div class="arch" style="background-image:url({_e(photo)})"></div>' if photo else ""
		lfoot = f'<div class="lfoot"><div class="ct">{_contact_lines(w)}</div>{_qr(link, pal, 18)}</div>'
		cta_l = f'<div class="lxcta">{_e(w.get("cta"))}</div>' if w.get("cta") else ""
		return (f'<div class="fill col lx" style="background:radial-gradient(120% 80% at 50% 25%,{pal["primary_deep"]},{pal["dark"]} 70%);color:#fff">'
				f'<div class="frame"></div><div class="lxin">{_logo(logo)}<div class="bn sm spaced">{_e(w.get("name"))}</div>{pic}'
				f'<h1 class="serif">{_rich(w.get("headline"))}</h1><div class="sub">{_rich(w.get("subline"))}</div>'
				f'<ul class="lxl">{pts}</ul>{cta_l}{badge}</div>{lfoot}</div>')
	if style == "block":
		return (f'<div class="fill col"><div class="hero block" style="background:{pal["primary"]};color:{pal["on_primary"]}">{head}'
				f'<h1>{_rich(w.get("headline"))}</h1><div class="sub">{_rich(w.get("subline"))}</div>{badge}</div>'
				f'<div class="body"><ul>{pts}</ul>{cta}</div>{foot}</div>')
	ph = f'style="background-image:url(\'{_e(photo)}\')"' if photo else f'style="background:{pal["primary_soft"]}"'
	return (f'<div class="fill col"><div class="photo" {ph}><div class="scrim"></div>{badge}</div>'
			f'<div class="body">{head}<h1 class="dk">{_rich(w.get("headline"))}</h1><div class="sub dk">{_rich(w.get("subline"))}</div>'
			f'<ul>{pts}</ul>{cta}</div>{foot}</div>')


def _menu(style: str, w: dict, pal: dict, logo: str | None) -> str:
	groups: dict[str, list] = {}
	for it in w.get("items") or []:
		groups.setdefault(it.get("group") or "", []).append(it)
	sections = ""
	for g, items in groups.items():
		rows = ""
		for i in items:
			dt = f'<div class="dt">{_e(i["details"])}</div>' if i.get("details") else ""
			rows += (f'<tr><td class="it"><b>{_e(i["name"])}</b>{dt}</td><td class="dots"></td>'
					 f'<td class="pr">{_e(i.get("price"))}</td></tr>')
		h2 = f'<h2 style="color:{pal["primary"]}">{_e(g)}</h2>' if g else ""
		sections += f'<div class="sec">{h2}<table>{rows}</table></div>'
	if style in ("elegant", "night"):
		night = style == "night"
		top = (f'<div class="mtop">{_logo(logo)}<div class="bn spaced">{_e(w.get("name"))}</div><div class="orn"><i></i><b>✦</b><i></i></div>'
			   f'<h1 class="serif">{_rich(w.get("headline"))}</h1><div class="sub">{_rich(w.get("subline"))}</div></div>')
		hours = f'<div><b>{_e(w.get("hours_label") or "Hours")}</b><br>{_e(w.get("hours")).replace(chr(10), "<br>")}</div>' if w.get("hours") else ""
		note = f'<div class="note">{_rich(w.get("note"))}</div>' if w.get("note") else ""
		bottom = f'<div class="mfoot">{hours}<div class="ct">{_contact_lines(w)}</div>{note}</div>'
		bg = f'background:{pal["dark"]};color:#fff' if night else f'background:{pal["light"]};color:{pal["dark"]}'
		return f'<div class="fill col menu {style}" style="{bg}"><div class="frame"></div>{top}<div class="mbody">{sections}</div>{bottom}</div>'
	modern = style == "modern"
	top = (f'<div class="mtop" style="background:{pal["primary"] if modern else "transparent"};color:{pal["on_primary"] if modern else pal["dark"]}">'
		   f'{_logo(logo)}<div class="bn">{_e(w.get("name"))}</div><h1 style="color:{"inherit" if modern else pal["primary"]}">{_rich(w.get("headline"))}</h1>'
		   f'<div class="sub">{_rich(w.get("subline"))}</div></div>')
	hours = f'<div><b>{_e(w.get("hours_label") or "Hours")}</b><br>{_e(w.get("hours")).replace(chr(10), "<br>")}</div>' if w.get("hours") else ""
	note = f'<div class="note">{_rich(w.get("note"))}</div>' if w.get("note") else ""
	bottom = (f'<div class="mfoot" style="border-top:2px solid {pal["primary"]}">{hours}'
			  f'<div class="ct">{_contact_lines(w)}</div>{note}</div>')
	return f'<div class="fill col menu {style}">{top}<div class="mbody">{sections}</div>{bottom}</div>'


def _css(product: str, pal: dict, fonts: dict, marks: bool) -> str:
	_, tw, th, _, _ = PRODUCTS[product]
	off = SLUG if marks else 0
	pw, ph = tw + 2 * BLEED + 2 * off, th + 2 * BLEED + 2 * off
	scale = 0.62 if product == "card" else (1.0 if product == "flyer_a5" else 1.4)  # type sizes grow with the page
	return (f"@page{{size:{pw}mm {ph}mm;margin:0}}*{{box-sizing:border-box;margin:0;padding:0}}"
			f"html,body{{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}}"
			f":root{{--h:{fonts['css_heading']};--b:{fonts['css_body']}}}"
			f"body{{font-family:var(--b);color:{pal['dark']}}}h1,h2,.bn,.pn{{font-family:var(--h)}}"
			f".pg{{position:relative;width:{pw}mm;height:{ph}mm;overflow:hidden;page-break-after:always}}"
			f".art{{position:absolute;left:{off}mm;top:{off}mm;width:{tw + 2 * BLEED}mm;height:{th + 2 * BLEED}mm;overflow:hidden}}"
			f".fill{{position:absolute;inset:0;padding:{BLEED + SAFE}mm}}"
			f".fill.row{{display:flex;padding:0}}.fill.col{{display:flex;flex-direction:column;padding:0}}"
			f".mk{{position:absolute;background:#000}}"
			f"em{{font-style:normal;color:{pal['accent'] if 'accent' in (pal.get('owner') or []) else pal['secondary']}}}"
			f".logo{{max-height:{9 * scale}mm;max-width:{30 * scale}mm;object-fit:contain}}.logo.big{{max-height:16mm;max-width:40mm;margin-bottom:2mm}}"
			f".bn{{font-weight:800;font-size:{16 * scale}pt;line-height:1.1}}.bn.sm{{font-size:{11 * scale}pt}}.tg{{font-size:{8 * scale}pt;opacity:.85;margin-top:1mm}}"
			f".pn{{font-weight:800;font-size:{13 * scale}pt}}.rl{{font-weight:600;font-size:{8.5 * scale}pt;margin:.6mm 0 2mm}}"
			f".ct .ln{{display:flex;align-items:center;gap:1.5mm;font-size:{7.5 * scale}pt;line-height:1.5}}.ic svg{{width:{2.8 * scale}mm;height:{2.8 * scale}mm;display:block}}"
			f".center{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}}"
			f".side{{width:38%;padding:{BLEED + SAFE}mm {SAFE}mm {BLEED + SAFE}mm {BLEED + SAFE}mm;display:flex;flex-direction:column;justify-content:center;gap:2mm}}"
			f".main{{flex:1;padding:{BLEED + SAFE}mm {BLEED + SAFE}mm {BLEED + SAFE}mm {SAFE}mm;display:flex;flex-direction:column;justify-content:center}}"
			f".pad{{display:flex;flex-direction:column;justify-content:space-between}}.top{{display:flex;align-items:center;gap:2mm}}"
			f".bottom{{display:flex;justify-content:space-between;align-items:flex-end}}"
			f".band{{position:absolute;left:0;right:0;top:0;height:42%;display:flex;align-items:center;gap:2.5mm;padding:{BLEED}mm {BLEED + SAFE}mm 0}}"
			f".pad2{{position:absolute;left:0;right:0;top:46%;padding:0 {BLEED + SAFE}mm}}.stripe{{position:absolute;left:0;right:0;bottom:0;height:{BLEED + 1.2}mm}}"
			f".head{{display:flex;align-items:center;gap:3mm;margin-bottom:4mm}}"
			f".hero{{padding:{BLEED + SAFE + 4}mm {BLEED + SAFE + 2}mm {8 * scale}mm;position:relative}}"
			f".photo{{height:42%;background-size:cover;background-position:center;position:relative}}"
			f".scrim{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 55%,rgba(0,0,0,.25))}}"
			f"h1{{font-size:{26 * scale}pt;line-height:1.08;font-weight:800;margin:2mm 0 3mm}}h1.dk{{color:{pal['dark']}}}"
			f".sub{{font-size:{10.5 * scale}pt;line-height:1.45;opacity:.92}}"
			f".body{{flex:1;padding:{6 * scale}mm {BLEED + SAFE + 2}mm}}ul{{list-style:none;margin:{4 * scale}mm 0}}"
			f"li{{display:flex;align-items:center;gap:2.5mm;font-size:{10.5 * scale}pt;font-weight:600;margin:{1.8 * scale}mm 0}}"
			f".dot{{width:{2.4 * scale}mm;height:{2.4 * scale}mm;border-radius:50%;flex:none}}"
			f".cta{{display:inline-block;padding:{2.2 * scale}mm {5 * scale}mm;border-radius:99px;font-weight:800;font-size:{10.5 * scale}pt;margin-top:2mm}}"
			f".badge{{position:absolute;right:{BLEED + SAFE + 2}mm;top:{BLEED + SAFE + 2}mm;width:{24 * scale}mm;height:{24 * scale}mm;border-radius:50%;"
			f"display:flex;align-items:center;justify-content:center;text-align:center;font-weight:900;font-size:{11 * scale}pt;line-height:1.05;padding:2mm;transform:rotate(-8deg)}}"
			f".foot{{display:flex;justify-content:space-between;align-items:center;padding:{5 * scale}mm {BLEED + SAFE + 2}mm {BLEED + SAFE}mm}}"
			f".foot .ln{{font-size:{8.5 * scale}pt}}"
			f".mtop{{padding:{BLEED + SAFE + 4}mm {BLEED + SAFE + 4}mm {6}mm;text-align:center}}.mtop .logo{{margin-bottom:2mm}}"
			f".mtop h1{{margin:3mm 0 2mm}}.mbody{{flex:1;padding:4mm {BLEED + SAFE + 6}mm;columns:{2 if product == 'menu' else 1};column-gap:10mm}}"
			f".sec{{break-inside:avoid;margin-bottom:{6 * scale}mm}}.sec h2{{font-size:{11 * scale}pt;margin-bottom:{2 * scale}mm;text-transform:uppercase;letter-spacing:.06em}}"
			f".sec table{{width:100%;border-collapse:collapse}}.sec td{{padding:{1.4 * scale}mm 0;vertical-align:bottom;font-size:{9 * scale}pt}}"
			f".it{{max-width:60mm}}.dt{{font-size:{7 * scale}pt;opacity:.7;font-weight:400}}.dots{{border-bottom:1px dotted #9aa3b2;width:30%}}.pr{{text-align:right;font-weight:800;white-space:nowrap;padding-left:2mm}}"
			f".mfoot{{margin:0 {BLEED + SAFE + 6}mm {BLEED + SAFE}mm;padding-top:3mm;display:flex;gap:8mm;font-size:{7.5 * scale}pt;justify-content:space-between}}"
			f".note{{font-style:italic;max-width:60mm}}"
			# premium styles: fine frames, spaced capitals, serif titles, ornaments
			f".frame{{position:absolute;inset:{BLEED + 2.2}mm;border:.35mm solid {GOLDISH};pointer-events:none}}"
			f".frame::after{{content:'';position:absolute;inset:1.2mm;border:.2mm solid {GOLDISH};opacity:.55}}"
			f".spaced{{letter-spacing:.22em;text-transform:uppercase;font-weight:600}}.gold{{color:{GOLDISH}}}"
			f".serif{{font-family:Georgia,'Playfair Display',serif;font-weight:500;letter-spacing:.01em}}"
			f".lx .ct .ln{{opacity:.92}}.lxin{{flex:1;display:flex;flex-direction:column;align-items:center;text-align:center;"
			f"padding:{BLEED + SAFE + 6 * scale}mm {BLEED + SAFE + 8}mm 0;gap:{2.5 * scale}mm;position:relative;min-height:0}}"
			f".arch{{width:62%;flex:1;min-height:30mm;max-height:42%;border-radius:999px 999px 3mm 3mm;background-size:cover;background-position:center;"
			f"outline:.35mm solid {GOLDISH};outline-offset:1.6mm;margin:{2 * scale}mm 0}}"
			f".lxl{{list-style:none;margin:1mm 0}}.lxl li{{justify-content:center;font-weight:500}}.lxl .dot{{display:none}}"
			f".lxcta{{border:.35mm solid {GOLDISH};color:{GOLDISH};padding:{1.8 * scale}mm {6 * scale}mm;font-weight:700;letter-spacing:.18em;"
			f"text-transform:uppercase;font-size:{9 * scale}pt}}.lx .badge{{position:static;transform:none;margin-top:1mm}}"
			f".lfoot{{display:flex;justify-content:space-between;align-items:center;padding:{4 * scale}mm {BLEED + SAFE + 6}mm {BLEED + SAFE + 4}mm;position:relative}}"
			f".menu.elegant .mtop,.menu.night .mtop{{position:relative;padding-top:{BLEED + SAFE + 8}mm}}"
			f".orn{{display:flex;align-items:center;justify-content:center;gap:3mm;margin:2mm 0;color:{GOLDISH}}}.orn i{{width:18mm;height:.3mm;background:{GOLDISH}}}"
			f".menu.elegant h2,.menu.night h2{{font-family:Georgia,serif;font-weight:500;letter-spacing:.2em;text-align:center;border-bottom:.3mm solid {GOLDISH};padding-bottom:1.5mm}}"
			f".menu.elegant .it b,.menu.night .it b{{font-variant:small-caps;letter-spacing:.04em;font-weight:600}}"
			f".menu.night .pr{{color:{GOLDISH}}}.menu.night .dots{{border-color:rgba(255,255,255,.35)}}.menu.elegant .pr{{color:{pal['primary']}}}"
			f".menu.elegant .mfoot,.menu.night .mfoot{{border-top:.3mm solid {GOLDISH};position:relative}}"
			f".menu.night h2{{color:{GOLDISH}!important}}"  # the main colour can be too dark on the night page
			f".fill.lx.pad{{padding:{BLEED + SAFE + 2.6}mm {BLEED + SAFE + 3}mm}}"  # words clear of the fine frame
			)


def _marks(product: str) -> str:
	"""Crop marks at the four corners of the cut, in the room outside the bleed."""
	_, tw, th, _, _ = PRODUCTS[product]
	x0, y0, x1, y1 = SLUG + BLEED, SLUG + BLEED, SLUG + BLEED + tw, SLUG + BLEED + th
	L, t = SLUG - 1, 0.25
	out = []
	for x in (x0, x1):
		for y in (y0, y1):
			out.append(f'<div class="mk" style="left:{x - t / 2}mm;top:{(y - L - BLEED) if y == y0 else (y + BLEED)}mm;width:{t}mm;height:{L}mm"></div>')
			out.append(f'<div class="mk" style="top:{y - t / 2}mm;left:{(x - L - BLEED) if x == x0 else (x + BLEED)}mm;height:{t}mm;width:{L}mm"></div>')
	return "".join(out)


def page(product: str, style: str, words: dict, pal: dict, fonts: dict, *, logo: str | None = None, photo: str | None = None,
		 marks: bool = False, only: str | None = None) -> str:
	"""The whole HTML: every side of the product (or `only` one, for a picture), with bleed; `marks`: crop marks too."""
	_, tw, th, sides, styles = PRODUCTS[product]
	style = style if style in styles else styles[0]
	pages = []
	for side in sides:
		if only and side != only:
			continue
		if product == "card":
			art = _card(style, side, words, pal, logo)
		elif product == "menu":
			art = _menu(style, words, pal, logo)
		else:
			art = _flyer(style, words, pal, logo, photo)
		pages.append(f'<div class="pg"><div class="art">{art}</div>{_marks(product) if marks else ""}</div>')
	links = "".join(f'<link rel="stylesheet" href="{_e(u)}">' for u in (fonts.get("urls") or [fonts.get("url")]) if u)
	return (f'<!doctype html><html><head><meta charset="utf-8">{links}<style>{_css(product, pal, fonts, marks)}</style></head>'
			f'<body>{"".join(pages)}<script>(async()=>{{try{{await document.fonts.ready}}catch(e){{}}window.qttReady=true}})()</script></body></html>')
