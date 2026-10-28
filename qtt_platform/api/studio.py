"""
QTT Studio (PROJ-0012 S0) — a product of its own (QTT_STUDIO). Everything QTT already made stays free with the other
products; making something new needs Studio. What's made goes into the Business Library every product uses.

  home            what Studio shows: on or not (and the plan / trial), this month's designs and AI credits, what can be
                  made, the latest designs
  make            "What do you want to make?" — AI picks a design and writes its words from the business knowledge
                  (1 AI credit); the design is drawn in the business's brand and saved
  new_design      start from a library design (and, optionally, one of its ready ideas) — no AI
  designs, design one business's designs, newest first / one with its picture
  update_design   change the words, size, look or design — drawn again
  ask             an AI edit in plain words ("make the title shorter", "dark background") — 1 AI credit
  delete_design   the design and its library item
  library         the Business Library: what the business made, for any product (kind / product)
  another         Show me another one: the same request in another design (1 AI credit), or the same words in another
                  design of the same kind (no AI)
  editor_assets   what the editor offers: fonts (the brand's first), the business's photos and Library pictures, the logo
  editor_src / editor_cutout   a photo for the editor (and its background removed)
  design_pdf      the design as a PDF to print

Who: the owner and admins, and team members given QTT Studio (Studio Admin, Designer).
"""

import json
import uuid

import frappe
from frappe import _

from qtt_platform.api import knowledge, post_templates as pt
from qtt_platform.design import content as library_words
from qtt_platform.design import library
from qtt_platform.studio import rules

DESIGN = "QTT Design"
ITEM = "QTT Library Item"


# ---- who, and what they have -------------------------------------------------------------------------------------------
def _tenant() -> str:
	from qtt_platform.product.guards import has_product_access
	from qtt_platform.tenant.guards import require_tenant_membership

	tenant = knowledge._tenant()
	m = require_tenant_membership(tenant)
	if m.tenant_role not in knowledge.GOVERNANCE and not has_product_access(tenant, rules.PRODUCT):
		frappe.throw(_("Ask your business owner to give you QTT Studio."), frappe.PermissionError)
	return tenant


def _entitlements(tenant: str) -> dict:
	from qtt_platform.entitlement.engine import get_entitlements

	return get_entitlements(tenant, rules.PRODUCT)


def _need_studio(tenant: str) -> dict:
	ent = _entitlements(tenant)
	if not ent:
		frappe.throw(_("Making something new needs QTT Studio — start its free trial in Explore QTT OS."), frappe.PermissionError)
	return ent


def _designs_this_month(tenant: str) -> int:
	from frappe.utils import get_first_day, today

	return frappe.db.count(DESIGN, {"tenant": tenant, "creation": [">=", get_first_day(today())]})


def _need_design_room(tenant: str, ent: dict) -> None:
	left = rules.limit_left(ent.get("studio_designs", 0), _designs_this_month(tenant))
	if left == 0:
		frappe.throw(_("You've made this month's designs — more come on the 1st, or choose a bigger Studio plan."))


def _credits(tenant: str) -> float | None:
	from qtt_platform.ai.services.credit_service import get_balance
	from qtt_platform.house import is_house

	return None if is_house(tenant) else float(get_balance(tenant, rules.PRODUCT) or 0)


def paid(tenant: str, feature: str, run, *, provider: str = "assistant", model: str = "assistant", provider_cost: float = 0):
	"""Run one AI job paid with AI credits: reserved first, refunded if it gives nothing or fails (QTT's own business
	doesn't pay); the usage is recorded either way. `run()` returns the result, or something empty when it failed."""
	import time

	from qtt_platform.ai.core.response import AiUsage
	from qtt_platform.ai.services import credit_service, usage_service
	from qtt_platform.house import is_house

	cost = rules.CREDITS[feature]
	ref = f"studio:{feature}:{uuid.uuid4()}"
	paying = not is_house(tenant)
	if paying and not credit_service.deduct_credits(tenant, rules.PRODUCT, cost, reference=ref).get("ok"):
		frappe.throw(_("You're out of AI credits — more come with next month's plan, or buy more in Business › Plans and billing."))
	start = time.monotonic()
	result = None
	try:
		result = run()
	except Exception:
		frappe.log_error(title=f"QTT Studio: AI {feature} failed")
	status = "success" if result else "error"
	if status != "success" and paying:
		credit_service.refund_credits(tenant, rules.PRODUCT, cost, reference=ref)
	try:
		usage_service.record_usage(tenant=tenant, product=rules.PRODUCT, user=frappe.session.user, feature=f"studio_{feature}",
								   provider=provider, model=model, usage=AiUsage(0, 0, 0), credits_used=cost if status == "success" and paying else 0,
								   provider_cost=provider_cost if status == "success" else 0, status=status,
								   duration_ms=int((time.monotonic() - start) * 1000))
	except Exception:
		frappe.log_error(title="QTT Studio: usage not recorded")
	if status != "success":
		frappe.throw(_("Studio couldn't do that just now — no credits were used. Please try again in a minute."))
	return result


