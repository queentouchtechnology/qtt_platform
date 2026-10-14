"""
Customers of the active workspace — one directory shared by every QTT
product (Inbox contacts link here; invoices, quotes and CRM can follow).
Every member can view, add and edit; archiving is for everyone, deleting is
for the owner and admins. Phone and email are unique within a workspace.
"""

import json

import frappe
from frappe import _

from qtt_platform import business_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role
from qtt_platform.smart_list import smart_get_all

DT = "QTT Customer"
GOVERNANCE = ["Tenant Owner", "Tenant Admin"]
LIST_FIELDS = ["name", "customer_name", "customer_type", "company_name", "phone", "email", "city", "tags", "status",
			   "source", "modified"]
FIELDS = ("customer_name", "customer_type", "company_name", "contact_person", "phone", "whatsapp", "email",
		  "address_line1", "address_line2", "city", "state", "pincode", "country", "gstin", "pan", "tags", "notes")


def _tenant() -> tuple[str, object]:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."))
	membership = require_tenant_membership(tenant)
	from qtt_platform import abilities

	abilities.require(membership, "customers")  # owners, admins, and people who bill or chat with customers
	return tenant, membership


def _doc(tenant: str, name: str):
	if not name or frappe.db.get_value(DT, name, "tenant") != tenant:
		frappe.throw(_("Customer not found."), frappe.DoesNotExistError)
	return frappe.get_doc(DT, name)


def _out(doc) -> dict:
	d = {f: doc.get(f) for f in FIELDS}
	d.update({"name": doc.name, "status": doc.status, "source": doc.source, "inbox_contact_id": doc.inbox_contact_id,
			  "tag_list": rules.tag_list(doc.tags), "gst_state": rules.gst_state(doc.gstin),
			  "created": str(doc.creation), "modified": str(doc.modified)})
	return d


def clean_customer(data: dict, default_country: str | None) -> dict:
	out = {}
	out["customer_name"] = rules._text(data.get("customer_name"))
	if not 1 <= len(out["customer_name"]) <= 140:
		raise rules.ProfileError("Enter the customer's name.")
	out["customer_type"] = data.get("customer_type") if data.get("customer_type") in ("Individual", "Business") else "Individual"
	for f in ("company_name", "contact_person", "address_line1", "address_line2", "city", "state"):
		out[f] = rules._text(data.get(f))[:140] or None
	out["notes"] = rules._text(data.get("notes"))[:5000] or None
	out["country"] = rules._text(data.get("country")) or default_country or None
	out["pincode"] = rules.clean_pincode(data.get("pincode"), out["country"])
	out["phone"] = rules.clean_phone(data.get("phone"))
	out["whatsapp"] = rules.clean_phone(data.get("whatsapp"))
	out["email"] = rules.clean_email(data.get("email"))
	out["gstin"] = rules.clean_gstin(data.get("gstin"))
	out["pan"] = rules.clean_pan(data.get("pan")) or (out["gstin"][2:12] if out["gstin"] else None)
	rules.check_gstin_pan(out["gstin"], out["pan"])
	if out["gstin"] and not out["state"]:
		out["state"] = rules.gst_state(out["gstin"])
	out["tags"] = rules.clean_tags(data.get("tags"))
	return out


def _duplicate(tenant: str, values: dict, exclude: str | None) -> None:
	messages = {"phone": _("Another customer already has this phone number. Search for it instead."),
				"email": _("Another customer already has this email address. Search for it instead.")}
	for field, message in messages.items():
		if values.get(field) and frappe.db.exists(DT, {"tenant": tenant, field: values[field], "name": ["!=", exclude or ""]}):
			frappe.throw(message)


@frappe.whitelist(methods=["GET"])
def customers(q: str | None = None, status: str = "Active", tag: str | None = None, start: int = 0,
			  page_length: int = 50) -> dict:
	tenant, _m = _tenant()
	start, page_length = max(int(start or 0), 0), min(max(int(page_length or 50), 1), 200)
	filters = [[DT, "tenant", "=", tenant]]
	if status in ("Active", "Archived"):
		filters.append([DT, "status", "=", status])
	if tag:
		filters.append([DT, "tags", "like", f"%{tag.strip()}%"])
	# Intelligent search: every word, any order, phone digits, one typo forgiven.
	rows, has_more = smart_get_all(DT, filters=filters, fields=LIST_FIELDS, q=q, title_field="customer_name",
								   search_fields=["customer_name", "company_name", "email", "city", "gstin"], digits_field="phone",
								   order_by="customer_name asc", start=start, page_length=page_length)
	for r in rows:
		r["modified"] = str(r.modified)
		r["tag_list"] = rules.tag_list(r.pop("tags"))
	return {"customers": rows, "start": start, "has_more": has_more,
			"counts": {s: frappe.db.count(DT, {"tenant": tenant, "status": s}) for s in ("Active", "Archived")}}


