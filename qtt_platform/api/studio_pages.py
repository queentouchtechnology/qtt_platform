"""
QTT Studio › Landing pages (PROJ-0012 S7): one-page sites for an offer, an event, a product launch or the business itself,
in its brand, at app.queentouchtech.in/p/<address>. Drafts are seen on a private preview link; publishing puts the page
on the web (counts towards the plan's pages — Starter none, Growth 1, Pro 5, editable in Desk).

  pages_home    the pages, what each kind is, the business's photos (for the top and the gallery), pages allowed / live
  new_page      a draft of a kind, filled from the business
  page          one page with everything to edit
  save_page     change a page (its words, sections, photos, address)
  publish       put it on the web, or take it off
  delete_page   delete it
  public_html   (the web) a published page, or a draft with its preview key — views counted on published ones

Who: as Studio (owner, admins, Studio members).
"""

import json

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

from qtt_platform.api import business_photos as bp
from qtt_platform.api import knowledge, studio
from qtt_platform.design import base, pages

DESIGN = "QTT Design"
ITEM = "QTT Library Item"
VIEWS = "qtt_page_views"


def _url(slug: str) -> str:
	return get_url(f"/p/{slug}")


def _allowed(tenant: str, ent: dict) -> int | None:
	"""Pages that may be live at once (None: no limit — QTT's own business)."""
	if frappe.get_attr("qtt_platform.house.is_house")(tenant):
		return None
	try:
		return max(0, int(float(ent.get("studio_pages") or 0)))
	except (TypeError, ValueError):
		return 0


def _live(tenant: str) -> int:
	return frappe.db.count(DESIGN, {"tenant": tenant, "kind": "page", "content": ["like", '%"published": true%']})


def _content(doc) -> dict:
	return json.loads(doc.content or "{}")


def _views(name: str) -> int:
	try:
		return int(frappe.cache.get(f"{VIEWS}:{name}") or 0)
	except Exception:
		return 0


def _out(doc, full: bool = False) -> dict:
	c = _content(doc)
	out = {"name": doc.name, "title": doc.title, "slug": doc.template, "url": _url(doc.template), "published": bool(c.get("published")),
		   "preview": _url(doc.template) + f"?preview={c.get('token')}", "kind": (c.get("page") or {}).get("kind"),
		   "views": _views(doc.name), "picture": get_url(doc.output) if doc.output else None, "modified": str(doc.modified)}
	if full:
		out["page"] = c.get("page") or {}
	return out


def _photos(tenant: str) -> dict:
	"""The business's own photos: name → public address."""
	return {r.name: r.image for r in bp._out(tenant) if r.image}


def _brand(tenant: str):
	k = knowledge.for_tenant(tenant) or {}
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	pal = base.palette(kit.get("colors") or {"primary": base.DEFAULT_PRIMARY})
	fonts = base.fonts(kit.get("font_heading") or "Poppins", kit.get("font_body") or "Inter", k.get("language") or "")
	return pal, fonts, k


def _contacts(tenant: str) -> dict:
	from qtt_platform.api.studio_print import _contacts as print_contacts  # profile, else what the invoices print

	return print_contacts(tenant)


def _free_slug(want: str, mine: str | None = None) -> str:
	s = pages.slugify(want)
	base_s, n = s, 2
	while frappe.db.exists(DESIGN, {"kind": "page", "template": s, "name": ["!=", mine or ""]}):
		s, n = f"{base_s}-{n}", n + 1
	return s


def _mine(tenant: str, name: str):
	doc = studio._mine(tenant, name)
	if doc.kind != "page":
		frappe.throw(_("That isn't a landing page."))
	return doc


def _render(doc, *, noindex: bool) -> str:
	tenant = doc.tenant
	pal, fonts, k = _brand(tenant)
	c = _content(doc)
	name = frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or ""
	logo = frappe.db.get_value("QTT Tenant", tenant, "logo")
	logo_url = (logo if str(logo).startswith("http") else get_url(logo)) if logo else None
	photos = {n: get_url(u) for n, u in _photos(tenant).items()}
	return pages.html(pages.clean(c.get("page") or {}), name=name, pal=pal, fonts=fonts, contacts=_contacts(tenant), knowledge=k,
					  logo_url=logo_url, photos=photos, url=_url(doc.template), noindex=noindex)


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def pages_home() -> dict:
	"""The pages (newest first), the kinds, the business's photos, pages allowed live and live now."""
	tenant = studio._tenant()
	ent = studio._entitlements(tenant)
	has = bool(ent) or frappe.get_attr("qtt_platform.house.is_house")(tenant)
	docs = [frappe.get_doc(DESIGN, n) for n in frappe.get_all(DESIGN, filters={"tenant": tenant, "kind": "page"}, pluck="name", order_by="modified desc")]
	return {"has_studio": has, "pages": [_out(d) for d in docs],
			"kinds": [{"key": k, "label": label} for k, (label, _s) in pages.KINDS.items()],
			"photos": [{"name": n, "image": get_url(u)} for n, u in _photos(tenant).items()],
			"allowed": _allowed(tenant, ent) if has else 0, "live": _live(tenant)}


