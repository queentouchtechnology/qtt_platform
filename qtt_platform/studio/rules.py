"""
QTT Studio (PROJ-0012 S0) — the pure rules: the product, its plans, what AI actions cost, and the AI's "make a post"
prompt and the checks on its answer. No Frappe; tests/test_studio.py.

Studio is a product of its own (QTT_STUDIO). Everything QTT already made stays free with the other products (the post
template library, its ready words, website kits, brand kit, photos and Remove background, default documents); making
anything new — a design of your own, AI-written words, AI edits — needs a Studio plan. Prices and limits are seeded
once and then edited in Desk (QTT Plan).
"""

import json
import re

PRODUCT = "QTT_STUDIO"
ROLES = ("Studio Admin", "Designer")

# (code, name, monthly price ₹, features) — seeded once, edited in Desk afterwards. A limit of 0 means unlimited.
PLANS = (
	("STARTER", "Studio Starter", 499, {"studio_designs": 30, "ai_credits_grant": 100, "studio_photos": 50, "studio_shorts": 2,
										"studio_pages": 0, "studio_doc_templates": 3, "studio_design_mode": 0}),
	("GROWTH", "Studio Growth", 999, {"studio_designs": 100, "ai_credits_grant": 400, "studio_photos": 200, "studio_shorts": 10,
									  "studio_pages": 1, "studio_doc_templates": 10, "studio_design_mode": 1}),
	("PRO", "Studio Pro", 1999, {"studio_designs": 400, "ai_credits_grant": 1200, "studio_photos": 600, "studio_shorts": 30,
								 "studio_pages": 5, "studio_doc_templates": 0, "studio_design_mode": 1}),
)
TRIAL_DAYS = 14

# AI credits each action takes (the plan's ai_credits_grant arrives every month; more can be bought).
CREDITS = {"make": 1, "ask": 1, "letter": 1, "short_script": 2, "read_image": 3, "ai_background": 10, "ai_logo": 20}

# What can be made, and from which phase (S0: posts, S1: Photo Lab; the rest arrive phase by phase).
CATEGORIES = (
	("posts", "Social posts", "post", True),
	("documents", "Business documents", "document", True),  # S3: letterhead styles and letters
	("logos", "Logo and brand", "logo", True),  # S5
	("print", "Cards, flyers and menus", "print", True),  # S4 (brochures later)
	("photos", "Photo Lab", "photo", True),  # S1
	("shorts", "Shorts and video", "video", True),  # S6
	("pages", "Landing pages", "page", True),  # S7
)
KINDS = ("post", "document", "logo", "print", "photo", "video", "page")
FORMATS = ("square", "portrait", "story")
WIDE = ("wide", "landscape")  # 16:9 and 3:2 — showcase designs (Poster variations) only
LOOKS = ("light", "dark", "brand")
SLOTS = {"kicker": 60, "headline": 90, "subline": 220, "cta": 40, "badge": 30, "tagline": 80, "quote": 160, "stat": 16, "stat_label": 50,
		 "before_label": 24, "after_label": 24}  # before-and-after posters: the two screens' labels
LIST_SLOTS = {"list": (10, 30), "steps": (4, 40), "problems": (4, 90)}  # the owner's own short lists: (how many, how long)


def limit_left(limit, used: int) -> int | None:
	"""How many are left this month (None: unlimited — a limit of 0 or less)."""
	try:
		n = int(float(limit))
	except (TypeError, ValueError):
		return 0
	return None if n <= 0 else max(0, n - used)


# ---- AI: make a post --------------------------------------------------------------------------------------------------
def make_prompt(*, request: str, brief: str, language: str, templates: list[dict], ideas: list[dict]) -> list[dict]:
	"""The owner's request + the business brief + the design library → JSON {template, look, words}."""
	lib = "\n".join(f"- {t['key']}: {t['label']} — for {', '.join(t['post_types'])}" for t in templates)
	ready = "\n".join(f"- {i['key']}: {i['headline']}" for i in ideas[:25])
	return [
		{"role": "system", "content": (
			"You are QTT Studio, making one social media post for a small business. Choose ONE design from the list and write "
			"its words. Use ONLY the facts in the business brief and the request: never invent prices, discounts, offers, dates, "
			"awards, numbers or claims. If the request needs a fact that isn't given (a price, a date), leave it out. "
			f"Write in {'Tamil' if language == 'ta' else 'English'}. Short words: kicker up to 6 words, headline up to 8 words "
			"(mark the one key word or two with *stars*), subline one sentence, cta up to 4 words, badge up to 3 words (only a "
			"price or a word the brief gives). items: up to 4 rows {title, text} only when listing things the brief names. "
			'Reply with JSON only: {"template": "<key>", "look": "light|dark|brand", "words": {"kicker": "", "headline": "", '
			'"subline": "", "cta": "", "badge": "", "items": []}}.')},
		{"role": "user", "content": f"Business brief:\n{brief}\n\nDesigns:\n{lib}\n\nReady ideas you may adapt:\n{ready or '-'}\n\n"
									f"The request: {(request or '').strip()[:400]}"},
	]