def _ai(tenant: str, feature: str, messages: list[dict], *, max_tokens: int = 900) -> str:
	"""One AI answer (words), paid with AI credits."""
	from qtt_platform.api.assistant import complete_json

	def run():
		for json_mode in (True, False):
			text = complete_json(messages, max_tokens=max_tokens, json_mode=json_mode, temperature=0.4, timeout=45)
			if (text or "").strip():
				return text
		return None

	return paid(tenant, feature, run)


# ---- designs -----------------------------------------------------------------------------------------------------------
def _out(doc) -> dict:
	from frappe.utils import get_url

	from qtt_platform.design import fitcheck

	c = json.loads(doc.content or "{}")
	showcase = bool(c.get("media"))
	layout = frappe.db.get_value(library.DT, doc.template, "layout")
	return {"name": doc.name, "title": doc.title, "kind": doc.kind, "template": doc.template, "format": doc.format, "look": doc.look,
			# words longer than this design holds at this size: told to the owner, never silently cut (design/fitcheck.py)
			"warnings": fitcheck.check(layout, c.get("words") or {}, doc.format) if layout else [],
			"made_by": doc.made_by, "request": doc.request or "", "words": c.get("words") or {}, "lang": c.get("lang") or "en",
			"picture": get_url(doc.output) if doc.output else None, "modified": str(doc.modified),
			"formats": list(rules.FORMATS + rules.WIDE if showcase else rules.FORMATS), "showcase": showcase,
			"palette": (c.get("media") or {}).get("palette"), "batch": (c.get("media") or {}).get("batch"),
			"shots": len((c.get("media") or {}).get("shots") or []), "fit": (c.get("media") or {}).get("fit") or [],
			"clear": bool((c.get("media") or {}).get("clear")),
			"direction": layout if showcase else None}


def _item_for(doc, fmt: str):
	"""The design's library picture for one size (each size drawn is its own picture in the library), or None."""
	name = frappe.db.get_value(ITEM, {"design": doc.name, "format": fmt}, "name")
	return frappe.get_doc(ITEM, name) if name else None


def _draw(tenant: str, doc) -> None:
	"""Draw the design in its current size, in the business's brand — only when something changed since that size was
	last drawn — and keep that size's picture in the library."""
	t = pt.template_row(doc.template)
	c = json.loads(doc.content or "{}")
	parts = pt.post_parts(tenant, t, look=doc.look, words=c.get("words") or None, lang=c.get("lang"), media=c.get("media"))
	pt.with_edits(tenant, parts, c.get("edits"))
	sig = pt.parts_sig(t, doc.format, parts)
	item = _item_for(doc, doc.format)
	if item and item.file and f"sig:{sig}" in (item.tags or "").split():
		if doc.output != item.file or doc.library_item != item.name:  # this size was drawn already, as it is now
			doc.output, doc.output_sig, doc.library_item = item.file, sig, item.name
			doc.save(ignore_permissions=True)
		return
	url = frappe.get_doc({"doctype": "File", "file_name": f"studio-{doc.name}-{sig}.png", "content": pt.draw(t, doc.format, parts),
						  "is_private": 0, "attached_to_doctype": DESIGN, "attached_to_name": doc.name}).insert(ignore_permissions=True).file_url
	old = item.file if item else None
	item = item or frappe.new_doc(ITEM)
	item.update({"tenant": tenant, "title": doc.title, "kind": doc.kind, "design": doc.name, "file": url, "format": doc.format,
				 "products": item.products or "all", "tags": f"sig:{sig}"})
	item.save(ignore_permissions=True) if not item.is_new() else item.insert(ignore_permissions=True)
	doc.output, doc.output_sig, doc.library_item = url, sig, item.name
	doc.save(ignore_permissions=True)
	if old and old != url:
		for f in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
			frappe.delete_doc("File", f, ignore_permissions=True)


