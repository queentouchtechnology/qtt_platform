"""
QTT Studio › Photo Lab (PROJ-0012 S1). Works on the business's own photos (the same ones as Business › Knowledge ›
Photos for your posts); every result is a new picture in the Business Library (kind "photo") that every product can use,
and can be added to Photos for your posts. The photo itself is never changed — except a finer cut-out, which replaces
its cut-out so post designs get it too.

  lab             the photos, what was made (newest first), the sizes, backdrops and scenes, what's left this month
  upload          add a photo (JPG, PNG or WEBP up to 10 MB)
  enhance         light, colour and sharpness put right
  crop            cut to a size (square, portrait, story, link, store product, website banner, profile) around the subject
  studio_shot     the cut-out on a clean backdrop in the brand's colours, on a soft shadow (makes the cut-out if needed)
  fine_cutout     a finer cut-out (hair, fur, see-through edges) for the photo
  ai_background   the cut-out on an AI-made scene (marble table, café, festive…) — the AI makes only the empty scene,
                  the product is the business's own photo (10 AI credits)
  save_to_posts   add a result to Photos for your posts
  delete_item     delete a result

Each result counts towards the plan's photos a month (studio_photos). Who: as Studio (owner, admins, Studio members).
"""

import frappe
from frappe import _
from frappe.utils import get_first_day, get_url, today

from qtt_platform.api import business_photos as bp
from qtt_platform.api import knowledge, studio
from qtt_platform.design import photo_lab as lab
from qtt_platform.studio import images, rules

ITEM = "QTT Library Item"
OPS = {"enhance": "Enhanced", "crop": "Cropped", "studio": "Studio shot", "ai": "AI background", "cutout": "Cut-out"}


# ---- helpers -----------------------------------------------------------------------------------------------------------
def _tenant() -> tuple[str, dict]:
	tenant = studio._tenant()
	return tenant, studio._need_studio(tenant)


def _made_this_month(tenant: str) -> int:
	return frappe.db.count(ITEM, {"tenant": tenant, "kind": "photo", "creation": [">=", get_first_day(today())]})


def _need_room(tenant: str, ent: dict) -> None:
	if rules.limit_left(ent.get("studio_photos", 0), _made_this_month(tenant)) == 0:
		frappe.throw(_("You've made this month's photos — more come on the 1st, or choose a bigger Studio plan."))


def _photo(tenant: str, name: str):
	return bp._mine(tenant, name)


def _bytes(doc, field: str) -> bytes:
	url = doc.get(field)
	try:
		return frappe.get_doc("File", {"file_url": url, "attached_to_doctype": bp.DT, "attached_to_name": doc.name}).get_content()
	except Exception:
		frappe.throw(_("That photo's file is missing — upload it again."))


def _cut(tenant: str, doc, *, fine: bool) -> bytes:
	"""The photo's cut-out — made now (and kept on the photo) when it has none, or when a finer one is asked for."""
	from qtt_platform.design import cutout

	if doc.cutout and not fine:
		return _bytes(doc, "cutout")
	png = cutout.remove_background(_bytes(doc, "image"), "person" if doc.kind == "Person" else "general", fine=fine)
	old = doc.cutout
	doc.db_set({"cutout": bp._file(tenant, doc.name, f"post-cutout-{frappe.generate_hash(length=10)}.png", png, "cutout"), "use_cutout": 1})
	if old:
		for f in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": bp.DT, "attached_to_name": doc.name}, pluck="name"):
			frappe.delete_doc("File", f, ignore_permissions=True)
	return png


def _palette(tenant: str) -> dict:
	from qtt_platform.design import base

	k = knowledge.for_tenant(tenant) or {}
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	return base.palette(kit.get("colors") or {"primary": base.DEFAULT_PRIMARY})


