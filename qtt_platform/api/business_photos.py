"""
A business's own photos for its posts (PROJ-0011) — Business › Knowledge › Photos for your posts. Owner and admins.

  photos             the list (newest first): photo, its cut-out (if made), what it shows, label
  upload_photo       multipart `file` (+ `kind`): JPG, PNG or WEBP up to 10 MB; at most 60 a business
  remove_background  make the cut-out on QTT's own server (rembg) — 20 a day a business
  update_photo       what it shows, its label, use the cut-out in designs or not
  delete_photo       the photo and its cut-out

Designs (post templates, the post studio) use these before any sample photo: people for the "person" layouts, products
for the product layouts, the place for the rest; a cut-out sits on the design without a frame.
"""

import frappe
from frappe import _

from qtt_platform.api import knowledge
from qtt_platform.tenant.guards import require_tenant_role

DT = "QTT Business Photo"
KINDS = ("Product", "Person", "Place", "Other")
MAX_BYTES = 10 * 1024 * 1024
MAX_PHOTOS = 60
CUTOUTS_PER_DAY = 20
TYPES = (".jpg", ".jpeg", ".png", ".webp")


def _tenant() -> str:
	tenant = knowledge._tenant()
	require_tenant_role(tenant, knowledge.GOVERNANCE)
	return tenant


def _out(tenant: str) -> list[dict]:
	return frappe.get_all(DT, filters={"tenant": tenant}, fields=["name", "kind", "label", "image", "cutout", "use_cutout"],
						  order_by="creation desc")


def _mine(tenant: str, name: str):
	if not frappe.db.exists(DT, {"name": name, "tenant": tenant}):
		frappe.throw(_("That photo isn't here any more."), frappe.DoesNotExistError)
	return frappe.get_doc(DT, name)


def _file(tenant: str, name: str, fname: str, content: bytes, field: str) -> str:
	return frappe.get_doc({"doctype": "File", "file_name": fname, "content": content, "is_private": 0, "attached_to_doctype": DT,
						   "attached_to_name": name, "attached_to_field": field}).insert(ignore_permissions=True).file_url


@frappe.whitelist(methods=["GET"])
def photos() -> list[dict]:
	"""The business's photos for posts, newest first."""
	return _out(_tenant())


@frappe.whitelist(methods=["POST"])
def upload_photo(kind: str = "Product") -> list[dict]:
	"""Multipart (field `file`): a JPG, PNG or WEBP photo up to 10 MB, and what it shows (Product, Person, Place, Other)."""
	tenant = _tenant()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a photo."))
	if frappe.db.count(DT, {"tenant": tenant}) >= MAX_PHOTOS:
		frappe.throw(_("You have {0} photos — delete some you don't use first.").format(MAX_PHOTOS))
	content = upload.stream.read(MAX_BYTES + 1)
	fname = (upload.filename or "photo.jpg").strip()
	if len(content) > MAX_BYTES:
		frappe.throw(_("A photo must be 10 MB or smaller."))
	if not fname.lower().endswith(TYPES):
		frappe.throw(_("A photo must be a JPG, PNG or WEBP image."))
	doc = frappe.get_doc({"doctype": DT, "tenant": tenant, "kind": kind if kind in KINDS else "Product", "image": "/files/placeholder"})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	doc.db_set("image", _file(tenant, doc.name, f"post-photo-{frappe.generate_hash(length=10)}{fname[fname.rfind('.'):].lower()}", content, "image"))
	return _out(tenant)


@frappe.whitelist(methods=["POST"])
def remove_background(name: str) -> list[dict]:
	"""Make the photo's cut-out (its background removed) on QTT's server, and use it in designs."""
	from frappe.utils import today

	from qtt_platform.design import cutout

	tenant = _tenant()
	doc = _mine(tenant, name)
	key = f"qtt_cutouts:{tenant}:{today()}"
	n = int(frappe.cache.get_value(key) or 0) + 1
	if n > CUTOUTS_PER_DAY:
		frappe.throw(_("That's enough for today — try again tomorrow."))
	frappe.cache.set_value(key, n, expires_in_sec=2 * 86400)
	src = frappe.get_doc("File", {"file_url": doc.image, "attached_to_doctype": DT, "attached_to_name": doc.name})
	png = cutout.remove_background(src.get_content(), "person" if doc.kind == "Person" else "general")
	old = doc.cutout
	doc.db_set({"cutout": _file(tenant, doc.name, f"post-cutout-{frappe.generate_hash(length=10)}.png", png, "cutout"), "use_cutout": 1})
	if old:
		for f in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": DT, "attached_to_name": doc.name}, pluck="name"):
			frappe.delete_doc("File", f, ignore_permissions=True)
	return _out(tenant)


@frappe.whitelist(methods=["POST"])
def update_photo(name: str, kind: str | None = None, label: str | None = None, use_cutout=None) -> list[dict]:
	"""Change what a photo shows (Product, Person, Place, Other), its label, or whether designs use its cut-out."""
	tenant = _tenant()
	doc = _mine(tenant, name)
	values = {}
	if kind in KINDS:
		values["kind"] = kind
	if label is not None:
		values["label"] = str(label).strip()[:80]
	if use_cutout is not None:
		values["use_cutout"] = 1 if str(use_cutout).lower() in ("1", "true") and doc.cutout else 0
	if values:
		doc.db_set(values)
	return _out(tenant)


@frappe.whitelist(methods=["POST"])
def delete_photo(name: str) -> list[dict]:
	"""Delete a photo and its cut-out; returns the photos left."""
	tenant = _tenant()
	doc = _mine(tenant, name)
	for f in frappe.get_all("File", filters={"attached_to_doctype": DT, "attached_to_name": doc.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(DT, doc.name, ignore_permissions=True)
	return _out(tenant)


# ---- for designs -------------------------------------------------------------------------------------------------------
PERSON_LAYOUTS = {"numbered_services", "curve_photo", "wave_agency", "event", "tribute", "circles_labels", "question_rows"}
PRODUCT_LAYOUTS = {"center_hero", "product_promo", "sale", "gallery"}
CUTOUT_LAYOUTS = {"center_hero", "product_promo", "numbered_services", "curve_photo", "wave_agency"}


def for_design(tenant: str, layout: str, count: int = 5) -> tuple[list[tuple[str, bytes]], bool]:
	"""([(file name, bytes)…], first is a cut-out) — the business's own photos, the right kind first; [] when it has none."""
	rows = frappe.get_all(DT, filters={"tenant": tenant}, fields=["name", "kind", "image", "cutout", "use_cutout"], order_by="creation desc")
	if not rows:
		return [], False
	want = "Person" if layout in PERSON_LAYOUTS else ("Product" if layout in PRODUCT_LAYOUTS else "Place")
	rows.sort(key=lambda r: (r.kind != want, r.kind == "Other"))
	out, first_cut = [], False
	for k, r in enumerate(rows[:count]):
		use_cut = bool(k == 0 and r.cutout and r.use_cutout and layout in CUTOUT_LAYOUTS)
		url = r.cutout if use_cut else r.image
		try:
			data = frappe.get_doc("File", {"file_url": url, "attached_to_doctype": DT, "attached_to_name": r.name}).get_content()
		except Exception:
			continue
		ext = url[url.rfind("."):].lower() if "." in url else ".jpg"
		out.append((f"own{k}{ext}", data))
		first_cut = first_cut or use_cut
	return out, first_cut
