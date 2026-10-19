"""
QTT Studio › Poster variations (PROJ-0012 S10) — a product's real screenshots (an app, a website, a dashboard) and a few
words become several poster concepts, each a different creative direction (design/showcase.py, showcase_more.py), drawn in
the business's brand by QTT's own renderer. Any product, any business — nothing here knows one product.

The screenshot is the source of truth: it is placed as it is inside a device frame — never redrawn, recoloured or written
on. Words come from the owner (and, if they ask, an AI that may only reword what they gave — numbers, prices, ratings and
claims they didn't write are taken out). Each concept is an ordinary Studio design: Quick edit, Ask AI, Move and resize,
Every size (also 16:9 and 3:2), Post it.

  directions      the creative directions (and what each needs), sizes, curated colour sets
  upload_shot     a screenshot (multipart `file`, PNG / JPG / WEBP up to 10 MB) kept for the business — its size, a
                  warning when it's small, and the colour sets that suit it best
  generate        the concepts: up to 8 designs at once (each counts as a design; AI words 1 credit for all)
  more_like       another concept like one: the same direction with the next colour set, or new AI words (1 credit)
  backdrop        an AI background behind a design (no phone, no words, no logo in it) — 10 AI credits, as Photo Lab

Who: as Studio (the owner, admins, members given QTT Studio).
"""

import io
import json
import uuid

import frappe
from frappe import _

from qtt_platform.api import post_templates as pt
from qtt_platform.api import studio
from qtt_platform.design import library, palettes, showcase
from qtt_platform.studio import rules

from qtt_platform.studio.showcase_rules import (BACKDROP, MAX_BYTES, MAX_CONCEPTS, MAX_SHOTS, SMALL, SUGGESTED, clean_brief, colour_sets,
											 pick_directions)


def _tenant() -> tuple[str, dict]:
	tenant = studio._tenant()
	return tenant, studio._need_studio(tenant)


def _templates() -> dict:
	"""direction → its library template (the first one on; QTT Admin can switch any off)."""
	out = {}
	for n in frappe.get_all(library.DT, filters={"enabled": 1}, pluck="name", order_by="sort asc"):
		r = library.row_dict(frappe.get_doc(library.DT, n))
		if "showcase" in r["post_types"] and r["layout"] not in out:
			out[r["layout"]] = r
	return out


def _has_brand(tenant: str) -> bool:
	from qtt_platform.api import knowledge

	return bool((knowledge.brand_kit(tenant).get("colors") or {}).get("primary"))


@frappe.whitelist(methods=["GET"])
def directions() -> dict:
	"""The creative directions on now (each: key, label, what it is, what it needs), the sizes, the curated colour sets and
	whether the business has its own brand colours."""
	tenant, _ent = _tenant()
	on = _templates()
	return {
		"directions": [{"key": k, "label": label, "what": what, "needs": need} for k, (label, what, need) in showcase.DIRECTIONS.items() if k in on],
		"suggested": [k for k in SUGGESTED if k in on],
		"formats": list(rules.FORMATS + rules.WIDE), "max": MAX_CONCEPTS, "max_shots": MAX_SHOTS,
		"palettes": [{"key": k, "label": label, "mood": mood, "colors": c} for k, (label, mood, c) in palettes.CURATED.items()],
		"has_brand": _has_brand(tenant), "credits": studio._credits(tenant), "backdrop": list(BACKDROP),
	}