def _save(tenant: str, doc, op: str, size: str, data: bytes, ext: str = ".jpg") -> dict:
	"""A result → a Business Library picture (kind photo) for every product, with its own copy of the file."""
	what = (doc.label or doc.kind or "Photo").strip()
	item = frappe.get_doc({"doctype": ITEM, "tenant": tenant, "title": f"{_(OPS[op])} · {what}"[:140], "kind": "photo", "format": size,
						   "products": "all", "tags": f"{op} from:{doc.name} kind:{doc.kind or 'Other'}"})
	item.insert(ignore_permissions=True)
	url = frappe.get_doc({"doctype": "File", "file_name": f"studio-photo-{op}-{frappe.generate_hash(length=10)}{ext}", "content": data,
						  "is_private": 0, "attached_to_doctype": ITEM, "attached_to_name": item.name}).insert(ignore_permissions=True).file_url
	item.db_set("file", url)
	return _item(item.as_dict())


def _item(r) -> dict:
	return {"name": r["name"], "title": r["title"], "file": get_url(r["file"]) if r.get("file") else None, "size": r.get("format"),
			"op": (r.get("tags") or "").split(" ")[0], "modified": str(r.get("modified"))}


def _items(tenant: str, limit: int = 60) -> list[dict]:
	rows = frappe.get_all(ITEM, filters={"tenant": tenant, "kind": "photo"}, fields=["name", "title", "file", "format", "tags", "modified"],
						  order_by="creation desc", page_length=limit)
	return [_item(r) for r in rows]


def _photos(tenant: str) -> list[dict]:
	return [{**r, "image": get_url(r.image) if r.image else None, "cutout": get_url(r.cutout) if r.cutout else None} for r in bp._out(tenant)]


def _mine_item(tenant: str, name: str):
	if not frappe.db.exists(ITEM, {"name": name, "tenant": tenant, "kind": "photo"}):
		frappe.throw(_("That picture isn't here any more."), frappe.DoesNotExistError)
	return frappe.get_doc(ITEM, name)


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def lab_home() -> dict:
	"""Photo Lab: the business's photos, what was made (newest first), the sizes, backdrops and scenes, this month's photos
	left, AI credits, and whether AI backgrounds are switched on."""
	tenant = studio._tenant()
	ent = studio._entitlements(tenant)
	return {
		"has_studio": bool(ent),
		"photos": _photos(tenant),
		"made": _items(tenant),
		"left": rules.limit_left(ent.get("studio_photos", 0), _made_this_month(tenant)) if ent else 0,
		"credits": studio._credits(tenant) if ent else 0,
		"sizes": [{"key": k, "label": label, "width": w, "height": h} for k, (w, h, label) in lab.SIZES.items()],
		"backdrops": [{"key": k, "label": label} for k, label in lab.BACKDROPS.items()],
		"scenes": [{"key": k, "label": label} for k, (label, _x) in lab.SCENES.items()],
		"ai_backgrounds": images.ready() is not None,
		"ai_background_credits": rules.CREDITS["ai_background"],
	}


@frappe.whitelist(methods=["POST"])
def upload(kind: str = "Product") -> dict:
	"""Multipart (field `file`): a JPG, PNG or WEBP photo up to 10 MB, and what it shows (Product, Person, Place, Other) —
	kept with Photos for your posts."""
	tenant, _ent = _tenant()
	bp._upload(tenant, kind)
	return {"photos": _photos(tenant)}


@frappe.whitelist(methods=["POST"])
def enhance(photo: str) -> dict:
	"""Light, colour and sharpness put right — a new picture in the library."""
	tenant, ent = _tenant()
	_need_room(tenant, ent)
	doc = _photo(tenant, photo)
	return _save(tenant, doc, "enhance", "original", lab.enhance(_bytes(doc, "image")))


@frappe.whitelist(methods=["POST"])
def crop(photo: str, size: str = "square") -> dict:
	"""The photo cut to a size around its subject — a new picture; `small` says when the photo is too small for the size."""
	tenant, ent = _tenant()
	if size not in lab.SIZES:
		frappe.throw(_("Choose a size."))
	_need_room(tenant, ent)
	doc = _photo(tenant, photo)
	data = _bytes(doc, "image")
	return {**_save(tenant, doc, "crop", size, lab.smart_crop(data, size)), "small": lab.too_small(data, size)}