def ask_prompt(*, instruction: str, design: dict, brief: str, language: str, looks: tuple = LOOKS, formats: tuple = FORMATS) -> list[dict]:
	"""An edit in plain words ("make the title shorter", "use a dark background") → JSON with only what changes."""
	return [
		{"role": "system", "content": (
			"You edit one social media post design for a small business. Apply the owner's instruction by changing only these: "
			"words (kicker, headline with *stars* on the key word, subline, cta, badge, items), look (light, dark or brand) and "
			"format (square, portrait, story). Never invent prices, offers, dates or claims beyond the brief and the current words. "
			f"Words in {'Tamil' if language == 'ta' else 'English'} unless the instruction asks for another language. "
			'Reply with JSON only, just the fields that change: {"words": {...}, "look": "...", "format": "..."}.')},
		{"role": "user", "content": f"Business brief:\n{brief}\n\nThe design now:\n{json.dumps(design, ensure_ascii=False)}\n\n"
									f"The instruction: {(instruction or '').strip()[:300]}"},
	]


def _json(text: str) -> dict:
	m = re.search(r"\{.*\}", text or "", re.S)
	try:
		d = json.loads(m.group(0)) if m else {}
	except ValueError:
		d = {}
	return d if isinstance(d, dict) else {}


def _icons() -> set:
	from qtt_platform.design.elements import ELEMENTS

	return {k for k in ELEMENTS if k.startswith("icon_") and k != "icon_tile"}


def clean_words(words) -> dict:
	"""Only known slots, trimmed to their size; items as up to 4 {icon, title, text}; nothing empty."""
	out = {}
	if not isinstance(words, dict):
		return out
	for slot, n in SLOTS.items():
		v = re.sub(r"\s+", " ", str(words.get(slot) or "")).strip()
		if v:
			out[slot] = v[:n]
	items = []
	for it in (words.get("items") or [])[:4] if isinstance(words.get("items"), list) else []:
		if isinstance(it, dict) and str(it.get("title") or "").strip():
			icon = it.get("icon") if isinstance(it.get("icon"), str) and it["icon"] in _icons() else "icon_check"
			items.append({"icon": icon, "title": str(it["title"]).strip()[:60], "text": str(it.get("text") or "").strip()[:100]})
	if items:
		out["items"] = items
	for slot, (n, size) in LIST_SLOTS.items():
		vals = [re.sub(r"\s+", " ", str(v)).strip()[:size] for v in (words.get(slot) or [])[:n]] if isinstance(words.get(slot), list) else []
		if any(vals):
			out[slot] = [v for v in vals if v]
	return out


def formats_for(post_types) -> tuple:
	"""The sizes a design can be drawn in: every design square, portrait and story; showcase designs also wide ones."""
	return FORMATS + WIDE if "showcase" in (post_types or []) else FORMATS


# ---- Poster variations (S10) ---------------------------------------------------------------------------------------
_NUMBER = re.compile(r"\d[\d,.]*\s*(?:\+|%|k|lakh|crore|million|x)?", re.I)


def ground_numbers(words: dict, source: str) -> dict:
	"""No number the owner didn't give: a line with a number that isn't in their own words loses it (the headline keeps
	its other words; other lines go) — "159+" stays only when they typed 159."""
	known = {re.sub(r"[^\d]", "", m.group(0)) for m in _NUMBER.finditer(source or "")}
	out = dict(words or {})
	for slot in ("kicker", "headline", "subline", "cta", "badge", "tagline"):
		v = out.get(slot)
		if not v:
			continue
		bad = [m.group(0) for m in _NUMBER.finditer(v) if re.sub(r"[^\d]", "", m.group(0)) not in known]
		if not bad:
			continue
		if slot != "headline":
			out.pop(slot)
			continue
		for b in bad:
			v = v.replace(b, "")
		out[slot] = re.sub(r"\s{2,}", " ", v).strip(" ,.-–")
	return {k: v for k, v in out.items() if v}