@frappe.whitelist(methods=["POST"])
def upload_shot() -> dict:
	"""Multipart `file`: a screenshot (PNG, JPG or WEBP, up to 10 MB), kept as it is — private, for this business's
	designs. {url, width, height, small, palettes: best colour sets for it first}."""
	from PIL import Image

	tenant, _ent = _tenant()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a screenshot."))
	data = upload.stream.read(MAX_BYTES + 1)
	if len(data) > MAX_BYTES:
		frappe.throw(_("A screenshot must be 10 MB or smaller."))
	try:
		im = Image.open(io.BytesIO(data))
		im.verify()
		im = Image.open(io.BytesIO(data))
		fmt = (im.format or "").upper()
	except Exception:
		frappe.throw(_("That isn't a picture — choose a PNG, JPG or WEBP screenshot."))
	if fmt not in ("PNG", "JPEG", "WEBP"):
		frappe.throw(_("Choose a PNG, JPG or WEBP screenshot."))
	w, h = im.size
	if w < 200 or h < 300:
		frappe.throw(_("That picture is too small to show — take the screenshot again at full size."))
	ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt]
	f = frappe.get_doc({"doctype": "File", "file_name": f"screenshot-{frappe.generate_hash(length=10)}{ext}", "content": data, "is_private": 1,
						"attached_to_doctype": "QTT Tenant", "attached_to_name": tenant}).insert(ignore_permissions=True)
	return {"url": f.file_url, "width": w, "height": h, "small": h < SMALL and w < SMALL,
			"palettes": palettes.rank(palettes.shot_colours(data))}


def _shot_ok(tenant: str, url: str) -> bool:
	return bool(frappe.db.exists("File", {"file_url": url, "attached_to_doctype": "QTT Tenant", "attached_to_name": tenant}))


@frappe.whitelist(methods=["POST"])
def generate(data=None) -> dict:
	"""Make poster concepts. data: {shots: [urls from upload_shot], about (what the product is), headline, kicker, subline,
	cta, items: [points], stat + stat_label, list: [chips], steps, problems, directions: [keys] (empty: Studio picks),
	count (1–8, default 4), format, colours: brand | auto | a colour set, ai: write the words with AI (1 credit)}.
	{batch, designs: [design + direction]}. Each concept counts as a design this month."""
	tenant, ent = _tenant()
	d = json.loads(data) if isinstance(data, str) else (data or {})
	shots = [u for u in (d.get("shots") or [])[:MAX_SHOTS] if isinstance(u, str)]
	if not shots:
		frappe.throw(_("Add a screenshot of your product first."))
	if not all(_shot_ok(tenant, u) for u in shots):
		frappe.throw(_("Upload your screenshots again."))
	count = max(1, min(MAX_CONCEPTS, int(d.get("count") or 4)))
	left = rules.limit_left(ent.get("studio_designs", 0), studio._designs_this_month(tenant))
	if left is not None:
		if left <= 0:
			frappe.throw(_("You've made this month's designs — more come on the 1st, or choose a bigger Studio plan."))
		count = min(count, left)
	words = clean_brief(d)
	about = str(d.get("about") or "").strip()[:800]
	if not words.get("headline") and not (d.get("ai") and about):
		frappe.throw(_("Write a headline — or say what the product is and let AI write the words."))
	on = _templates()
	keys = pick_directions(d.get("directions") or [], words, len(shots), on, count)
	if not keys:
		frappe.throw(_("None of those directions fit what you gave — add points, a number or steps, or choose others."))
	brief, lang = studio._brief(tenant)
	sets = [words] * len(keys)
	if d.get("ai"):
		given = {k: v for k, v in words.items() if k in ("headline", "kicker", "subline", "cta", "items", "stat", "stat_label")}
		source = json.dumps(d, ensure_ascii=False) + "\n" + brief
		got = rules.parse_showcase(studio._ai(tenant, "make", rules.showcase_prompt(brief=brief, about=about, given=given, count=len(keys), language=lang),
											  max_tokens=1200))
		if got:
			# only what the owner and the business said — no claims or numbers they didn't write
			got = [rules.ground_numbers(rules.ground_words(g, source), source) for g in got]
			sets = [{**words, **{k: v for k, v in got[i % len(got)].items() if v}} for i in range(len(keys))]
	if not all(s.get("headline") for s in sets):
		frappe.throw(_("Write a headline for your posters."))
	fmt = d.get("format") if d.get("format") in rules.FORMATS + rules.WIDE else "portrait"
	first = pt._file_bytes(shots[0])
	ranked = palettes.rank(palettes.shot_colours(first)) if first else list(palettes.CURATED)
	colours = colour_sets(str(d.get("colours") or ""), _has_brand(tenant), ranked, len(keys))
	batch = uuid.uuid4().hex[:12]
	out = []
	for key, w, colour in zip(keys, sets, colours):
		out.append(_make(tenant, on[key], w, lang, fmt, {"shots": shots, "palette": colour, "batch": batch}, made_by="AI" if d.get("ai") else "Template",
						 request=f"Poster variations: {about or w.get('headline', '')}"[:500]))
	return {"batch": batch, "designs": out}


