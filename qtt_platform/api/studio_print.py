"""
QTT Studio › Print (PROJ-0012 S4): visiting cards, flyers (A5, A4) and menus / price lists — in the business's logo,
colours and fonts, filled from its Business profile and Business knowledge (its own offerings and prices only), as a
print-ready PDF (3 mm bleed, crop marks) and a picture of each side for sharing.

  print_home     what can be printed (each product, its styles and sides), the print designs made
  start          a product's words filled from the business, and the fields to change
  previews       each style of a product drawn with these words (pictures only, nothing kept)
  make_print     the print-ready PDF and the pictures, kept in the Business Library (counts as a design)
  delete_print   a print design and its files

Who: as Studio (owner, admins, Studio members).
"""

import base64
import io
import json

import frappe
from frappe import _
from frappe.utils import get_url

from qtt_platform.api import knowledge, studio
from qtt_platform.design import base, print as pr, render

DESIGN = "QTT Design"
ITEM = "QTT Library Item"


def _brand(tenant: str) -> tuple[dict, dict, str]:
	k = knowledge.for_tenant(tenant) or {}
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	pal = base.palette(kit.get("colors") or {"primary": base.DEFAULT_PRIMARY})
	fonts = base.fonts(kit.get("font_heading") or "Poppins", kit.get("font_body") or "Inter", k.get("language") or "")
	name = frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or ""
	return pal, fonts, name


def _files(tenant: str, product: str) -> tuple[dict, str | None, str | None]:
	"""The pictures a print page uses — the business's logo and (a flyer) its own first photo, else one for its trade."""
	from qtt_platform.api import business_photos
	from qtt_platform.design import business_types, catalog, post

	files, logo, photo = {}, None, None
	lname, ldata = knowledge._logo(tenant)
	if ldata:
		files[lname], logo = ldata, lname
	if product.startswith("flyer"):
		own, _cut = business_photos.for_design(tenant, "gallery", 1)
		if not own:
			btype = (knowledge.for_tenant(tenant) or {}).get("business_type")
			own = post.kit_photos(business_types.photo_kit(btype) if btype else catalog.sample_kit("center_hero", "any"), 1)
		if own:
			files[own[0][0]], photo = own[0][1], own[0][0]
	return files, logo, photo


def _need_product(product: str, style: str | None = None) -> None:
	if product not in pr.PRODUCTS:
		frappe.throw(_("Choose what to print."))
	if style is not None and style not in pr.PRODUCTS[product][4]:
		frappe.throw(_("Choose a style."))


def _picture(tenant: str, product: str, style: str, words: dict, side: str, *, trim: bool = True) -> bytes:
	"""One side drawn by the renderer (the bleed cut off when `trim`)."""
	from PIL import Image

	pal, fonts, _name = _brand(tenant)
	files, logo, photo = _files(tenant, product)
	_lbl, tw, th, _sides, _st = pr.PRODUCTS[product]
	k = 96 / 25.4
	w, h = round((tw + 2 * pr.BLEED) * k), round((th + 2 * pr.BLEED) * k)
	png = render.png(pr.page(product, style, words, pal, fonts, logo=logo, photo=photo, only=side), w, h, files)
	if not trim:
		return png
	im = Image.open(io.BytesIO(png))
	b = round(pr.BLEED * k)
	buf = io.BytesIO()
	im.crop((b, b, w - b, h - b)).save(buf, "PNG", optimize=True)
	return buf.getvalue()


def _out(doc) -> dict:
	c = json.loads(doc.content or "{}")
	return {"name": doc.name, "title": doc.title, "product": c.get("product"), "style": c.get("style"),
			"picture": get_url(doc.output) if doc.output else None, "pictures": c.get("pictures") or [], "pdf": c.get("pdf"),
			"words": c.get("words") or {}}


def _saved(tenant: str) -> list[dict]:
	return [_out(frappe.get_doc(DESIGN, n)) for n in frappe.get_all(DESIGN, filters={"tenant": tenant, "kind": "print"}, pluck="name",
																	  order_by="creation desc", page_length=40)]


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def print_home() -> dict:
	"""What can be printed — each product with its size, styles and sides — and the print designs made."""
	tenant = studio._tenant()
	has = bool(studio._entitlements(tenant)) or frappe.get_attr("qtt_platform.house.is_house")(tenant)
	return {"has_studio": has,
			"products": [{"key": k, "label": label, "size": f"{w} × {h} mm", "sides": list(sides),
						  "styles": [{"key": s, "label": pr.STYLE_NAMES[s]} for s in styles]}
						 for k, (label, w, h, sides, styles) in pr.PRODUCTS.items()],
			"saved": _saved(tenant)}