def _formats(doc) -> tuple:
	"""The sizes this design can be drawn in (showcase designs also 16:9 and 3:2)."""
	return rules.formats_for(pt.template_row(doc.template)["post_types"])


def _mine(tenant: str, name: str):
	if not frappe.db.exists(DESIGN, {"name": name, "tenant": tenant}):
		frappe.throw(_("That design isn't here any more."), frappe.DoesNotExistError)
	return frappe.get_doc(DESIGN, name)


def _title(words: dict) -> str:
	return (" ".join(x for x in (words.get("kicker"), words.get("headline")) if x).replace("*", "") or "Design")[:120]


def _create(tenant: str, *, template: str, words: dict, lang: str, look: str | None, made_by: str, request: str = "") -> dict:
	t = pt.template_row(template)
	doc = frappe.get_doc({"doctype": DESIGN, "tenant": tenant, "kind": "post", "template": template, "format": "square",
						  "look": look if look in rules.LOOKS else t["look"], "made_by": made_by, "request": request[:500],
						  "title": _title(words), "content": json.dumps({"words": words, "lang": lang}, ensure_ascii=False)})
	doc.insert(ignore_permissions=True)
	_draw(tenant, doc)
	return _out(doc)


def _new_words(c: dict) -> None:
	"""The words were changed (Quick edit, Ask AI): words typed on the design itself give way to them; moves stay."""
	from qtt_platform.design import arrange

	c["edits"] = arrange.without_text(c.get("edits") or {})


def _brief(tenant: str) -> tuple[str, str]:
	k = knowledge.for_tenant(tenant)
	return knowledge.marketing_brief(tenant), library_words.language_of(k.get("language"))


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def home() -> dict:
	"""Studio's home: on or not (plan, trial end), this month's designs and AI credits left, what can be made, the latest
	designs, and where the free designs are for a business without Studio."""
	from qtt_platform.subscription.service import get_current_subscription
	from qtt_platform.house import is_house

	tenant = _tenant()
	ent = _entitlements(tenant)
	sub = get_current_subscription(tenant, rules.PRODUCT)
	used = _designs_this_month(tenant)
	recent = [_out(frappe.get_doc(DESIGN, n)) for n in frappe.get_all(DESIGN, filters={"tenant": tenant, "kind": "post"}, pluck="name", order_by="modified desc", limit=8)]
	return {
		"has_studio": bool(ent), "house": is_house(tenant),
		"plan": frappe.db.get_value("QTT Plan", sub.plan, "display_name") if sub and ent else None,
		"status": sub.status if sub and ent else None, "trial_end": str(sub.trial_end) if sub and ent and sub.trial_end else None,
		"designs": {"used": used, "left": rules.limit_left(ent.get("studio_designs", 0), used) if ent else 0},
		"credits": _credits(tenant) if ent else 0,
		"categories": [{"key": k, "label": label, "kind": kind, "ready": ready} for k, label, kind, ready in rules.CATEGORIES],
		"recent": recent, "library": frappe.db.count(ITEM, {"tenant": tenant}), "festival": _festival(tenant) if ent else None,
		"can_activate": frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": frappe.session.user, "status": "active"},
											"tenant_role") == "Tenant Owner",
	}


def _festival(tenant: str) -> dict | None:
	"""The next festival in 3 weeks with a wish ready for it: {key, label, date, idea, template} (a greeting design of this
	business's kind) — Make starts it without AI."""
	try:
		soon = library.upcoming(21, tenant)
	except Exception:
		return None
	rows, _templates = _library(tenant)
	greeting = next((r["key"] for r in rows if "greeting" in (r.get("post_types") or [])), None)
	for o in soon:
		if greeting and f"wish-{o.key}" in library_words.IDEAS:
			return {"key": o.key, "label": o.label, "date": str(o.date), "idea": f"wish-{o.key}", "template": greeting}
	return None


