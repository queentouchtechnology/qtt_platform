"""
QTT Studio › Shorts (PROJ-0012 S6): 9:16 videos (Reels, YouTube Shorts, WhatsApp Status) from the business's own photos —
a hook, a caption on each photo (slow zoom), and a brand end card — made in the background on QTT's server.

  shorts_home    the business's photos to pick from, the Shorts made (and any still being made), this month's left
  write_script   AI writes the hook, captions and end line from a few words and the Business knowledge (2 AI credits)
  make_short     start making a Short (photos + words) — it's ready in about a minute; counts towards the month's Shorts
  short          one Short (its state while it's being made)
  delete_short   a Short and its files
  short_to_post  the Short becomes a Marketing assistant post waiting for the owner's OK

Who: as Studio (owner, admins, Studio members); Post it the owner.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_first_day, get_url, today

from qtt_platform.api import business_photos as bp
from qtt_platform.api import knowledge, studio
from qtt_platform.design import base, render, shorts
from qtt_platform.studio import rules

DESIGN = "QTT Design"
ITEM = "QTT Library Item"


def _made_this_month(tenant: str) -> int:
	"""Shorts made (or being made) this month — one that failed isn't counted."""
	return frappe.db.count(DESIGN, {"tenant": tenant, "kind": "video", "creation": [">=", get_first_day(today())],
									"content": ["not like", '%"state": "failed"%']})


def _out(doc) -> dict:
	c = json.loads(doc.content or "{}")
	return {"name": doc.name, "title": doc.title, "state": c.get("state") or "making", "error": c.get("error"),
			"video": c.get("video"), "picture": get_url(doc.output) if doc.output else None, "script": c.get("script") or {},
			"seconds": c.get("seconds"), "modified": str(doc.modified)}


def _saved(tenant: str) -> list[dict]:
	return [_out(frappe.get_doc(DESIGN, n)) for n in frappe.get_all(DESIGN, filters={"tenant": tenant, "kind": "video"}, pluck="name",
																	  order_by="creation desc", page_length=30)]


def _brand(tenant: str) -> tuple[dict, dict, str]:
	k = knowledge.for_tenant(tenant) or {}
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	pal = base.palette(kit.get("colors") or {"primary": base.DEFAULT_PRIMARY})
	fonts = base.fonts(kit.get("font_heading") or "Poppins", kit.get("font_body") or "Inter", k.get("language") or "")
	return pal, fonts, frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or ""


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def shorts_home() -> dict:
	"""The business's photos to pick from (Photos for your posts), the Shorts made, this month's left, AI script cost."""
	tenant = studio._tenant()
	ent = studio._entitlements(tenant)
	has = bool(ent) or frappe.get_attr("qtt_platform.house.is_house")(tenant)
	photos = [{"name": r.name, "kind": r.kind, "label": r.label, "image": get_url(r.image) if r.image else None} for r in bp._out(tenant)]
	return {"has_studio": has, "photos": photos, "saved": _saved(tenant),
			"left": rules.limit_left(ent.get("studio_shorts", 0), _made_this_month(tenant)) if ent else (None if has else 0),
			"script_credits": rules.CREDITS["short_script"], "max_scenes": shorts.MAX_SCENES}


@frappe.whitelist(methods=["POST"])
def write_script(about: str, scenes: int = 3) -> dict:
	"""AI writes the Short's words from a few words ("our new breakfast menu") and the Business knowledge: a hook, one
	caption a photo, an end line — never inventing prices, offers or dates. 2 AI credits. {hook, captions, end_line}."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	if len((about or "").strip()) < 3:
		frappe.throw(_("Say what the Short is about."))
	n = max(1, min(int(scenes or 3), shorts.MAX_SCENES))
	brief, lang = studio._brief(tenant)
	answer = shorts.clean_script(rules.parse_json(studio._ai(tenant, "short_script", rules.short_prompt(about=about, brief=brief, language=lang, scenes=n))))
	if not answer["hook"] or not answer["captions"]:
		frappe.throw(_("Studio couldn't write that just now — no credits were used. Try saying it another way."))
	answer["captions"] = (answer["captions"] + [""] * n)[:n]
	return answer


@frappe.whitelist(methods=["POST"])
def make_short(photos=None, script=None) -> dict:
	"""Start making a Short from up to 4 of the business's photos (Photos for your posts, in order) and its words (hook,
	a caption a photo, end line). Made in the background — about a minute; counts towards the month's Shorts."""
	tenant = studio._tenant()
	ent = studio._need_studio(tenant)
	if rules.limit_left(ent.get("studio_shorts", 0), _made_this_month(tenant)) == 0 and ent:
		frappe.throw(_("You've made this month's Shorts — more come on the 1st, or choose a bigger Studio plan."))
	names = [str(n) for n in (json.loads(photos) if isinstance(photos, str) else (photos or []))][: shorts.MAX_SCENES]
	names = [n for n in names if frappe.db.exists(bp.DT, {"name": n, "tenant": tenant})]
	if not names:
		frappe.throw(_("Pick at least one photo."))
	s = shorts.clean_script(json.loads(script) if isinstance(script, str) else (script or {}))
	s["captions"] = (s["captions"] + [""] * len(names))[: len(names)]
	doc = frappe.get_doc({"doctype": DESIGN, "tenant": tenant, "kind": "video", "made_by": "Template", "format": "story",
						  "title": (s["hook"] or _("Short")).replace("*", "")[:120],
						  "content": json.dumps({"state": "making", "photos": names, "script": s}, ensure_ascii=False)})
	doc.insert(ignore_permissions=True)
	frappe.enqueue("qtt_platform.api.studio_video.build_short", queue="long", timeout=900, design=doc.name, enqueue_after_commit=True)
	return _out(doc)


