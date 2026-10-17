"""
The post template library (PROJ-0011 C) for a business's owner and admins:

  library   the templates, filtered by post type and business group (default: the business's own group, from Business ›
            Knowledge › Type of business), each with its library picture
  preview   one template in the business's own brand — its logo, colours and fonts, its name, phone, website and
            address, photos for its type of business — in any size and look; kept, so the same preview is never made twice
"""

import hashlib
import json

import frappe
from frappe import _

from qtt_platform.api import knowledge
from qtt_platform.design import base, business_types, catalog, library, post
from qtt_platform.tenant.guards import require_tenant_role

PREVIEWS_PER_DAY = 40


def _tenant() -> str:
	tenant = knowledge._tenant()
	require_tenant_role(tenant, knowledge.GOVERNANCE)
	return tenant


def _group_of(tenant: str) -> str:
	t = knowledge.for_tenant(tenant).get("business_type")
	return business_types.group_of(t) if t else ""


@frappe.whitelist(methods=["GET"])
def library_list(post_type: str | None = None, group: str | None = None, start: int = 0, limit: int = 30) -> dict:
	"""Templates for this business: {templates: [{key, title, layout, post_types, groups, look, picture}], total, group,
	post_types: [{key, label, count}], groups: [{key, label}]}. group '' = the business's own group; 'all' = every one."""
	tenant = _tenant()
	mine = _group_of(tenant)
	g = mine if group in (None, "") else ("" if group == "all" else group)
	rows = [library.row_dict(frappe.get_doc(library.DT, n)) for n in
			frappe.get_all(library.DT, filters={"enabled": 1}, pluck="name", order_by="sort asc")]
	in_group = [r for r in rows if catalog.matches(r, group=g or None)]
	chosen = [r for r in in_group if catalog.matches(r, post_type=post_type or None)]
	start, limit = max(0, int(start or 0)), min(60, max(1, int(limit or 30)))
	counts = {k: sum(1 for r in in_group if k in r["post_types"]) for k in catalog.POST_TYPES}
	return {
		"templates": [{"key": r["key"], "title": r["title"], "label": (catalog.LAYOUTS.get(r["layout"]) or {}).get("label") or r["title"],
					   "name": r["title"].split(" · ", 1)[-1], "layout": r["layout"], "post_types": r["post_types"], "groups": r["groups"],
					   "look": r["look"], "picture": library.picture(r, g)} for r in chosen[start:start + limit]],
		"total": len(chosen), "group": g, "my_group": mine,
		"post_types": [{"key": k, "label": label, "count": counts[k]} for k, label in catalog.POST_TYPES.items() if counts[k]],
		"groups": [{"key": k, "label": label} for k, label in business_types.GROUPS],
	}


def business_content(tenant: str, layout: str, group: str) -> dict:
	"""The template's sample words, with the business's own name and contact details in place of the sample's."""
	c = catalog.sample_for(layout, group or "any")
	contacts = knowledge.contacts(tenant)
	c["business"] = frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or c.get("business")
	for key in ("phone", "website", "email", "address"):
		if key in c or key in ("phone", "website"):
			val = contacts.get(key) or (contacts.get("whatsapp") if key == "phone" else "")
			if val:
				c[key] = val
			elif key in c and key != "phone":
				c.pop(key)
	return c


@frappe.whitelist(methods=["POST"])
def preview(key: str, format: str = "square", look: str | None = None) -> dict:  # noqa: A002
	"""One template in the business's own brand (logo, colours, fonts, name, contacts; photos for its type of business).
	The words are the template's sample until the post is written (Marketing assistant). {url, width, height}."""
	from frappe.utils import get_url, today

	tenant = _tenant()
	if not frappe.db.get_value(library.DT, {"name": key, "enabled": 1}):
		frappe.throw(_("That design isn't in the library any more."), frappe.DoesNotExistError)
	t = library.row_dict(frappe.get_doc(library.DT, key))
	fmt = format if format in post.SIZES else "square"
	k = knowledge.for_tenant(tenant) or knowledge.save_for(tenant, {})
	kit = knowledge.rules.brand(k, knowledge.contacts(tenant).get("brand_color") or "")
	fonts = (kit["font_heading"] or catalog.FONT_SETS[t["fonts"]][0], kit["font_body"] or catalog.FONT_SETS[t["fonts"]][1])
	group = _group_of(tenant) or (t["groups"][0] if t["groups"][0] != "any" else "any")
	btype = k.get("business_type")
	photos = post.kit_photos(business_types.photo_kit(btype) if btype else catalog.sample_kit(t["layout"], group), 5)
	content = business_content(tenant, t["layout"], group)
	logo = knowledge._logo(tenant)
	the_look = look if look in ("light", "dark", "brand") else t["look"]
	sig = hashlib.sha1(json.dumps([t, fmt, the_look, kit, fonts, content, logo[0], len(logo[1] or b""), [n for n, _ in photos],
								   catalog.catalog_hash()], sort_keys=True, default=str).encode()).hexdigest()[:14]
	name = frappe.db.get_value(knowledge.DT, {"tenant": tenant})
	fname = f"post-preview-{name}-{sig}.png"
	have = frappe.db.get_value("File", {"file_name": fname, "attached_to_doctype": knowledge.DT, "attached_to_name": name}, "file_url")
	if not have:
		ck = f"qtt_post_preview:{tenant}:{today()}"
		n = int(frappe.cache.get_value(ck) or 0) + 1
		if n > PREVIEWS_PER_DAY:
			frappe.throw(_("That's enough previews for today — try again tomorrow."))
		frappe.cache.set_value(ck, n, expires_in_sec=2 * 86400)
		data = post.render(t["layout"], t["variant"], colors=kit["colors"] or {"primary": base.DEFAULT_PRIMARY}, fonts=fonts, look=the_look,
						   fmt=fmt, content=content, photos=photos, logo=logo if logo[1] else None, language=k.get("language") or "")
		have = frappe.get_doc({"doctype": "File", "file_name": fname, "content": data, "is_private": 0, "attached_to_doctype": knowledge.DT,
							   "attached_to_name": name}).insert(ignore_permissions=True).file_url
	return {"url": get_url(have), "width": 1080, "height": post.SIZES[fmt], "key": key, "format": fmt, "look": the_look}