def showcase_prompt(*, brief: str, about: str, given: dict, count: int, language: str) -> list[dict]:
	"""The owner's product + what they wrote → `count` different sets of poster words (each a different angle)."""
	return [
		{"role": "system", "content": (
			f"You write the words for {count} different marketing posters of ONE product, shown with its real screenshot. Each set "
			"takes a different angle (the benefit, who it's for, how easy it is, an invitation…) — not the same line reworded. Use "
			"ONLY facts in the product description, the owner's points and the business brief: never invent numbers, prices, "
			"ratings, users, awards, testimonials or features. Use a number only if the owner wrote it. "
			f"Write in {'Tamil' if language == 'ta' else 'English'}. kicker up to 4 words, headline up to 7 words (mark one or two "
			"key words with *stars*), subline one short sentence, cta up to 3 words. "
			'Reply with JSON only: {"sets": [{"kicker": "", "headline": "", "subline": "", "cta": ""}]}.')},
		{"role": "user", "content": f"Product: {(about or '').strip()[:800]}\n\nThe owner's own words: {json.dumps(given, ensure_ascii=False)[:1500]}\n\n"
									f"Business brief:\n{brief[:2500]}"},
	]


def parse_showcase(text: str) -> list[dict]:
	"""The AI's sets → clean word sets with a headline (others dropped)."""
	sets = _json(text).get("sets")
	out = []
	for s in sets if isinstance(sets, list) else []:
		w = clean_words({k: s.get(k) for k in ("kicker", "headline", "subline", "cta")} if isinstance(s, dict) else {})
		if w.get("headline"):
			out.append(w)
	return out


def backdrop_prompt(what: str) -> str:
	"""An empty, calm background for a poster (the AI never draws a phone, a screen, words or a logo — those are the owner's)."""
	return ("An atmospheric background picture for a poster: " + ((what or "").strip()[:200] or "soft abstract light") + ". Calm, with soft "
			"empty space in the middle where a phone will be placed later; gentle depth of field. Empty: no phones, no screens, no "
			"devices, no people, no hands, no text, no letters, no numbers, no logos, no watermarks.")


def post_caption(words: dict) -> str:
	"""A first caption from the design's own words (no stars), to change in the Marketing assistant: the small line and
	the headline, the line below, the button's words. Nothing added that the design doesn't say."""
	w = {k: re.sub(r"\s+", " ", str((words or {}).get(k) or "").replace("*", "")).strip() for k in ("kicker", "headline", "subline", "cta")}
	head = " — ".join(x for x in (w["kicker"], w["headline"]) if x)
	items = [f"• {i['title']}" + (f": {i['text']}" if i.get("text") else "") for i in (words or {}).get("items") or [] if isinstance(i, dict) and i.get("title")]
	return "\n\n".join(x for x in (head, w["subline"], "\n".join(items), w["cta"]) if x)