@frappe.whitelist(methods=["POST"])
def make(request: str, template: str | None = None) -> dict:
	"""What do you want to make? — AI picks a library design and writes its words from the business knowledge only (never
	invented prices, offers or dates), in the business's language; drawn in its brand and saved. 1 AI credit.
	template: write the words for this design (a template the owner chose)."""
	tenant = _tenant()
	ent = _need_studio(tenant)
	if len((request or "").strip()) < 3:
		frappe.throw(_("Say what you'd like to make."))
	return _make(tenant, ent, request.strip(), only=template)


def _make(tenant: str, ent: dict, request: str, *, only: str | None = None, exclude: str | None = None) -> dict:
	_need_design_room(tenant, ent)
	brief, lang = _brief(tenant)
	rows, templates = _library(tenant)
	if only:
		rows = [r for r in rows if r["key"] == only] or [{"key": only}]
		templates = [r for r in templates if r["key"] == only] or [{"key": only, "label": pt.template_row(only)["title"],
																	 "post_types": pt.template_row(only)["post_types"]}]
	elif exclude:
		rows = [r for r in rows if r["key"] != exclude] or rows
		templates = [r for r in templates if r["key"] != exclude] or templates
	f, _lang = pt._facts(tenant)
	ideas = [{"key": k, "headline": (w.get("kicker", "") + " " + w["headline"]).strip()} for k, i in library_words.IDEAS.items()
			 if (w := library_words.fill(i, f, lang)) and not i.get("occasion")]
	answer = rules.parse_make(_ai(tenant, "make", rules.make_prompt(request=request, brief=brief, language=lang, templates=templates, ideas=ideas)),
							  {r["key"] for r in rows})
	if not answer:
		frappe.throw(_("Studio couldn't match that to a design — try saying it another way (\"a Pongal wish\", \"a post about our meals\")."))
	words = rules.ground_words(answer["words"], brief + "\n" + request)  # what the business and the request said, nothing more
	words["headline"] = words.get("headline") or answer["words"]["headline"]
	return _create(tenant, template=answer["template"], words=words, lang=lang, look=answer["look"], made_by="AI", request=request)


def _library(tenant: str) -> tuple[list[dict], list[dict]]:
	"""The library designs for this business's kind (all when none fit), and how the AI sees them."""
	from qtt_platform.design import catalog

	rows = [library.row_dict(frappe.get_doc(library.DT, n)) for n in frappe.get_all(library.DT, filters={"enabled": 1}, pluck="name", order_by="sort asc")]
	group = pt._group_of(tenant)
	rows = [r for r in rows if catalog.matches(r, group=group or None)] or rows
	templates = [{"key": r["key"], "label": catalog.LAYOUTS.get(r["layout"], {}).get("label", r["title"]) + " · " + r["title"].split(" · ")[-1],
				  "post_types": r["post_types"]} for r in rows]
	return rows, templates


@frappe.whitelist(methods=["POST"])
def from_poster() -> dict:
	"""Template intake — multipart `file`: a poster you like (JPG, PNG or WEBP, up to 8 MB). AI reads only its kind of
	layout and mood, picks the closest library design and writes new words for your business from Business knowledge — the
	poster's words, logos and pictures are never copied (3 AI credits, none if it fails). The design is drawn in your brand
	and saved. {design, saw}."""
	import base64
	import io

	from PIL import Image

	from qtt_platform.studio import images

	tenant = _tenant()
	ent = _need_studio(tenant)
	_need_design_room(tenant, ent)
	setup = images.need_ready(images.VISION_TASK)
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a poster."))
	data = upload.stream.read(8 * 1024 * 1024 + 1)
	if len(data) > 8 * 1024 * 1024:
		frappe.throw(_("A poster must be 8 MB or smaller."))
	try:
		im = Image.open(io.BytesIO(data)).convert("RGB")
	except Exception:
		frappe.throw(_("That isn't a picture — choose a JPG, PNG or WEBP poster."))
	im.thumbnail((1024, 1024))  # the AI looks at it small; it isn't kept
	buf = io.BytesIO()
	im.save(buf, "JPEG", quality=85)
	url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
	brief, lang = _brief(tenant)
	rows, templates = _library(tenant)
	keys = {r["key"] for r in rows}
	answer = paid(tenant, "read_image", lambda: rules.parse_poster(images.vision_json(rules.poster_prompt(image_url=url, brief=brief, language=lang,
																									  templates=templates), setup) or "", keys),
				  provider=setup[0], model=setup[1], provider_cost=0.002)
	words = rules.ground_words(answer["words"], brief)  # only what the business said — never the poster's points or made-up claims
	if not words.get("headline"):
		words["headline"] = answer["words"].get("headline", "")
	design = _create(tenant, template=answer["template"], words=words, lang=lang, look=answer["look"], made_by="AI",
					 request=f"From a poster: {answer.get('saw') or ''}")
	return {"design": design, "saw": answer.get("saw") or ""}


