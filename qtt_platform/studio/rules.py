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
CREDITS = {"make": 1, "ask": 1, "short_script": 2, "read_image": 3, "ai_background": 10, "ai_logo": 20}

# What can be made, and from which phase (S0: posts, S1: Photo Lab; the rest arrive phase by phase).
CATEGORIES = (
	("posts", "Social posts", "post", True),
	("documents", "Business documents", "document", False),
	("logos", "Logo and brand", "logo", False),
	("print", "Flyers and brochures", "print", False),
	("photos", "Photo Lab", "photo", True),  # S1
	("shorts", "Shorts and video", "video", False),
	("pages", "Landing pages", "page", False),
)
KINDS = ("post", "document", "logo", "print", "photo", "video", "page")
FORMATS = ("square", "portrait", "story")
LOOKS = ("light", "dark", "brand")
SLOTS = {"kicker": 60, "headline": 90, "subline": 220, "cta": 40, "badge": 30, "tagline": 80, "quote": 160}


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
			items.append({"icon": "icon_check", "title": str(it["title"]).strip()[:60], "text": str(it.get("text") or "").strip()[:100]})
	if items:
		out["items"] = items
	return out


def post_caption(words: dict) -> str:
	"""A first caption from the design's own words (no stars), to change in the Marketing assistant: the small line and
	the headline, the line below, the button's words. Nothing added that the design doesn't say."""
	w = {k: re.sub(r"\s+", " ", str((words or {}).get(k) or "").replace("*", "")).strip() for k in ("kicker", "headline", "subline", "cta")}
	head = " — ".join(x for x in (w["kicker"], w["headline"]) if x)
	items = [f"• {i['title']}" + (f": {i['text']}" if i.get("text") else "") for i in (words or {}).get("items") or [] if isinstance(i, dict) and i.get("title")]
	return "\n\n".join(x for x in (head, w["subline"], "\n".join(items), w["cta"]) if x)


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
