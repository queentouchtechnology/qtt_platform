"""
QTT Studio › Business documents (PROJ-0012 S3). The letterhead every PDF uses, and letters written on it.

  docs_home       the styles (each drawn as a page with the business's own logo, colour and details), the one in use,
                  the letters made (newest first)
  set_style       the letterhead for every PDF — Orbitra's invoices, quotations, challans and receipts, Office Pulse's
                  payslips, letters and ID cards (QTT's own "band" is free; the others need Studio)
  write_letter    AI drafts a letter from a few words and the Business knowledge — never inventing facts (1 AI credit)
  make_letter     the letter as a PDF on the letterhead, kept in the Business Library
  blank_letterhead   the letterhead alone as a PDF (for a print shop)
  delete_document    a letter or letterhead PDF

Who: as Studio (owner, admins, Studio members); a style only the owner and admins.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import formatdate, get_url, today

from qtt_platform.api import knowledge, studio
from qtt_platform.studio import docs_rules as rules

ITEM = "QTT Library Item"
PROFILE = "QTT Business Profile"
LETTER = "qtt_platform/templates/print/letter.html"
PICTURE = (794, 600)  # the top of an A4 page at 96 px an inch — the style pictures


def _brand(tenant: str, style: str | None = None):
	from qtt_platform import print_brand

	b = print_brand.brand(tenant=tenant)
	if style in rules.STYLES:  # a style's picture before it's chosen
		b.style, b.ink = style, frappe._dict(rules.colours(b.color, style))
	if b.logo and not b.logo.startswith("http"):
		b.logo = get_url(b.logo)
	return b


def _html(b, letter: dict | None) -> str:
	return frappe.render_template(LETTER, {"b": b, "l": frappe._dict(letter) if letter else None})


def _pdf(html: str) -> bytes:
	from frappe.utils.pdf import get_pdf

	return get_pdf(html, {"page-size": "A4", "margin-top": "12mm", "margin-bottom": "12mm", "margin-left": "14mm", "margin-right": "14mm"})


def _sample(b) -> dict:
	return {"ref": "L-0001", "date": formatdate(today()), "to": _("Mr. Kumar\nChennai"), "subject": _("Thank you for your order"),
			"greeting": _("Dear Mr. Kumar,"),
			"paragraphs": [_("Thank you for choosing {0}. This page shows how your letters, bills and payslips look in this style.").format(b.name),
						   _("Your logo, your colour and your details come from your Business profile, so every document stays the same.")],
			"closing": _("Warm regards,"), "signer": _("For") + " " + b.name}


def _templates_code() -> bytes:
	from pathlib import Path

	here = Path(frappe.get_app_path("qtt_platform", "templates", "print"))
	return b"".join((here / f).read_bytes() for f in ("qtt.html", "letter.html"))


def _picture(tenant: str, style: str) -> str | None:
	"""The style drawn as a page in the business's own brand (made once for each brand, then kept)."""
	from qtt_platform.design import render

	b = _brand(tenant, style)
	sig = hashlib.sha1(json.dumps([style, b], sort_keys=True, default=str).encode() + _templates_code()).hexdigest()[:12]
	fname = f"doc-style-{tenant}-{style}-{sig}.png"
	url = frappe.db.get_value("File", {"file_name": fname}, "file_url")
	if url:
		return get_url(url)
	for old in frappe.get_all("File", filters={"file_name": ["like", f"doc-style-{tenant}-{style}-%"], "attached_to_doctype": "QTT Tenant"},
							  pluck="name"):  # an older picture of this style (the brand or the style changed)
		frappe.delete_doc("File", old, ignore_permissions=True)
	if not render.ready():
		return None
	try:
		png = render.png(_html(b, _sample(b)), *PICTURE)
	except frappe.ValidationError:
		frappe.clear_messages()
		return None
	url = frappe.get_doc({"doctype": "File", "file_name": fname, "content": png, "is_private": 0, "attached_to_doctype": "QTT Tenant",
						  "attached_to_name": tenant}).insert(ignore_permissions=True).file_url
	return get_url(url)


def _governs(tenant: str) -> bool:
	return frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": frappe.session.user, "status": "active"},
							   "tenant_role") in knowledge.GOVERNANCE


def _items(tenant: str) -> list[dict]:
	rows = frappe.get_all(ITEM, filters={"tenant": tenant, "kind": "document"}, fields=["name", "title", "file", "format", "modified"],
						  order_by="creation desc", page_length=60)
	return [{"name": r.name, "title": r.title, "file": get_url(r.file) if r.file else None, "what": r.format, "modified": str(r.modified)}
			for r in rows]