@frappe.whitelist(methods=["POST"])
def studio_shot(photo: str, size: str = "square", backdrop: str = "white") -> dict:
	"""The photo's cut-out on a clean backdrop (white, soft, brand, dark) in the brand's colours, standing on a soft
	shadow — a new picture. The cut-out is made first when the photo has none."""
	tenant, ent = _tenant()
	if size not in lab.SIZES or backdrop not in lab.BACKDROPS:
		frappe.throw(_("Choose a size and a backdrop."))
	_need_room(tenant, ent)
	doc = _photo(tenant, photo)
	return _save(tenant, doc, "studio", size, lab.studio_shot(_cut(tenant, doc, fine=not doc.cutout), size, backdrop, _palette(tenant)))


@frappe.whitelist(methods=["POST"])
def fine_cutout(photo: str) -> dict:
	"""A finer cut-out for the photo (hair, fur, see-through edges); it replaces the photo's cut-out, so post designs use
	it too. Counts as one of the month's photos."""
	tenant, ent = _tenant()
	_need_room(tenant, ent)
	doc = _photo(tenant, photo)
	_save(tenant, doc, "cutout", "cutout", _cut(tenant, doc, fine=True), ext=".png")
	return {"photos": _photos(tenant), "made": _items(tenant)}


@frappe.whitelist(methods=["POST"])
def ai_background(photo: str, size: str = "square", scene: str = "studio", custom: str = "") -> dict:
	"""The photo's cut-out on an AI-made scene (SCENES, or the owner's own words). The AI makes only the empty scene — never
	the product, text or a logo; the product is the business's own photo. 10 AI credits (none if it fails)."""
	tenant, ent = _tenant()
	if size not in lab.SIZES:
		frappe.throw(_("Choose a size."))
	setup = images.need_ready()
	_need_room(tenant, ent)
	doc = _photo(tenant, photo)
	cut = _cut(tenant, doc, fine=not doc.cutout)
	ai_size = lab.AI_SIZES[size]
	picture = studio.paid(tenant, "ai_background", lambda: images.scene(lab.scene_prompt(scene, custom), ai_size, setup),
						  provider=setup[0], model=setup[1], provider_cost=images.COST.get(ai_size, 0.06))
	return _save(tenant, doc, "ai", size, lab.on_scene(picture, cut, size))


@frappe.whitelist(methods=["POST"])
def save_to_posts(item: str) -> dict:
	"""Add a Photo Lab picture to Photos for your posts (what it shows is kept from its photo)."""
	tenant, _ent = _tenant()
	it = _mine_item(tenant, item)
	if frappe.db.count(bp.DT, {"tenant": tenant}) >= bp.MAX_PHOTOS:
		frappe.throw(_("You have {0} photos for posts — delete some you don't use first.").format(bp.MAX_PHOTOS))
	tags = dict(t.split(":", 1) for t in (it.tags or "").split() if ":" in t)
	try:
		data = frappe.get_doc("File", {"file_url": it.file, "attached_to_doctype": ITEM, "attached_to_name": it.name}).get_content()
	except Exception:
		frappe.throw(_("That picture's file is missing."))
	kind = tags.get("kind") if tags.get("kind") in bp.KINDS else "Product"
	doc = frappe.get_doc({"doctype": bp.DT, "tenant": tenant, "kind": kind, "label": (it.title or "")[:80], "image": "/files/placeholder"})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	ext = ".png" if (it.file or "").lower().endswith(".png") else ".jpg"
	doc.db_set("image", bp._file(tenant, doc.name, f"post-photo-{frappe.generate_hash(length=10)}{ext}", data, "image"))
	return {"photos": _photos(tenant)}


@frappe.whitelist(methods=["POST"])
def delete_item(item: str) -> dict:
	"""Delete a Photo Lab picture (a photo's own cut-out stays on the photo)."""
	tenant = studio._tenant()
	it = _mine_item(tenant, item)
	for f in frappe.get_all("File", filters={"attached_to_doctype": ITEM, "attached_to_name": it.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(ITEM, it.name, ignore_permissions=True, force=True)
	return {"made": _items(tenant)}
