"""
QTT Studio › Landing pages (PROJ-0012 S7) — one-page sites for an offer, an event, a product launch or the business
itself, in its logo, colours and fonts; fast (no scripts), readable on a phone, with search and sharing tags. No Frappe;
tests/test_pages.py. Every word is the owner's own or from its Business knowledge — never a made-up review, price or date.

  KINDS        offer, event, launch, general — and the sections each starts with
  SECTIONS     hero, points, offer, event, gallery, faq, contact
  start        a page's first words, filled from the business
  clean        the app's page checked (known sections and fields, trimmed, a safe link)
  slugify      the page's address ("Pongal offer" → "pongal-offer")
  html         the whole page
"""

import html as _html
import re
from urllib.parse import quote

KINDS = {
	"offer": ("Offer", ("hero", "offer", "points", "gallery", "contact")),
	"event": ("Event", ("hero", "event", "points", "gallery", "contact")),
	"launch": ("Product launch", ("hero", "points", "gallery", "faq", "contact")),
	"general": ("About the business", ("hero", "points", "gallery", "faq", "contact")),
}
SECTIONS = ("hero", "points", "offer", "event", "gallery", "faq", "contact")
CTAS = ("whatsapp", "call", "link")
MAX_POINTS, MAX_PHOTOS, MAX_FAQ = 6, 8, 8


def _e(t) -> str:
	return _html.escape(str(t or ""), quote=True)


def _rich(t) -> str:
	return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", _e(t)).replace("\n", "<br>")


def _s(v, n: int) -> str:
	return re.sub(r"[ \t]+", " ", str(v or "")).strip()[:n]


def slugify(text: str) -> str:
	s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:50].strip("-")
	return s or "page"


def _digits(phone: str) -> str:
	d = re.sub(r"\D", "", phone or "")
	return ("91" + d) if len(d) == 10 else d


def _safe_link(url: str) -> str:
	u = _s(url, 300)
	if re.match(r"^https?://[^\s<>\"']+$", u, re.I):
		return u
	if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/[^\s<>\"']*)?$", u, re.I):
		return "https://" + u
	return ""


def start(kind: str, *, name: str, knowledge: dict, contacts: dict) -> dict:
	"""A page's first words for its kind, filled from the business — the owner changes them before publishing."""
	k, c = knowledge or {}, contacts or {}
	kind = kind if kind in KINDS else "general"
	offers = [o for o in k.get("offerings") or [] if o.get("active", 1) and str(o.get("item") or "").strip()]
	faqs = [f for f in k.get("faqs") or [] if f.get("active", 1) and str(f.get("question") or "").strip() and str(f.get("answer") or "").strip()]
	headline = {"offer": "A special offer from *" + name + "*", "event": "Join us", "launch": "Something *new* at " + name,
				"general": name}[kind]
	return {
		"kind": kind, "title": {"offer": "Offer", "event": "Event", "launch": "New", "general": name}[kind],
		"sections": list(KINDS[kind][1]),
		"hero": {"kicker": name if kind != "general" else (k.get("tagline") or ""), "headline": headline,
				 "subline": str(k.get("about") or "").split("\n")[0][:220], "cta": "whatsapp" if (c.get("whatsapp") or c.get("phone")) else "link",
				 "cta_label": "Chat on WhatsApp" if (c.get("whatsapp") or c.get("phone")) else "Visit us", "link": c.get("website") or "", "photo": ""},
		"points": [{"title": o["item"], "text": str(o.get("details") or "")[:160]} for o in offers[:4]],
		"offer": {"title": "", "price": "", "old_price": "", "until": "", "terms": ""},
		"event": {"date": "", "time": "", "place": c.get("address") or "", "map_link": k.get("map_link") or ""},
		"gallery": [],
		"faq": [{"q": f["question"][:160], "a": str(f["answer"])[:500]} for f in faqs[:MAX_FAQ]],
		"seo": {"title": "", "description": str(k.get("about") or "")[:155]},
	}