def poster_prompt(*, image_url: str, brief: str, language: str, templates: list[dict]) -> list[dict]:
	"""Template intake: a poster the owner likes → the closest library design and words for THIS business. The poster's
	own words, names, prices, logos and pictures are never copied — only its kind of layout and mood are used."""
	lib = "\n".join(f"- {t['key']}: {t['label']} — for {', '.join(t['post_types'])}" for t in templates)
	return [
		{"role": "system", "content": (
			"You are QTT Studio. Look at the poster only to understand its STRUCTURE: what kind of post it is (offer, product, "
			"festival wish, hiring, event, tips…), where the headline, the small line, the button and any badge sit, how many "
			"listed items, and whether it is light, dark or in a strong brand colour. Then choose the ONE closest design from "
			"the list and write NEW words for the business in the brief. Never copy the poster's words, names, prices, phone "
			"numbers, logos or claims; never invent prices, discounts, dates or claims the brief doesn't give — leave them out. "
			f"Write in {'Tamil' if language == 'ta' else 'English'}. Short words: kicker up to 6 words, headline up to 8 (mark one "
			"key word with *stars*), subline one sentence, cta up to 4 words, badge up to 3 words (only a word the brief gives), "
			"items up to 4 {title, text} only for things the brief names. "
			'Reply with JSON only: {"saw": "one short line on what kind of poster it is", "template": "<key>", '
			'"look": "light|dark|brand", "words": {"kicker": "", "headline": "", "subline": "", "cta": "", "badge": "", "items": []}}.')},
		{"role": "user", "content": [
			{"type": "text", "text": f"Business brief:\n{brief}\n\nDesigns:\n{lib}"},
			{"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
		]},
	]


_CLAIMS = re.compile(r"\b(24\s*[/x×]\s*7|24\s*hours?|no\.?\s*1|number\s*one|#\s*1|best|cheapest|lowest|guaranteed?|100\s*%|award[- ]?winning|"
					 r"\d+\s*\+?\s*(years?|customers?|clients?|happy))\b", re.I)


def _words_of(text: str) -> set[str]:
	"""Real words (4+ letters), plural endings off — "Backups" matches "backup"."""
	return {re.sub(r"(es|s)$", "", w) for w in re.findall(r"[^\W\d_]{4,}", (text or "").lower(), re.U)}


def ground_words(words: dict, brief: str) -> dict:
	"""Keep only what the business itself said: list items whose name shares a real word with the brief, a badge whose
	words are in the brief, and no claim ("24/7", "No. 1", "best", "100 %", "10 years") the brief doesn't make — even
	when the AI wrote them (a poster's own points, made-up promises)."""
	known = _words_of(brief)
	b = (brief or "").lower()
	out = dict(words or {})
	items = [i for i in out.get("items") or [] if _words_of(i.get("title", "")) & known]
	if items:
		out["items"] = items
	else:
		out.pop("items", None)
	if out.get("badge") and not (_words_of(out["badge"]) and _words_of(out["badge"]) <= known):
		out.pop("badge")
	for slot in ("kicker", "headline", "subline", "cta", "tagline"):
		v = out.get(slot)
		if not v:
			continue
		made_up = [m.group(0) for m in _CLAIMS.finditer(v) if m.group(0).lower() not in b]  # claims the business didn't make
		if not made_up:
			continue
		if slot != "headline":
			out.pop(slot)  # the whole line goes — taking a word out leaves a broken sentence
			continue
		for claim in made_up:
			v = v.replace(claim, "")
		out[slot] = re.sub(r"\s{2,}", " ", v).strip(" ,.-–")
	return {k: v for k, v in out.items() if v}


def parse_poster(text: str, keys: set[str]) -> dict | None:
	"""The vision answer → {saw, template, look, words}; None when it chose no known design or wrote no headline."""
	d = _json(text)
	made = parse_make(json.dumps({"template": d.get("template"), "look": d.get("look"), "words": d.get("words")}), keys)
	if not made:
		return None
	return {**made, "saw": re.sub(r"\s+", " ", str(d.get("saw") or "")).strip()[:160]}


def short_prompt(*, about: str, brief: str, language: str, scenes: int) -> list[dict]:
	"""A Short's words: a hook, one caption a photo, an end line — from the business brief only."""
	return [
		{"role": "system", "content": (
			"You write the words for a 10-second vertical video (Reel / Short) of a small business, shown over its own photos. "
			"Use ONLY the facts in the business brief and the request: never invent prices, discounts, offers, dates, numbers "
			f"or claims. Write in {'Tamil' if language == 'ta' else 'English'}. A hook up to 6 words that stops the scroll "
			f"(mark one key word with *stars*); exactly {scenes} short captions, one a photo, up to 8 words each; an end line "
			'up to 6 words that says what to do (call, visit, order on WhatsApp). Reply with JSON only: '
			'{"hook": "", "captions": ["", ...], "end_line": ""}.')},
		{"role": "user", "content": f"Business brief:\n{brief}\n\nThe Short is about: {(about or '').strip()[:300]}"},
	]


def parse_json(text: str) -> dict:
	"""The first JSON object in an AI answer ({} when there's none)."""
	return _json(text)


def parse_make(text: str, keys: set[str]) -> dict | None:
	"""The AI's answer → {template, look, words}; None when it chose no known design or wrote no headline."""
	d = _json(text)
	words = clean_words(d.get("words"))
	if d.get("template") not in keys or not words.get("headline"):
		return None
	return {"template": d["template"], "look": d.get("look") if d.get("look") in LOOKS else None, "words": words}


def parse_ask(text: str) -> dict:
	"""The AI's edit → only valid changes ({} when nothing usable)."""
	d = _json(text)
	out = {}
	words = clean_words(d.get("words"))
	if words:
		out["words"] = words
	if d.get("look") in LOOKS:
		out["look"] = d["look"]
	if d.get("format") in FORMATS:
		out["format"] = d["format"]
	return out