def _keep(tenant: str, title: str, what: str, pdf: bytes) -> dict:
	item = frappe.get_doc({"doctype": ITEM, "tenant": tenant, "title": title[:140], "kind": "document", "format": what, "products": "all"})
	item.insert(ignore_permissions=True)
	url = frappe.get_doc({"doctype": "File", "file_name": f"studio-{what}-{frappe.generate_hash(length=10)}.pdf", "content": pdf,
						  "is_private": 0, "attached_to_doctype": ITEM, "attached_to_name": item.name}).insert(ignore_permissions=True).file_url
	item.db_set("file", url)
	return {"name": item.name, "title": item.title, "file": get_url(url), "what": what}


# ---- endpoints ---------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def docs_home() -> dict:
	"""The letterhead styles drawn in the business's brand, the one every PDF uses now, whether this person may change
	it, and the letters made."""
	tenant = studio._tenant()
	has = bool(studio._entitlements(tenant)) or frappe.get_attr("qtt_platform.house.is_house")(tenant)
	saved = frappe.db.get_value(PROFILE, tenant, "document_style") if frappe.db.exists(PROFILE, tenant) else None
	return {
		"has_studio": has, "can_change": _governs(tenant), "style": rules.style_for(saved, has),
		"styles": [{"key": k, "label": label, "about": about, "free": k == rules.DEFAULT, "picture": _picture(tenant, k)}
				   for k, (label, about) in rules.STYLES.items()],
		"documents": _items(tenant),
	}


@frappe.whitelist(methods=["POST"])
def set_style(style: str) -> dict:
	"""Use a letterhead style for every PDF the business prints. Owner and admins; QTT's own style is free, the others
	need QTT Studio."""
	tenant = studio._tenant()
	if style not in rules.STYLES:
		frappe.throw(_("Choose a style."))
	if not _governs(tenant):
		frappe.throw(_("Only the owner and admins can change how documents look."), frappe.PermissionError)
	if style != rules.DEFAULT:
		studio._need_studio(tenant)
	if not frappe.db.exists(PROFILE, tenant):
		frappe.get_doc({"doctype": PROFILE, "tenant": tenant}).insert(ignore_permissions=True)
	frappe.db.set_value(PROFILE, tenant, "document_style", style)
	return docs_home()


@frappe.whitelist(methods=["POST"])
def write_letter(request: str, to: str = "") -> dict:
	"""AI drafts a letter from a few words ("thank a customer for a big order") and the Business knowledge — never
	inventing prices, dates or promises ([ ] where a fact is missing). 1 AI credit. {subject, greeting, body, closing}."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	if len((request or "").strip()) < 4:
		frappe.throw(_("Say what the letter is about."))
	brief, lang = studio._brief(tenant)
	answer = rules.parse_letter(studio._ai(tenant, "letter", rules.letter_prompt(request=request, to=to, brief=brief, language=lang),
										   max_tokens=1200))
	if not answer:
		frappe.throw(_("Studio couldn't write that just now — no credits were used. Try saying it another way."))
	return answer


@frappe.whitelist(methods=["POST"])
def make_letter(subject: str = "", body: str = "", to: str = "", greeting: str = "", closing: str = "", signer: str = "", ref: str = "") -> dict:
	"""The letter as a PDF on the business's letterhead (its style, logo, colour and details), kept in the Business
	Library. {name, title, file}."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	paras = rules.paragraphs(body)
	if not paras:
		frappe.throw(_("Write the letter first."))
	b = _brand(tenant)
	html = _html(b, {"ref": (ref or "").strip()[:40], "date": formatdate(today()), "to": (to or "").strip()[:300],
					 "subject": (subject or "").strip()[:160], "greeting": (greeting or "").strip()[:120], "paragraphs": paras,
					 "closing": (closing or "").strip()[:80], "signer": (signer or "").strip()[:80] or None})
	return _keep(tenant, (subject or "").strip() or _("Letter"), "letter", _pdf(html))


@frappe.whitelist(methods=["POST"])
def blank_letterhead() -> dict:
	"""The letterhead alone as a PDF (A4) — for a print shop, or to write on by hand. Kept in the Business Library."""
	tenant = studio._tenant()
	studio._need_studio(tenant)
	return _keep(tenant, _("Letterhead"), "letterhead", _pdf(_html(_brand(tenant), None)))


@frappe.whitelist(methods=["POST"])
def delete_document(item: str) -> dict:
	"""Delete a letter or letterhead PDF from the library."""
	tenant = studio._tenant()
	if not frappe.db.exists(ITEM, {"name": item, "tenant": tenant, "kind": "document"}):
		frappe.throw(_("That document isn't here any more."), frappe.DoesNotExistError)
	for f in frappe.get_all("File", filters={"attached_to_doctype": ITEM, "attached_to_name": item}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)
	frappe.delete_doc(ITEM, item, ignore_permissions=True, force=True)
	return {"documents": _items(tenant)}