@frappe.whitelist(methods=["GET"])
def start(product: str) -> dict:
	"""A product's words filled from the Business profile and knowledge (its own offerings and prices — nothing made
	up), and the fields to change. {words, fields: [{key, label, multiline}], items (a menu)}."""
	tenant = studio._tenant()
	_need_product(product)
	_pal, _fonts, name = _brand(tenant)
	person = frappe.db.get_value("User", frappe.session.user, "full_name") or ""
	k = dict(knowledge.for_tenant(tenant) or {})
	k["tagline"] = (frappe.db.get_value("QTT Business Profile", tenant, "tagline") if frappe.db.exists("QTT Business Profile", tenant) else "") or ""
	words = pr.fields_for(product, name=name, contacts=knowledge.contacts(tenant), knowledge=k, person=person)
	return {"words": words, "fields": [{"key": k, "label": label, "multiline": multi} for k, label, _n, multi in pr.FIELDS[pr.group_of(product)]],
			"menu": product == "menu"}


@frappe.whitelist(methods=["POST"])
def previews(product: str, words=None) -> dict:
	"""Each style of the product drawn with these words (its first side) — pictures only. {styles: [{key, label, picture}]}."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	_need_product(product)
	w = pr.clean(product, json.loads(words) if isinstance(words, str) else (words or {}))
	side = pr.PRODUCTS[product][3][0]
	out = []
	for s in pr.PRODUCTS[product][4]:
		png = _picture(tenant, product, s, w, side)
		out.append({"key": s, "label": pr.STYLE_NAMES[s], "picture": "data:image/png;base64," + base64.b64encode(png).decode()})
	return {"styles": out}


@frappe.whitelist(methods=["POST"])
def make_print(product: str, style: str, words=None) -> dict:
	"""The print-ready PDF (every side, 3 mm bleed, crop marks — for the print shop) and a picture of each side (to
	share), kept in the Business Library. Counts as one of the month's designs."""
	tenant = studio._tenant()
	ent = studio._need_studio(tenant)
	_need_product(product, style)
	studio._need_design_room(tenant, ent)
	w = pr.clean(product, json.loads(words) if isinstance(words, str) else (words or {}))
	pal, fonts, name = _brand(tenant)
	files, logo, photo = _files(tenant, product)
	pdf = render.pdf(pr.page(product, style, w, pal, fonts, logo=logo, photo=photo, marks=True), files=files)
	label = pr.PRODUCTS[product][0]
	doc = frappe.get_doc({"doctype": DESIGN, "tenant": tenant, "kind": "print", "title": f"{_(label)} · {w.get('name') or name}"[:120],
						  "made_by": "Template", "format": "square", "content": json.dumps({"product": product, "style": style, "words": w})})
	doc.insert(ignore_permissions=True)

	def keep(fname: str, data: bytes) -> str:
		return frappe.get_doc({"doctype": "File", "file_name": fname, "content": data, "is_private": 0, "attached_to_doctype": DESIGN,
							   "attached_to_name": doc.name}).insert(ignore_permissions=True).file_url

	kept = [keep(f"print-{product}-{side}-{doc.name}.png", _picture(tenant, product, style, w, side)) for side in pr.PRODUCTS[product][3]]
	pictures = [get_url(u) for u in kept]
	pdf_url = get_url(keep(f"print-{product}-{doc.name}-print-ready.pdf", pdf))
	first = kept[0] if kept else None
	item = frappe.get_doc({"doctype": ITEM, "tenant": tenant, "title": doc.title, "kind": "print", "design": doc.name, "file": first,
						   "format": product, "products": "all"}).insert(ignore_permissions=True)
	doc.db_set({"output": first, "library_item": item.name,
				"content": json.dumps({"product": product, "style": style, "words": w, "pictures": pictures, "pdf": pdf_url}, ensure_ascii=False)})
	doc.reload()
	return _out(doc)


@frappe.whitelist(methods=["POST"])
def delete_print(name: str) -> dict:
	"""Delete a print design, its PDF and pictures."""
	tenant = studio._tenant()
	doc = studio._mine(tenant, name)
	if doc.kind != "print":
		frappe.throw(_("That isn't a print design."))
	for item in frappe.get_all(ITEM, filters={"design": doc.name}, pluck="name"):
		frappe.delete_doc(ITEM, item, ignore_permissions=True, force=True)
	for f in frappe.get_all("File", filters={"attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(DESIGN, doc.name, ignore_permissions=True, force=True)
	return {"saved": _saved(tenant)}