@frappe.whitelist(methods=["GET"])
def customer(name: str) -> dict:
	tenant, m = _tenant()
	return {**_out(_doc(tenant, name)), "can_delete": m.tenant_role in GOVERNANCE}


@frappe.whitelist(methods=["GET"])
def tags() -> list[str]:
	tenant, _m = _tenant()
	seen = {}
	for t in frappe.get_all(DT, filters={"tenant": tenant, "tags": ["is", "set"]}, pluck="tags"):
		for tag in rules.tag_list(t):
			seen.setdefault(tag.lower(), tag)
	return sorted(seen.values(), key=str.lower)


@frappe.whitelist(methods=["POST"])
def save_customer(data, name: str | None = None) -> dict:
	tenant, _m = _tenant()
	data = json.loads(data) if isinstance(data, str) else (data or {})
	try:
		values = clean_customer(data, frappe.db.get_value("QTT Tenant", tenant, "country"))
	except rules.ProfileError as e:
		frappe.throw(_(str(e)))
	if values["country"] and not frappe.db.exists("Country", values["country"]):
		frappe.throw(_("Choose a country from the list."))
	_duplicate(tenant, values, name)
	if name:
		doc = _doc(tenant, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": DT, "tenant": tenant, "status": "Active", "source": "Manual", **values})
		doc.insert(ignore_permissions=True)
	write_audit_event("customer_saved" if name else "customer_created", tenant=tenant, target_doctype=DT, target_name=doc.name)
	return customer(doc.name)


@frappe.whitelist(methods=["POST"])
def set_status(name: str, status: str) -> dict:
	tenant, _m = _tenant()
	if status not in ("Active", "Archived"):
		frappe.throw(_("Status must be Active or Archived."))
	doc = _doc(tenant, name)
	doc.status = status
	doc.save(ignore_permissions=True)
	write_audit_event(f"customer_{status.lower()}", tenant=tenant, target_doctype=DT, target_name=name)
	return customer(name)


@frappe.whitelist(methods=["POST"])
def delete_customer(name: str) -> dict:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."))
	require_tenant_role(tenant, GOVERNANCE)
	doc = _doc(tenant, name)
	frappe.delete_doc(DT, doc.name, ignore_permissions=True)
	write_audit_event("customer_deleted", tenant=tenant, target_doctype=DT, target_name=name,
					  metadata={"customer_name": doc.customer_name})
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def for_contact(inbox_contact_id: int | None = None, contact_name: str | None = None, phone: str | None = None,
				email: str | None = None, create: int = 0) -> dict:
	"""The customer behind an Inbox contact: by contact id, then phone, then
	email (linking the contact on a match). With create=1 a new customer is
	made from the contact when none matches."""
	tenant, _m = _tenant()
	cid = int(inbox_contact_id) if inbox_contact_id not in (None, "", "null") else None
	norm_phone = rules.normalize_phone(phone) if phone else None
	try:
		norm_email = rules.clean_email(email)
	except rules.ProfileError:
		norm_email = None
	name = None
	if cid:
		name = frappe.db.get_value(DT, {"tenant": tenant, "inbox_contact_id": cid}, "name")
	for field, value in (("phone", norm_phone), ("email", norm_email)):
		if not name and value:
			name = frappe.db.get_value(DT, {"tenant": tenant, field: value}, "name")
	if name:
		if cid and not frappe.db.get_value(DT, name, "inbox_contact_id"):
			frappe.db.set_value(DT, name, "inbox_contact_id", cid)
		return {"customer": customer(name), "created": False}
	if not int(create or 0):
		return {"customer": None, "created": False}
	label = rules._text(contact_name) or norm_phone or norm_email or _("Unknown contact")
	doc = frappe.get_doc({"doctype": DT, "tenant": tenant, "status": "Active", "source": "Inbox",
						  "customer_name": label[:140], "phone": norm_phone, "whatsapp": norm_phone, "email": norm_email,
						  "inbox_contact_id": cid, "country": frappe.db.get_value("QTT Tenant", tenant, "country")})
	doc.insert(ignore_permissions=True)
	write_audit_event("customer_created", tenant=tenant, target_doctype=DT, target_name=doc.name, metadata={"source": "Inbox"})
	return {"customer": customer(doc.name), "created": True}
