"""
QTT Studio › Logo and brand (PROJ-0012 S5). Logos drawn from the business's name, an icon and its brand fonts and
colours; AI logo symbols (Recraft) set beside the name in a real font; each saved logo with its export pack; one made the
business's logo for everything (brand kit, posts, every PDF).

  logo_home    the logo in use, the icons to choose from, whether AI logos are on, the logos saved
  ideas        a dozen logo ideas (monogram, wordmark, icon and name, emblem, stacked) — pictures only, nothing kept
  ai_ideas     AI draws two logo symbols from a few words (20 AI credits; refunded if it fails) — each shown three ways
  save_logo    keep one: its SVG, PNG (clear background), PDF, square icon and favicons, in one pack (a zip) in the
               Business Library
  use_logo     make a saved logo the business's logo (owner and admins) — the brand kit, posts and PDFs use it
  delete_logo  a saved logo and its files

Who: as Studio (owner, admins, Studio members); making it the business's logo only the owner and admins.
"""

import base64
import hashlib
import io
import json
import re
import zipfile

import frappe
from frappe import _
from frappe.utils import get_url

from qtt_platform.api import knowledge, studio
from qtt_platform.design import base, elements, logo, render
from qtt_platform.studio import images, rules

DESIGN = "QTT Design"
ITEM = "QTT Library Item"
MARKS = "qtt_logo_mark"  # cache: AI marks made for a business, until it saves one (7 days)


def _brand(tenant: str) -> tuple[dict, dict, str, str]:
	"""(palette, fonts, name, tagline) of the business."""
	k = knowledge.for_tenant(tenant) or {}
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	pal = base.palette(kit.get("colors") or {"primary": base.DEFAULT_PRIMARY})
	fonts = base.fonts(kit.get("font_heading") or "Poppins", kit.get("font_body") or "Inter", "")
	t = frappe.db.get_value("QTT Tenant", tenant, ["tenant_name", "legal_name"], as_dict=True) or {}
	tag = frappe.db.get_value("QTT Business Profile", tenant, "tagline") if frappe.db.exists("QTT Business Profile", tenant) else ""
	return pal, fonts, (t.get("tenant_name") or t.get("legal_name") or "").strip(), (tag or "").strip()