@frappe.whitelist(methods=["POST"])
def new_design(template: str, idea: str | None = None) -> dict:
	"""Start a design from a library design — with one of its ready ideas' words (filled from the knowledge), or its sample
	words to change. No AI."""
	tenant = _tenant()
	ent = _need_studio(tenant)
	_need_design_room(tenant, ent)
	t = pt.template_row(template)
	f, lang = pt._facts(tenant)
	words = None
	if idea:
		words = library_words.fill(library_words.IDEAS.get(idea) or {"needs": ["?"]}, f, lang)
		if not words:
			frappe.throw(_("Add the details this idea needs in Business › Knowledge first."))
	if not words:
		from qtt_platform.design import catalog

		sample = catalog.sample_for(t["layout"], pt._group_of(tenant) or "any")
		words = {k: v for k, v in sample.items() if k in pt.WORD_SLOTS}
		lang = "en"
	return _create(tenant, template=template, words=words, lang=lang, look=None, made_by="Template")


@frappe.whitelist(methods=["GET"])
def designs(start: int = 0, limit: int = 30) -> dict:
	"""The business's designs, newest first."""
	tenant = _tenant()
	names = frappe.get_all(DESIGN, filters={"tenant": tenant, "kind": "post"}, pluck="name", order_by="modified desc", start=max(0, int(start or 0)),
						   page_length=min(60, max(1, int(limit or 30))))
	return {"designs": [_out(frappe.get_doc(DESIGN, n)) for n in names], "total": frappe.db.count(DESIGN, {"tenant": tenant, "kind": "post"})}


@frappe.whitelist(methods=["GET"])
def design(name: str) -> dict:
	"""One design with its picture."""
	return _out(_mine(_tenant(), name))