def clean(page: dict) -> dict:
	"""The app's page → only known sections and fields, trimmed; a link only when it's a real web address."""
	p = page if isinstance(page, dict) else {}
	h = p.get("hero") if isinstance(p.get("hero"), dict) else {}
	o = p.get("offer") if isinstance(p.get("offer"), dict) else {}
	ev = p.get("event") if isinstance(p.get("event"), dict) else {}
	seo = p.get("seo") if isinstance(p.get("seo"), dict) else {}
	pts = [x for x in p.get("points") or [] if isinstance(x, dict)] if isinstance(p.get("points"), list) else []
	faq = [x for x in p.get("faq") or [] if isinstance(x, dict)] if isinstance(p.get("faq"), list) else []
	gal = [str(x) for x in p.get("gallery") or [] if isinstance(x, str)] if isinstance(p.get("gallery"), list) else []
	return {
		"kind": p.get("kind") if p.get("kind") in KINDS else "general",
		"title": _s(p.get("title"), 80),
		"sections": [s for s in dict.fromkeys(p.get("sections") or []) if s in SECTIONS] or ["hero", "contact"],
		"hero": {"kicker": _s(h.get("kicker"), 60), "headline": _s(h.get("headline"), 100), "subline": _s(h.get("subline"), 300),
				 "cta": h.get("cta") if h.get("cta") in CTAS else "whatsapp", "cta_label": _s(h.get("cta_label"), 40) or "Contact us",
				 "link": _safe_link(h.get("link") or ""), "photo": _s(h.get("photo"), 40)},
		"points": [{"title": _s(x.get("title"), 70), "text": _s(x.get("text"), 220)} for x in pts if _s(x.get("title"), 70)][:MAX_POINTS],
		"offer": {"title": _s(o.get("title"), 80), "price": _s(o.get("price"), 30), "old_price": _s(o.get("old_price"), 30),
				  "until": _s(o.get("until"), 60), "terms": _s(o.get("terms"), 300)},
		"event": {"date": _s(ev.get("date"), 60), "time": _s(ev.get("time"), 60), "place": _s(ev.get("place"), 200),
				  "map_link": _safe_link(ev.get("map_link") or "")},
		"gallery": [_s(x, 40) for x in gal][:MAX_PHOTOS],
		"faq": [{"q": _s(x.get("q"), 160), "a": _s(x.get("a"), 600)} for x in faq if _s(x.get("q"), 160) and _s(x.get("a"), 600)][:MAX_FAQ],
		"seo": {"title": _s(seo.get("title"), 70), "description": _s(seo.get("description"), 160)},
	}


def _cta(page: dict, contacts: dict, *, label: str | None = None) -> str:
	h = page["hero"]
	phone = contacts.get("whatsapp") or contacts.get("phone") or ""
	if h["cta"] == "whatsapp" and _digits(phone):
		text = quote(f"Hi, I saw {page.get('title') or 'your page'}")
		href = f"https://wa.me/{_digits(phone)}?text={text}"
	elif h["cta"] == "call" and (contacts.get("phone") or phone):
		href = "tel:+" + _digits(contacts.get("phone") or phone)
	else:
		href = h["link"] or contacts.get("website_url") or ""
	if not href:
		return ""
	return f'<a class="btn" href="{_e(href)}" rel="noopener">{_e(label or h["cta_label"])}</a>'