def _tiles(specs: list[dict], pal: dict, fonts: dict, marks: dict | None = None) -> list[str]:
	"""Every idea drawn on one sheet by the renderer, then cut into one picture each (data: PNGs, nothing kept)."""
	from PIL import Image

	page, w, h = logo.sheet(specs, pal, fonts, marks)
	sheet = Image.open(io.BytesIO(render.png(page, w, h)))
	tw, th = logo.TILE
	out = []
	for i in range(len(specs)):
		x, y = (i % 3) * tw, (i // 3) * th
		buf = io.BytesIO()
		sheet.crop((x, y, x + tw, y + th)).save(buf, "PNG", optimize=True)
		out.append("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())
	return out


def _marks(tenant: str) -> dict:
	return frappe.cache.get_value(f"{MARKS}:{tenant}") or {}


def _item(doc) -> dict:
	c = json.loads(doc.content or "{}")
	return {"name": doc.name, "title": doc.title, "picture": get_url(doc.output) if doc.output else None, "pack": c.get("pack"),
			"svg": c.get("svg_url"), "pdf": c.get("pdf_url"), "kind": (c.get("spec") or {}).get("kind")}


def _saved(tenant: str) -> list[dict]:
	return [_item(frappe.get_doc(DESIGN, n)) for n in frappe.get_all(DESIGN, filters={"tenant": tenant, "kind": "logo"}, pluck="name",
																	  order_by="creation desc", page_length=30)]


def _governs(tenant: str) -> bool:
	return frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": frappe.session.user, "status": "active"},
							   "tenant_role") in knowledge.GOVERNANCE


def _file(name: str, data: bytes, doc: str) -> str:
	return frappe.get_doc({"doctype": "File", "file_name": name, "content": data, "is_private": 0, "attached_to_doctype": DESIGN,
						   "attached_to_name": doc}).insert(ignore_permissions=True).file_url


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def logo_home() -> dict:
	"""The logo in use, the business's name and tagline, the icons, whether AI logos are on (and their cost), the logos
	saved."""
	tenant = studio._tenant()
	ent = studio._entitlements(tenant)
	_pal, _fonts, name, tag = _brand(tenant)
	current = frappe.db.get_value("QTT Tenant", tenant, "logo")
	return {
		"has_studio": bool(ent) or frappe.get_attr("qtt_platform.house.is_house")(tenant), "can_use": _governs(tenant),
		"current": get_url(current) if current and not str(current).startswith("http") else current,
		"name": name, "tagline": tag,
		"icons": [{"key": k, "label": elements.ELEMENTS[k][0]} for k in elements.ICONS],
		"ai_ready": images.ready(images.LOGO_TASK) is not None, "ai_credits": rules.CREDITS["ai_logo"],
		"credits": studio._credits(tenant) if ent else 0,
		"saved": _saved(tenant),
	}


@frappe.whitelist(methods=["POST"])
def ideas(name: str | None = None, tagline: str | None = None, icon: str | None = None) -> dict:
	"""A dozen logo ideas from the business's name (or `name`), its tagline, an icon (elements.ICONS), its colours and
	fonts. {ideas: [{spec, picture}]} — the pictures aren't kept; save_logo keeps the one picked."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	pal, fonts, own, tag = _brand(tenant)
	name = re.sub(r"\s+", " ", (name or own or "")).strip()[:40]
	if not name:
		frappe.throw(_("Type your business name."))
	specs = logo.ideas(name, tagline if tagline is not None else tag, icon, pal)
	return {"ideas": [{"spec": s, "picture": p} for s, p in zip(specs, _tiles(specs, pal, fonts))]}


@frappe.whitelist(methods=["POST"])
def ai_ideas(about: str, name: str | None = None, tagline: str | None = None) -> dict:
	"""AI draws two logo symbols from a few words ("a friendly tooth", "a coffee cup with steam") in the brand's colours
	— the symbol only, the name is set beside it in the brand's font. Each shown three ways. 20 AI credits."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	if len((about or "").strip()) < 3:
		frappe.throw(_("Say what the symbol should show."))
	setup = images.need_ready(images.LOGO_TASK)
	pal, fonts, own, tag = _brand(tenant)
	name = re.sub(r"\s+", " ", (name or own or "")).strip()[:40]
	k = knowledge.for_tenant(tenant) or {}
	prompt = logo.mark_prompt(about, k.get("business_type") or "")
	raw = studio.paid(tenant, "ai_logo", lambda: [m for m in (logo.safe_mark(x) for x in images.logo_marks(prompt, [pal["primary"], pal["dark"]], setup)) if m],
					  provider=setup[0], model=setup[1], provider_cost=images.LOGO_COST * 2)
	marks = _marks(tenant)
	specs = []
	for svg_text in raw:
		mid = hashlib.sha1(svg_text.encode()).hexdigest()[:16]
		marks[mid] = svg_text
		for kind in ("side", "emblem", "stacked"):
			specs.append(logo.clean_spec({"kind": kind, "tone": "primary", "name": name, "tagline": tagline if tagline is not None else tag,
										  "mark": mid}, name=name))
	frappe.cache.set_value(f"{MARKS}:{tenant}", dict(list(marks.items())[-12:]), expires_in_sec=7 * 86400)
	return {"ideas": [{"spec": s, "picture": p} for s, p in zip(specs, _tiles(specs, pal, fonts, marks))]}


@frappe.whitelist(methods=["POST"])
def save_logo(spec=None) -> dict:
	"""Keep a logo idea: its SVG, a PNG with a clear background, a PDF, a square icon and favicons — all in one pack (a
	zip) — in the Business Library. Counts as one of the month's designs."""
	from PIL import Image

	tenant = studio._tenant()
	ent = studio._need_studio(tenant)
	studio._need_design_room(tenant, ent)
	pal, fonts, own, tag = _brand(tenant)
	s = logo.clean_spec(json.loads(spec) if isinstance(spec, str) else (spec or {}), name=own, tagline=tag)
	if not s:
		frappe.throw(_("Pick a logo first."))
	mark = _marks(tenant).get(s["mark"]) if s.get("mark") else None
	if s.get("mark") and not mark:
		frappe.throw(_("That AI symbol has expired — make the AI ideas again."))
	w, h = logo.SIZE[s["kind"]]
	svg_text = logo.svg(s, pal, fonts, mark)
	png = render.png(logo.page_for(logo.svg(s, pal, fonts, mark, scale=2), w * 2, h * 2), w * 2, h * 2, transparent=True)  # sharp: twice the size
	pdf = render.pdf(logo.page_for(svg_text, w, h, "#ffffff"), w / 96, h / 96)
	# the square icon (app icon, profile picture, favicon): the logo itself when it's square, else its monogram
	sq = s if w == h else {**s, "kind": "monogram", "shape": "rounded"}
	sq_svg = logo.svg(sq, pal, fonts, mark if sq is s else None)
	sw, sh = logo.SIZE[sq["kind"]]
	icon = Image.open(io.BytesIO(render.png(logo.page_for(sq_svg, sw, sh), sw, sh, transparent=True))).convert("RGBA").resize((512, 512), Image.LANCZOS)

	def png_bytes(im, size):
		buf = io.BytesIO()
		im.resize((size, size), Image.LANCZOS).save(buf, "PNG", optimize=True)
		return buf.getvalue()

	doc = frappe.get_doc({"doctype": DESIGN, "tenant": tenant, "kind": "logo", "title": f"{_('Logo')} · {s['name']}"[:120], "made_by": "AI" if mark else "Template",
						  "format": "square", "content": json.dumps({"spec": s}, ensure_ascii=False)})
	doc.insert(ignore_permissions=True)
	slug = re.sub(r"[^a-z0-9]+", "-", s["name"].lower()).strip("-")[:30] or "logo"
	files = {f"{slug}-logo.svg": svg_text.encode(), f"{slug}-logo.png": png, f"{slug}-logo.pdf": pdf, f"{slug}-icon-512.png": png_bytes(icon, 512),
			 f"{slug}-icon-192.png": png_bytes(icon, 192), f"{slug}-favicon-32.png": png_bytes(icon, 32)}
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		for n, data in files.items():
			z.writestr(n, data)
		z.writestr("README.txt", "Your logo from QTT Studio.\n\n- logo.svg: for any size (print shops, signs)\n- logo.png: clear background, "
								 "for documents and social media\n- logo.pdf: for printers\n- icon-512 / icon-192: square, for profile pictures and apps\n"
								 "- favicon-32: for your website's tab\n")
	png_url = _file(f"{slug}-logo-{doc.name}.png", png, doc.name)
	c = {"spec": s, "mark": mark, "svg_url": get_url(_file(f"{slug}-logo-{doc.name}.svg", svg_text.encode(), doc.name)),
		 "pdf_url": get_url(_file(f"{slug}-logo-{doc.name}.pdf", pdf, doc.name)), "pack": get_url(_file(f"{slug}-logo-pack-{doc.name}.zip", buf.getvalue(), doc.name)),
		 "icon": _file(f"{slug}-icon-{doc.name}.png", png_bytes(icon, 512), doc.name)}
	item = frappe.get_doc({"doctype": ITEM, "tenant": tenant, "title": doc.title, "kind": "logo", "design": doc.name, "file": png_url, "format": s["kind"],
						   "products": "all"}).insert(ignore_permissions=True)
	doc.db_set({"output": png_url, "library_item": item.name, "content": json.dumps(c, ensure_ascii=False)})
	doc.reload()
	return _item(doc)


@frappe.whitelist(methods=["POST"])
def use_logo(name: str) -> dict:
	"""Make a saved logo the business's logo: the brand kit, post designs and every PDF use it from now (the one before
	is kept in Studio's saved logos only if it was made here). Owner and admins."""
	tenant = studio._tenant()
	if not _governs(tenant):
		frappe.throw(_("Only the owner and admins can change the business's logo."), frappe.PermissionError)
	doc = studio._mine(tenant, name)
	if doc.kind != "logo" or not doc.output:
		frappe.throw(_("That isn't a saved logo."))
	data = frappe.get_doc("File", {"file_url": doc.output, "attached_to_doctype": DESIGN, "attached_to_name": doc.name}).get_content()
	url = frappe.get_doc({"doctype": "File", "file_name": f"logo-{tenant}-{doc.name}.png", "content": data, "is_private": 0,
						  "attached_to_doctype": "QTT Tenant", "attached_to_name": tenant, "attached_to_field": "logo"}).insert(ignore_permissions=True).file_url
	frappe.db.set_value("QTT Tenant", tenant, "logo", url)
	return logo_home()


@frappe.whitelist(methods=["POST"])
def delete_logo(name: str) -> dict:
	"""Delete a saved logo and its files (the business's logo in use stays as it is)."""
	tenant = studio._tenant()
	doc = studio._mine(tenant, name)
	if doc.kind != "logo":
		frappe.throw(_("That isn't a saved logo."))
	for item in frappe.get_all(ITEM, filters={"design": doc.name}, pluck="name"):
		frappe.delete_doc(ITEM, item, ignore_permissions=True, force=True)
	for f in frappe.get_all("File", filters={"attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(DESIGN, doc.name, ignore_permissions=True, force=True)
	return {"saved": _saved(tenant)}
