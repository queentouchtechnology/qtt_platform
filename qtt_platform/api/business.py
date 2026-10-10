"""
Business profile of the active workspace: name, legal name and logo (on
QTT Tenant) plus address, tax IDs, contact, brand and bank (QTT Business
Profile). Every member can read it; the owner and admins edit it. Bank
details are returned only to the owner and admins.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_url

from qtt_platform import business_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

DT = "QTT Business Profile"
GOVERNANCE = ["Tenant Owner", "Tenant Admin"]
MAX_LOGO_BYTES = 2 * 1024 * 1024
LOGO_TYPES = (".png", ".jpg", ".jpeg", ".webp")

PLAIN = ("tagline", "address_line1", "address_line2", "city", "state", "letterhead_footer",
		 "facebook", "instagram", "linkedin", "youtube", "x_twitter", "bank_account_name", "bank_name", "bank_branch")
BANK = ("bank_account_name", "bank_name", "bank_branch", "bank_account_number", "bank_ifsc", "upi_id")
FIELDS = PLAIN + ("pincode", "country", "gstin", "pan", "phone", "whatsapp", "email", "website", "brand_color",
				  "bank_account_number", "bank_ifsc", "upi_id")
LIMITS = {"tagline": 140, "letterhead_footer": 500}


def _active_tenant() -> str:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Select a workspace first."))
	return tenant


def absolute_url(path: str | None) -> str | None:
	if not path:
		return None
	return path if path.startswith("http") else get_url(path)


def clean_profile(data: dict, country: str | None) -> dict:
	"""Validated, normalised profile fields (ProfileError on bad input)."""
	out = {}
	for f in PLAIN:
		out[f] = (rules._text(data.get(f)) or None)
		if out[f] and len(out[f]) > LIMITS.get(f, 200):
			raise rules.ProfileError(_("{0} is too long.").format(f.replace("_", " ").capitalize()))
	out["country"] = rules._text(data.get("country")) or country or None
	out["pincode"] = rules.clean_pincode(data.get("pincode"), out["country"])
	out["gstin"] = rules.clean_gstin(data.get("gstin"))
	out["pan"] = rules.clean_pan(data.get("pan")) or (out["gstin"][2:12] if out["gstin"] else None)
	rules.check_gstin_pan(out["gstin"], out["pan"])
	if out["gstin"] and not out["state"]:
		out["state"] = rules.gst_state(out["gstin"])
	out["phone"] = rules.clean_phone(data.get("phone"))
	out["whatsapp"] = rules.clean_phone(data.get("whatsapp"))
	out["email"] = rules.clean_email(data.get("email"))
	out["website"] = rules.clean_url(data.get("website"))
	out["brand_color"] = rules.clean_colour(data.get("brand_color"))
	out["bank_account_number"] = rules.clean_account_number(data.get("bank_account_number"))
	out["bank_ifsc"] = rules.clean_ifsc(data.get("bank_ifsc"))
	out["upi_id"] = rules.clean_upi(data.get("upi_id"))
	return out


def profile_for(tenant: str, *, with_bank: bool) -> dict:
	"""Also used server-side by products (invoices, payslips, quotes)."""
	t = frappe.db.get_value("QTT Tenant", tenant, ["tenant_name", "legal_name", "logo", "country", "currency"], as_dict=True)
	p = frappe.db.get_value(DT, tenant, list(FIELDS), as_dict=True) or {}
	out = {f: p.get(f) for f in FIELDS if with_bank or f not in BANK}
	out.update({
		"tenant": tenant,
		"tenant_name": t.tenant_name,
		"legal_name": t.legal_name,
		"logo": absolute_url(t.logo),
		"country": out.get("country") or t.country,
		"gst_state": rules.gst_state(out.get("gstin")),
	})
	return out


@frappe.whitelist(methods=["GET"])
def get_profile() -> dict:
	tenant = _active_tenant()
	m = require_tenant_membership(tenant)
	can_edit = m.tenant_role in GOVERNANCE
	return {**profile_for(tenant, with_bank=can_edit), "can_edit": can_edit}


@frappe.whitelist(methods=["POST"])
def save_profile(data) -> dict:
	tenant = _active_tenant()
	require_tenant_role(tenant, GOVERNANCE)
	data = json.loads(data) if isinstance(data, str) else (data or {})

	name = rules._text(data.get("tenant_name"))
	if not 2 <= len(name) <= 80:
		frappe.throw(_("Business name must be 2–80 characters."))
	legal = rules._text(data.get("legal_name"))[:140] or None
	try:
		values = clean_profile(data, frappe.db.get_value("QTT Tenant", tenant, "country"))
	except rules.ProfileError as e:
		frappe.throw(_(str(e)))
	if values["country"] and not frappe.db.exists("Country", values["country"]):
		frappe.throw(_("Choose a country from the list."))

	t = frappe.get_doc("QTT Tenant", tenant)
	if t.tenant_name != name or (t.legal_name or None) != legal:
		t.tenant_name, t.legal_name = name, legal
		t.save(ignore_permissions=True)  # the tenant hook refreshes every member's app

	doc = frappe.get_doc(DT, tenant) if frappe.db.exists(DT, tenant) else frappe.new_doc(DT)
	doc.tenant = tenant
	doc.update(values)
	doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
	write_audit_event("business_profile_updated", tenant=tenant, target_doctype=DT, target_name=tenant,
					  metadata={"fields": sorted(k for k, v in values.items() if v)})
	return get_profile()


@frappe.whitelist(methods=["POST"])
def upload_logo() -> dict:
	"""Multipart (field `file`). Public file: the logo appears on PDFs and the web chat."""
	tenant = _active_tenant()
	require_tenant_role(tenant, GOVERNANCE)
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose an image."))
	content = upload.stream.read(MAX_LOGO_BYTES + 1)
	fname = (upload.filename or "logo.png").strip()
	if len(content) > MAX_LOGO_BYTES:
		frappe.throw(_("The logo must be 2 MB or smaller."))
	if not fname.lower().endswith(LOGO_TYPES):
		frappe.throw(_("The logo must be a PNG, JPG or WEBP image."))
	f = frappe.get_doc({"doctype": "File", "file_name": f"logo-{frappe.generate_hash(length=8)}{fname[fname.rfind('.'):]}",
						"content": content, "attached_to_doctype": "QTT Tenant", "attached_to_name": tenant,
						"attached_to_field": "logo", "is_private": 0}).insert(ignore_permissions=True)
	_set_logo(tenant, f.file_url)
	write_audit_event("business_logo_changed", tenant=tenant, target_doctype="QTT Tenant", target_name=tenant)
	return get_profile()


@frappe.whitelist(methods=["POST"])
def remove_logo() -> dict:
	tenant = _active_tenant()
	require_tenant_role(tenant, GOVERNANCE)
	_set_logo(tenant, None)
	write_audit_event("business_logo_removed", tenant=tenant, target_doctype="QTT Tenant", target_name=tenant)
	return get_profile()


def _set_logo(tenant: str, url: str | None):
	t = frappe.get_doc("QTT Tenant", tenant)
	old = t.logo
	t.logo = url
	t.save(ignore_permissions=True)
	if old and old != url:
		for name in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": "QTT Tenant",
													"attached_to_name": tenant}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True)