def html(page: dict, *, name: str, pal: dict, fonts: dict, contacts: dict, knowledge: dict, logo_url: str | None, photos: dict,
		 url: str = "", noindex: bool = False) -> str:
	"""The whole page. `photos`: {photo name: its public address} (the business's own photos)."""
	p = page
	h = p["hero"]
	c = contacts or {}
	k = knowledge or {}
	parts = []
	hero_photo = photos.get(h.get("photo")) or next(iter(photos.values()), None) if photos else None
	for s in p["sections"]:
		if s == "hero":
			bg = (f"background-image:linear-gradient(180deg,rgba(0,0,0,.35),rgba(0,0,0,.6)),url('{_e(hero_photo)}')" if hero_photo
				  else f"background:{pal['primary']}")
			parts.append(f'<header class="hero" style="{bg}"><div class="wrap">'
						 + (f'<img class="logo" src="{_e(logo_url)}" alt="{_e(name)}">' if logo_url else "")
						 + (f'<p class="kick">{_e(h["kicker"])}</p>' if h["kicker"] else "")
						 + f'<h1>{_rich(h["headline"] or name)}</h1>'
						 + (f'<p class="sub">{_rich(h["subline"])}</p>' if h["subline"] else "")
						 + _cta(p, c) + "</div></header>")
		elif s == "points" and p["points"]:
			cards = ""
			for x in p["points"]:
				body = f'<p>{_e(x["text"])}</p>' if x["text"] else ""
				cards += f'<div class="card"><h3>{_e(x["title"])}</h3>{body}</div>'
			parts.append(f'<section><div class="wrap"><div class="grid">{cards}</div></div></section>')
		elif s == "offer" and (p["offer"]["title"] or p["offer"]["price"]):
			o = p["offer"]
			price = (f'<div class="price">{_e(o["price"])}' + (f' <s>{_e(o["old_price"])}</s>' if o["old_price"] else "") + "</div>") if o["price"] else ""
			parts.append('<section class="offer"><div class="wrap"><div class="box">'
						 + (f'<h2>{_rich(o["title"])}</h2>' if o["title"] else "") + price
						 + (f'<p class="until">Until {_e(o["until"])}</p>' if o["until"] else "")
						 + (f'<p class="terms">{_e(o["terms"])}</p>' if o["terms"] else "") + _cta(p, c) + "</div></div></section>")
		elif s == "event" and (p["event"]["date"] or p["event"]["place"]):
			ev = p["event"]
			rows = "".join(f'<div class="row"><b>{label}</b><span>{_e(v)}</span></div>' for label, v in
						   (("When", " · ".join(x for x in (ev["date"], ev["time"]) if x)), ("Where", ev["place"])) if v)
			mp = f'<a class="link" href="{_e(ev["map_link"])}" rel="noopener">Open in Maps</a>' if ev["map_link"] else ""
			parts.append(f'<section><div class="wrap"><div class="box event">{rows}{mp}</div></div></section>')
		elif s == "gallery":
			urls = [photos[n] for n in p["gallery"] if n in photos] or ([u for u in photos.values() if u != hero_photo][:6] if photos else [])
			if urls:
				imgs = "".join(f'<img src="{_e(u)}" alt="" loading="lazy">' for u in urls)
				parts.append(f'<section><div class="wrap"><div class="gallery">{imgs}</div></div></section>')
		elif s == "faq" and p["faq"]:
			items = "".join(f"<details><summary>{_e(x['q'])}</summary><p>{_e(x['a'])}</p></details>" for x in p["faq"])
			parts.append(f'<section><div class="wrap"><h2>Questions</h2>{items}</div></section>')
		elif s == "contact":
			rows = []
			for label, v in (("Phone", c.get("phone")), ("WhatsApp", c.get("whatsapp")), ("Email", c.get("email")), ("Address", c.get("address")),
							 ("Hours", k.get("hours"))):
				if v:
					rows.append(f'<div class="row"><b>{label}</b><span>{_e(v).replace(chr(10), "<br>")}</span></div>')
			mp = _safe_link(k.get("map_link") or "")
			if mp:
				rows.append(f'<a class="link" href="{_e(mp)}" rel="noopener">Open in Maps</a>')
			if rows:
				parts.append(f'<section class="contact"><div class="wrap"><h2>Contact {_e(name)}</h2><div class="box">{"".join(rows)}</div>'
							 f'{_cta(p, c)}</div></section>')
	title = p["seo"]["title"] or (f"{p['title']} · {name}" if p["title"] and p["title"] != name else name)
	desc = p["seo"]["description"] or h["subline"][:155]
	links = "".join(f'<link rel="stylesheet" href="{_e(u)}">' for u in (fonts.get("urls") or [fonts.get("url")]) if u)
	accent = pal["accent"] if "accent" in (pal.get("owner") or []) else pal["secondary"]
	css = (f":root{{--p:{pal['primary']};--d:{pal['dark']};--a:{accent};--l:{pal['light']}}}*{{box-sizing:border-box;margin:0;padding:0}}"
		   f"body{{font-family:{fonts['css_body']};color:var(--d);background:#fff;line-height:1.55;font-size:17px}}"
		   f"h1,h2,h3{{font-family:{fonts['css_heading']};line-height:1.15}}em{{font-style:normal;color:var(--a)}}"
		   ".wrap{max-width:980px;margin:0 auto;padding:0 20px}section{padding:44px 0}"
		   ".hero{color:#fff;background-size:cover;background-position:center;padding:64px 0 72px;text-align:center}"
		   ".hero em{color:#fff;background:var(--p);padding:0 .25em;border-radius:.2em}"
		   ".logo{max-height:64px;max-width:200px;background:#fff;padding:8px;border-radius:12px;margin-bottom:18px}"
		   ".kick{text-transform:uppercase;letter-spacing:.12em;font-weight:700;font-size:14px;opacity:.9}"
		   "h1{font-size:clamp(32px,7vw,56px);font-weight:800;margin:10px 0 14px}.sub{font-size:19px;max-width:640px;margin:0 auto 26px;opacity:.95}"
		   ".btn{display:inline-block;background:var(--p);color:#fff;text-decoration:none;font-weight:800;padding:15px 30px;border-radius:999px;"
		   "margin-top:8px;box-shadow:0 6px 18px rgba(0,0,0,.18)}.hero .btn{background:#fff;color:var(--p)}"
		   ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}"
		   ".card{background:var(--l);border-radius:16px;padding:20px}.card h3{font-size:19px;margin-bottom:6px;color:var(--p)}"
		   "h2{font-size:28px;margin-bottom:16px}.box{background:var(--l);border-radius:18px;padding:24px}"
		   ".offer .box{text-align:center;border:3px solid var(--p);background:#fff}.price{font-size:44px;font-weight:800;color:var(--p);margin:8px 0}"
		   ".price s{font-size:22px;color:#8a93a3;font-weight:600}.until{font-weight:700}.terms{font-size:14px;color:#5b6475;margin:10px 0}"
		   ".row{display:flex;gap:14px;padding:8px 0;border-bottom:1px solid rgba(0,0,0,.06)}.row b{min-width:96px}"
		   ".link{display:inline-block;margin-top:12px;color:var(--p);font-weight:700}"
		   ".gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}"
		   ".gallery img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:14px}"
		   "details{background:var(--l);border-radius:14px;padding:14px 18px;margin-bottom:10px}summary{font-weight:700;cursor:pointer}"
		   "details p{margin-top:8px}.contact .btn{margin-top:20px}"
		   "footer{text-align:center;font-size:13px;color:#8a93a3;padding:26px 0 40px}footer a{color:inherit}")
	og = (f'<meta property="og:title" content="{_e(title)}"><meta property="og:description" content="{_e(desc)}">'
		  + (f'<meta property="og:image" content="{_e(hero_photo)}">' if hero_photo else "")
		  + (f'<meta property="og:url" content="{_e(url)}"><link rel="canonical" href="{_e(url)}">' if url else "")
		  + '<meta property="og:type" content="website"><meta name="twitter:card" content="summary_large_image">')
	robots = '<meta name="robots" content="noindex,nofollow">' if noindex else ""
	return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
			f'<title>{_e(title)}</title><meta name="description" content="{_e(desc)}">{og}{robots}<meta name="theme-color" content="{pal["primary"]}">'
			f'{links}<style>{css}</style></head><body>{"".join(parts)}'
			f'<footer>© {_e(name)} · Made with QTT Studio</footer></body></html>')