def _make(tenant: str, t: dict, words: dict, lang: str, fmt: str, media: dict, *, made_by: str, request: str) -> dict:
	doc = frappe.get_doc({"doctype": studio.DESIGN, "tenant": tenant, "kind": "post", "template": t["key"], "format": fmt, "look": t["look"],
						  "made_by": made_by, "request": request, "title": studio._title(words),
						  "content": json.dumps({"words": words, "lang": lang, "media": media}, ensure_ascii=False)})
	doc.insert(ignore_permissions=True)
	studio._draw(tenant, doc)
	return {**studio._out(doc), "direction": t["layout"], "direction_label": showcase.DIRECTIONS[t["layout"]][0]}


@frappe.whitelist(methods=["POST"])
def more_like(name: str, ai: int = 0) -> dict:
	"""Another concept like this one: the same direction and words in the next colour set — or, with ai, new words for it
	(1 credit; only the owner's facts). Counts as a design."""
	tenant, ent = _tenant()
	studio._need_design_room(tenant, ent)
	doc = studio._mine(tenant, name)
	c = json.loads(doc.content or "{}")
	media = dict(c.get("media") or {})
	if not media.get("shots"):
		frappe.throw(_("This design isn't a poster variation."))
	t = pt.template_row(doc.template)
	words = c.get("words") or {}
	if str(ai).lower() in ("1", "true"):
		brief, lang = studio._brief(tenant)
		source = json.dumps(words, ensure_ascii=False) + "\n" + brief + "\n" + (doc.request or "")
		got = rules.parse_showcase(studio._ai(tenant, "make", rules.showcase_prompt(brief=brief, about=doc.request or "", given=words, count=1,
																					   language=c.get("lang") or lang), max_tokens=500))
		if not got:
			frappe.throw(_("Studio couldn't write new words just now — no credits were used. Try again."))
		words = {**words, **rules.ground_numbers(rules.ground_words(got[0], source), source)}
	else:
		order = list(palettes.CURATED)
		now = media.get("palette")
		media["palette"] = order[(order.index(now) + 1) % len(order)] if now in order else order[0]
	return _make(tenant, t, words, c.get("lang") or "en", doc.format, media, made_by=doc.made_by, request=doc.request or "")


@frappe.whitelist(methods=["POST"])
def backdrop(name: str, what: str = "") -> dict:
	"""An AI background behind this design (what it should show, e.g. "an open Bible in warm morning light") — the AI makes
	only the empty scene, never the phone, words or logo. 10 AI credits (none if it fails)."""
	from qtt_platform.studio import images

	tenant, _ent = _tenant()
	doc = studio._mine(tenant, name)
	c = json.loads(doc.content or "{}")
	if not (c.get("media") or {}).get("shots"):
		frappe.throw(_("This design isn't a poster variation."))
	if pt.template_row(doc.template)["layout"] not in BACKDROP:
		frappe.throw(_("This direction has no background picture — choose In context, Floating chips or Open book."))
	setup = images.need_ready()
	size = "1024x1536" if doc.format in ("story", "portrait") else ("1536x1024" if doc.format in rules.WIDE else "1024x1024")
	picture = studio.paid(tenant, "ai_background", lambda: images.scene(rules.backdrop_prompt(what), size, setup),
						  provider=setup[0], model=setup[1], provider_cost=images.COST.get(size, 0.06))
	f = frappe.get_doc({"doctype": "File", "file_name": f"backdrop-{frappe.generate_hash(length=10)}.png", "content": picture, "is_private": 1,
						"attached_to_doctype": "QTT Tenant", "attached_to_name": tenant}).insert(ignore_permissions=True)
	c["media"] = {**c["media"], "backdrop": f.file_url}
	doc.content = json.dumps(c, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	studio._draw(tenant, doc)
	return studio._out(doc)