@frappe.whitelist(methods=["POST"])
def new_page(kind: str = "offer") -> dict:
	"""A draft page of a kind, its words filled from the Business profile and knowledge."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	pal, fonts, k = _brand(tenant)
	name = frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or ""
	p = pages.clean(pages.start(kind, name=name, knowledge=k, contacts=_contacts(tenant)))
	slug = _free_slug(f"{name} {p['title']}" if p["title"] != name else name)
	doc = frappe.get_doc({"doctype": DESIGN, "tenant": tenant, "kind": "page", "made_by": "Template", "format": "story", "template": slug,
						  "title": p["title"] if p["title"] != name else name,
						  "content": json.dumps({"page": p, "published": False, "token": frappe.generate_hash(length=16)}, ensure_ascii=False)})
	doc.insert(ignore_permissions=True)
	return _out(doc, full=True)


@frappe.whitelist(methods=["GET"])
def page(name: str) -> dict:
	"""One page with everything to edit."""
	return _out(_mine(studio._tenant(), name), full=True)


@frappe.whitelist(methods=["POST"])
def save_page(name: str, page=None, slug: str | None = None) -> dict:
	"""Change a page: its words, sections, photos (the business's own), and — optionally — its address (letters, numbers
	and dashes; taken addresses get a number)."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	doc = _mine(tenant, name)
	c = _content(doc)
	p = pages.clean(json.loads(page) if isinstance(page, str) else (page or {}))
	own = set(_photos(tenant))
	p["gallery"] = [x for x in p["gallery"] if x in own]
	if p["hero"]["photo"] not in own:
		p["hero"]["photo"] = ""
	c["page"] = p
	if slug and pages.slugify(slug) != doc.template:
		doc.template = _free_slug(slug, doc.name)
	doc.title = p["title"] or doc.title
	doc.content = json.dumps(c, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	return _out(doc, full=True)


@frappe.whitelist(methods=["POST"])
def publish(name: str, on: int = 1) -> dict:
	"""Put the page on the web (within the plan's pages) — or take it off. A picture of it is kept in the Business Library."""
	tenant = studio._tenant()
	ent = studio._need_studio(tenant)
	doc = _mine(tenant, name)
	c = _content(doc)
	turn_on = str(on).lower() in ("1", "true")
	if turn_on and not c.get("published"):
		allowed = _allowed(tenant, ent)
		if allowed is not None and _live(tenant) >= allowed:
			frappe.throw(_("Your Studio plan has {0} live landing pages — take one off, or choose a bigger plan.").format(allowed)
						 if allowed else _("Landing pages come with Studio Growth and Pro — choose one of them in Plans and billing."))
	c["published"] = turn_on
	if turn_on:
		c["published_at"] = str(now_datetime())
	doc.content = json.dumps(c, ensure_ascii=False)
	doc.save(ignore_permissions=True)
	if turn_on:
		_picture(doc)
	return _out(doc, full=True)


def _picture(doc) -> None:
	"""A phone-sized picture of the page's top, kept as its library picture."""
	from qtt_platform.design import render

	try:
		png = render.png(_render(doc, noindex=True), 390, 844)
	except Exception:
		frappe.clear_messages()
		return
	url = frappe.get_doc({"doctype": "File", "file_name": f"page-{doc.name}-{frappe.generate_hash(length=6)}.png", "content": png, "is_private": 0,
						  "attached_to_doctype": DESIGN, "attached_to_name": doc.name}).insert(ignore_permissions=True).file_url
	old = doc.output
	item = frappe.get_doc(ITEM, doc.library_item) if doc.library_item and frappe.db.exists(ITEM, doc.library_item) else frappe.new_doc(ITEM)
	item.update({"tenant": doc.tenant, "title": doc.title, "kind": "page", "design": doc.name, "file": url, "format": "page", "products": "all",
				 "tags": f"url:{_url(doc.template)}"})
	item.save(ignore_permissions=True) if not item.is_new() else item.insert(ignore_permissions=True)
	doc.db_set({"output": url, "library_item": item.name})
	if old and old != url:
		for f in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
			frappe.delete_doc("File", f, ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def delete_page(name: str) -> dict:
	"""Delete a page (it goes off the web) and its picture."""
	tenant = studio._tenant()
	doc = _mine(tenant, name)
	for item in frappe.get_all(ITEM, filters={"design": doc.name}, pluck="name"):
		frappe.delete_doc(ITEM, item, ignore_permissions=True, force=True)
	for f in frappe.get_all("File", filters={"attached_to_doctype": DESIGN, "attached_to_name": doc.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(DESIGN, doc.name, ignore_permissions=True, force=True)
	return {"deleted": True}


def public_html(slug: str, preview: str = "") -> str | None:
	"""The web: a published page (its view counted) or a draft with its preview key; None when there's no such page."""
	name = frappe.db.get_value(DESIGN, {"kind": "page", "template": slug}, "name") if slug else None
	if not name:
		return None
	doc = frappe.get_doc(DESIGN, name)
	c = _content(doc)
	is_preview = bool(preview) and preview == c.get("token")
	if not c.get("published") and not is_preview:
		return None
	if c.get("published") and not is_preview:
		try:
			frappe.cache.incrby(f"{VIEWS}:{doc.name}", 1)
		except Exception:
			pass
	return _render(doc, noindex=is_preview or not c.get("published"))