def build_short(design: str) -> None:
	"""Background: draw the words and the end card on the renderer, put the video together with FFmpeg, keep it."""
	import imageio_ffmpeg

	doc = frappe.get_doc(DESIGN, design)
	c = json.loads(doc.content or "{}")
	tenant = doc.tenant
	try:
		pal, fonts, name = _brand(tenant)
		s = c.get("script") or {}
		photos = []
		for n in c.get("photos") or []:
			r = frappe.db.get_value(bp.DT, {"name": n, "tenant": tenant}, ["name", "image"], as_dict=True)
			if r:
				photos.append(frappe.get_doc("File", {"file_url": r.image, "attached_to_doctype": bp.DT, "attached_to_name": r.name}).get_content())
		if not photos:
			raise ValueError("no photos")
		overs = [render.png(shorts.overlay_page(cap, pal, fonts, hook=s.get("hook") if i == 0 else ""), shorts.W, shorts.H, transparent=True)
				 for i, cap in enumerate((s.get("captions") or [""] * len(photos))[: len(photos)])]
		lname, ldata = knowledge._logo(tenant)
		contacts = knowledge.contacts(tenant)
		end = render.png(shorts.end_page(name, s.get("end_line") or "", contacts.get("phone") or contacts.get("whatsapp") or "",
										 contacts.get("website") or "", pal, fonts, logo=lname if ldata else None), shorts.W, shorts.H,
						 {lname: ldata} if ldata else None)
		mp4 = shorts.build(photos, overs, end, imageio_ffmpeg.get_ffmpeg_exe())

		def keep(fname, data):
			return frappe.get_doc({"doctype": "File", "file_name": fname, "content": data, "is_private": 0, "attached_to_doctype": DESIGN,
								   "attached_to_name": doc.name}).insert(ignore_permissions=True).file_url

		from PIL import Image
		import io

		thumb = io.BytesIO()
		first = Image.open(io.BytesIO(photos[0])).convert("RGB")
		cover = Image.alpha_composite(shorts._cover(first, Image).resize((shorts.W, shorts.H)).convert("RGBA"),
									  Image.open(io.BytesIO(overs[0])).convert("RGBA").resize((shorts.W, shorts.H)))
		cover.convert("RGB").resize((540, 960)).save(thumb, "JPEG", quality=85)
		video_url = keep(f"short-{doc.name}.mp4", mp4)
		thumb_url = keep(f"short-{doc.name}.jpg", thumb.getvalue())
		item = frappe.get_doc({"doctype": ITEM, "tenant": tenant, "title": doc.title, "kind": "video", "design": doc.name, "file": video_url,
							   "format": "story", "products": "all"}).insert(ignore_permissions=True)
		c.update({"state": "ready", "video": get_url(video_url), "seconds": shorts.timing(len(photos))[0], "error": None})
		doc.db_set({"output": thumb_url, "library_item": item.name, "content": json.dumps(c, ensure_ascii=False)})
	except Exception:
		frappe.log_error(title="QTT Studio: Short failed")
		c.update({"state": "failed", "error": "Couldn't make this Short — please try again."})
		doc.db_set("content", json.dumps(c, ensure_ascii=False))
	frappe.db.commit()


@frappe.whitelist(methods=["GET"])
def short(name: str) -> dict:
	"""One Short — while it's being made, state is "making"; then "ready" (video, picture) or "failed"."""
	tenant = studio._tenant()
	doc = studio._mine(tenant, name)
	if doc.kind != "video":
		frappe.throw(_("That isn't a Short."))
	return _out(doc)


@frappe.whitelist(methods=["POST"])
def delete_short(name: str) -> dict:
	"""Delete a Short, its video and picture."""
	tenant = studio._tenant()
	doc = studio._mine(tenant, name)
	if doc.kind != "video":
		frappe.throw(_("That isn't a Short."))
	for item in frappe.get_all(ITEM, filters={"design": doc.name}, pluck="name"):
		frappe.delete_doc(ITEM, item, ignore_permissions=True, force=True)
	for f in frappe.get_all("File", filters={"attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(DESIGN, doc.name, ignore_permissions=True, force=True)
	return {"saved": _saved(tenant)}


@frappe.whitelist(methods=["POST"])
def short_to_post(name: str) -> dict:
	"""Post it: the Short becomes a Marketing assistant post waiting for the owner's OK (its video attached, its words as
	the caption). Needs the Marketing assistant. {post}."""
	tenant = studio._tenant()
	doc = studio._mine(tenant, name)
	c = json.loads(doc.content or "{}")
	if doc.kind != "video" or c.get("state") != "ready" or not c.get("video"):
		frappe.throw(_("This Short isn't ready yet."))
	if "qtt_services" not in frappe.get_installed_apps():
		frappe.throw(_("Posting needs the Marketing assistant — order it in Managed Services › Explore."))
	s = c.get("script") or {}
	caption = "\n\n".join(x for x in ((s.get("hook") or "").replace("*", ""), "\n".join(x.replace("*", "") for x in s.get("captions") or [] if x),
									   s.get("end_line") or "") if x)
	save = frappe.get_attr("qtt_services.api.marketing.save")
	return {"post": save(caption=caption, media=json.dumps([c["video"]]))}