@frappe.whitelist(methods=["POST"])
def update_design(name: str, data=None) -> dict:
	"""Change a design — words, size (square, portrait, story), look (light, dark, brand), its library design or title; a
	poster variation also how its screenshots sit (fit: [top | middle | bottom | whole], clear: keep the screen clear) — and
	draw it again."""
	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	d = json.loads(data) if isinstance(data, str) else (data or {})
	c = json.loads(doc.content or "{}")
	if isinstance(d.get("words"), dict):
		keep = ("items",) + tuple(rules.LIST_SLOTS) + ("stat", "stat_label", "step_icons", "before_label", "after_label")  # what Quick edit doesn't show stays
		c["words"] = {**{k: v for k, v in (c.get("words") or {}).items() if k in keep}, **rules.clean_words(d["words"])}
		_new_words(c)
	if (c.get("media") or {}).get("shots") and ("fit" in d or "clear" in d):
		from qtt_platform.studio.showcase_rules import clean_media

		m = c["media"]
		c["media"] = {**m, **clean_media({"fit": d.get("fit", m.get("fit")), "clear": d.get("clear", m.get("clear"))}, len(m["shots"]))}
	if d.get("format") in _formats(doc):
		doc.format = d["format"]
	if d.get("look") in rules.LOOKS:
		doc.look = d["look"]
	if d.get("template"):
		pt.template_row(d["template"])
		doc.template = d["template"]
	if str(d.get("title") or "").strip():
		doc.title = str(d["title"]).strip()[:120]
	doc.content = json.dumps(c, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	_draw(tenant, doc)
	return _out(doc)


@frappe.whitelist(methods=["POST"])
def ask(name: str, instruction: str) -> dict:
	"""Ask AI to change a design in plain words ("make the title shorter", "use a dark background", "make it Tamil"). Only
	the words, look and size change; nothing is invented. 1 AI credit."""
	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	if len((instruction or "").strip()) < 2:
		frappe.throw(_("Say what to change."))
	brief, lang = _brief(tenant)
	c = json.loads(doc.content or "{}")
	change = rules.parse_ask(_ai(tenant, "ask", rules.ask_prompt(instruction=instruction, brief=brief, language=c.get("lang") or lang,
																	design={"words": c.get("words") or {}, "look": doc.look, "format": doc.format})))
	if not change:
		frappe.throw(_("Studio didn't find anything to change — try saying it another way."))
	if "words" in change:
		c["words"] = {**(c.get("words") or {}), **change["words"]}
		_new_words(c)
		if any("஀" <= ch <= "௿" for ch in json.dumps(change["words"], ensure_ascii=False)):
			c["lang"] = "ta"
	doc.look = change.get("look", doc.look)
	doc.format = change.get("format", doc.format)
	doc.title = _title(c.get("words") or {})
	doc.content = json.dumps(c, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	_draw(tenant, doc)
	return _out(doc)


@frappe.whitelist(methods=["GET"])
def editor(name: str, format: str | None = None) -> dict:
	"""Move and resize: the design's own page for the app's editor (one size — the design's, or `format`), with its
	pictures inside it and the moves already saved for that size."""
	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	fmt = format if format in _formats(doc) else doc.format
	t = pt.template_row(doc.template)
	c = json.loads(doc.content or "{}")
	parts = pt.post_parts(tenant, t, look=doc.look, words=c.get("words") or None, lang=c.get("lang"), media=c.get("media"))
	pt.with_edits(tenant, parts, c.get("edits"))
	from qtt_platform.design.post import SIZES

	return {"html": pt.editor_html(t, fmt, parts), "width": 1080, "height": SIZES.get(fmt, 1080), "format": fmt}


@frappe.whitelist(methods=["POST"])
def save_moves(name: str, format: str, edits=None) -> dict:
	"""Save Move and resize for one size: each piece moved, made bigger or smaller, turned, its words changed or hidden
	({piece: {t, tf, text, hide}}; {} puts the size back as the design was). Drawn again and kept in the library."""
	from qtt_platform.design import arrange

	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	if format not in _formats(doc):
		frappe.throw(_("Choose a size."))
	raw = json.loads(edits) if isinstance(edits, str) else (edits or {})
	one = arrange.clean_edits({format: raw}).get(format) or {}
	c = json.loads(doc.content or "{}")
	all_edits = c.get("edits") or {}
	if one:
		all_edits[format] = one
	else:
		all_edits.pop(format, None)
	c["edits"] = all_edits
	doc.format = format
	doc.content = json.dumps(c, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	_draw(tenant, doc)
	return _out(doc)


@frappe.whitelist(methods=["POST"])
def all_sizes(name: str) -> dict:
	"""Magic resize: the design drawn in every size — square (feed), portrait (Instagram) and story (Stories, WhatsApp
	Status) — each kept in the library, with any moves made for that size. {design, sizes: [{format, picture}]}."""
	from frappe.utils import get_url

	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	keep = doc.format
	sizes = []
	for fmt in _formats(doc):
		doc.format = fmt
		_draw(tenant, doc)
		sizes.append({"format": fmt, "picture": get_url(doc.output) if doc.output else None})
	doc.format = keep
	_draw(tenant, doc)  # back to the size it was on (already drawn)
	return {"design": _out(doc), "sizes": sizes}


@frappe.whitelist(methods=["POST"])
def to_post(name: str, format: str | None = None) -> dict:
	"""Post it: the design (in `format`, or its own size) becomes a Marketing assistant post waiting for the owner's OK —
	its picture attached, its words as the caption to change there; the owner picks the pages and the time and approves.
	Needs the Marketing assistant. {post}."""
	from frappe.utils import get_url

	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	if "qtt_services" not in frappe.get_installed_apps():
		frappe.throw(_("Posting needs the Marketing assistant — order it in QTT Business Suite › Explore."))
	if format in _formats(doc) and format != doc.format:
		doc.format = format
	_draw(tenant, doc)
	save = frappe.get_attr("qtt_services.api.marketing.save")  # the owner's own post (checks the service and the owner)
	c = json.loads(doc.content or "{}")
	post = save(caption=rules.post_caption(c.get("words") or {}), media=json.dumps([get_url(doc.output)]))
	return {"post": post}


@frappe.whitelist(methods=["POST"])
def delete_design(name: str) -> dict:
	"""Delete a design, its picture and its library item."""
	tenant = _tenant()
	doc = _mine(tenant, name)
	for item in frappe.get_all(ITEM, filters={"design": doc.name}, pluck="name"):  # every size's picture
		frappe.delete_doc(ITEM, item, ignore_permissions=True, force=True)
	for f in frappe.get_all("File", filters={"attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(DESIGN, doc.name, ignore_permissions=True, force=True)
	return {"deleted": True}


@frappe.whitelist(methods=["GET"])
def library_items(kind: str | None = None, product: str | None = None, start: int = 0, limit: int = 40) -> dict:
	"""The Business Library: what the business made in Studio, newest first — for one kind (post, document, logo…) and one
	product's use. Every member may look (each app shows the business's own items first, then QTT's defaults)."""
	from frappe.utils import get_url

	from qtt_platform.tenant.guards import require_tenant_membership

	tenant = knowledge._tenant()
	require_tenant_membership(tenant)
	filters = {"tenant": tenant}
	if kind in rules.KINDS:
		filters["kind"] = kind
	rows = frappe.get_all(ITEM, filters=filters, fields=["name", "title", "kind", "file", "format", "design", "products", "modified"],
						  order_by="modified desc", start=max(0, int(start or 0)), page_length=min(80, max(1, int(limit or 40))))
	if product:
		rows = [r for r in rows if "all" in (r.products or "all").split() or product in (r.products or "").split()]
	return {"items": [{**r, "file": get_url(r.file) if r.file else None, "modified": str(r.modified)} for r in rows]}


@frappe.whitelist(methods=["POST"])
def another(name: str) -> dict:
	"""Show me another one: a design asked for in words is asked again for a different design (1 AI credit); one started
	from a design gets the same words in another design of the same kind (no AI)."""
	tenant = _tenant()
	ent = _need_studio(tenant)
	doc = _mine(tenant, name)
	if doc.request:
		return _make(tenant, ent, doc.request, exclude=doc.template)
	_need_design_room(tenant, ent)
	t = pt.template_row(doc.template)
	rows, _templates = _library(tenant)
	kinds = set(t["post_types"]) - {"showcase"}
	others = [r["key"] for r in rows if r["key"] != doc.template and kinds & set(r.get("post_types") or [])]
	if not others:
		frappe.throw(_("There isn't another design of this kind yet — try Ask AI to change this one."))
	seen = frappe.cache.get_value(f"qtt_studio_another:{doc.name}") or []
	fresh = [k for k in others if k not in seen] or others
	pick = fresh[0]
	frappe.cache.set_value(f"qtt_studio_another:{doc.name}", (seen + [pick])[-30:], expires_in_sec=86400)
	c = json.loads(doc.content or "{}")
	return _create(tenant, template=pick, words=c.get("words") or {}, lang=c.get("lang") or "en", look=doc.look, made_by="Template")


@frappe.whitelist(methods=["GET"])
def editor_assets() -> dict:
	"""What the editor offers: {fonts (the brand's first), colors (the brand's), photos (Photos for your posts: ref, picture,
	has a cut-out), pictures (Business Library photos), logo}."""
	from frappe.utils import get_url

	from qtt_platform.api import business_photos as bp
	from qtt_platform.design import base

	tenant = _tenant()
	_need_studio(tenant)
	k = knowledge.for_tenant(tenant) or {}
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	brand = [f for f in (kit.get("font_heading"), kit.get("font_body")) if f]
	pal = base.palette(kit.get("colors") or {"primary": base.DEFAULT_PRIMARY})
	colors = list(dict.fromkeys(c for c in (pal.get("primary"), pal.get("accent"), pal.get("primary_deep"), pal.get("dark")) if c))
	photos = [{"ref": f"photo:{r['name']}", "picture": get_url(r["image"]) if r.get("image") else None, "label": r.get("label") or r.get("kind"),
			   "cutout": bool(r.get("cutout"))} for r in bp._out(tenant)]
	items = frappe.get_all(ITEM, filters={"tenant": tenant, "kind": "photo"}, fields=["name", "title", "file"], order_by="creation desc", page_length=40)
	logo = knowledge._logo(tenant)
	return {"fonts": list(dict.fromkeys(brand + list(base.FONTS))), "brand_fonts": brand, "colors": colors,
			"photos": [p for p in photos if p["picture"]],
			"pictures": [{"ref": f"item:{r.name}", "picture": get_url(r.file), "label": r.title} for r in items if r.file],
			"logo": bool(logo and logo[1])}


@frappe.whitelist(methods=["GET"])
def editor_src(ref: str) -> dict:
	"""A photo for the editor to show now ({ref, url}: the picture inside the answer, brought down to 1200 px)."""
	from qtt_platform.design import arrange

	tenant = _tenant()
	_need_studio(tenant)
	data, ext = pt.source_bytes(tenant, ref)
	if not data:
		frappe.throw(_("That photo isn't here any more."))
	return {"ref": ref, "url": arrange.data_uri(f"x.{ext}", data)}


@frappe.whitelist(methods=["POST"])
def editor_cutout(ref: str) -> dict:
	"""The photo with its background removed, for the editor ({ref, url}). A photo for your posts keeps its cut-out (post
	designs use it too); a Library picture's cut-out is a new Library picture (one of the month's photos)."""
	from qtt_platform.api import studio_photos as sp
	from qtt_platform.design import arrange, cutout

	tenant = _tenant()
	ent = _need_studio(tenant)
	kind, _sep, name = str(ref).partition(":")
	if kind in ("photo", "cut"):
		doc = sp._photo(tenant, name)
		sp._cut(tenant, doc, fine=False)
		new = f"cut:{name}"
	elif kind == "item":
		sp._need_room(tenant, ent)
		data, _ext = pt.source_bytes(tenant, ref)
		if not data:
			frappe.throw(_("That photo isn't here any more."))
		png = cutout.remove_background(data, "general", fine=False)
		item = frappe.get_doc({"doctype": ITEM, "tenant": tenant, "title": _("Cut-out"), "kind": "photo", "format": "cutout", "products": "all",
							   "tags": f"cutout from:{name}"}).insert(ignore_permissions=True)
		url = frappe.get_doc({"doctype": "File", "file_name": f"studio-photo-cutout-{frappe.generate_hash(length=10)}.png", "content": png,
							  "is_private": 0, "attached_to_doctype": ITEM, "attached_to_name": item.name}).insert(ignore_permissions=True).file_url
		item.db_set("file", url)
		new = f"item:{item.name}"
	else:
		frappe.throw(_("Pick one of your photos first."))
	data, ext = pt.source_bytes(tenant, new)
	return {"ref": new, "url": arrange.data_uri(f"x.{ext}", data)}


@frappe.whitelist(methods=["POST"])
def design_pdf(name: str) -> dict:
	"""The design in its size as a PDF to print (a shop prints it as a poster) → {url}."""
	from frappe.utils import get_url

	tenant = _tenant()
	_need_studio(tenant)
	doc = _mine(tenant, name)
	t = pt.template_row(doc.template)
	c = json.loads(doc.content or "{}")
	parts = pt.post_parts(tenant, t, look=doc.look, words=c.get("words") or None, lang=c.get("lang"), media=c.get("media"))
	pt.with_edits(tenant, parts, c.get("edits"))
	sig = pt.parts_sig(t, doc.format, parts)
	fname = f"studio-{doc.name}-{sig}.pdf"
	have = frappe.db.get_value("File", {"file_name": fname, "attached_to_doctype": DESIGN, "attached_to_name": doc.name}, "file_url")
	if not have:
		have = frappe.get_doc({"doctype": "File", "file_name": fname, "content": pt.draw_pdf(t, doc.format, parts), "is_private": 0,
							   "attached_to_doctype": DESIGN, "attached_to_name": doc.name}).insert(ignore_permissions=True).file_url
	return {"url": get_url(have)}


@frappe.whitelist(methods=["POST"])
def duplicate(name: str) -> dict:
	"""Make a copy: the same design, words, look, size and changes, as a new design (counts as one of the month's)."""
	tenant = _tenant()
	ent = _need_studio(tenant)
	_need_design_room(tenant, ent)
	doc = _mine(tenant, name)
	new = frappe.copy_doc(doc)
	new.update({"output": None, "output_sig": None, "library_item": None, "title": (doc.title or "Design")[:110] + " · " + _("copy")})
	new.insert(ignore_permissions=True)
	_draw(tenant, new)
	return _out(new)
