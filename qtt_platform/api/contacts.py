"""
Office Pulse Contacts (PROJ-0016 C2): the people in the business, and the business's address book — customers,
suppliers, partners and others (QTT Customer with a kind; the list and the form are api/customers.py's, with kind).

  directory     everyone in the business: name, role, phone, email, photo (to call, WhatsApp or email)
  export_vcf    the address book (or one kind) as a .vcf file — for a phone, Google or Outlook
  import_vcf    a .vcf from a phone, Google or Outlook into the address book (as one kind); someone with the same phone
                or email is skipped, not doubled
"""

import frappe
from frappe import _
from frappe.utils import cstr

from qtt_platform import contacts_rules as cr

DT = "QTT Customer"


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


@frappe.whitelist(methods=["GET"])
def directory() -> dict:
	"""Everyone in the business with their role, phone and email."""
	from qtt_platform.api.team import _people

	ctx = _ctx()
	people = _people(ctx.tenant)
	info = {u.name: u for u in frappe.get_all("User", filters={"name": ["in", list(people) or [""]]},
											   fields=["name", "email", "mobile_no", "phone", "user_image"])}
	pulse = {}
	ms = {m.name: m.user for m in frappe.get_all("QTT Tenant Membership", filters={"tenant": ctx.tenant, "status": "active"}, fields=["name", "user"])}
	for a in frappe.get_all("QTT Product Access", filters={"tenant": ctx.tenant, "product": "QTT_OFFICE_PULSE", "status": "active"}, fields=["membership", "product_role"]):
		if a.membership in ms:
			pulse[ms[a.membership]] = a.product_role
	out = []
	for u, p in sorted(people.items(), key=lambda x: x[1]["name"].lower()):
		i = info.get(u) or {}
		out.append({"user": u, "name": p["name"], "role": p.get("role"), "job": pulse.get(u), "email": i.get("email") or u,
					"phone": i.get("mobile_no") or i.get("phone") or "", "image": p.get("image"), "me": u == ctx.user})
	return {"people": out}


@frappe.whitelist(methods=["GET"])
def export_vcf(kind: str = "all"):
	"""The address book (or one kind: Customer / Supplier / Partner / Other) as a .vcf file."""
	ctx = _ctx()
	f = {"tenant": ctx.tenant, "status": "Active"}
	if kind in cr.KINDS:
		f["kind"] = kind
	rows = frappe.get_all(DT, filters=f, fields=["customer_name", "company_name", "phone", "whatsapp", "email", "address_line1", "city", "state",
												 "pincode", "country", "notes", "kind"], order_by="customer_name asc", limit=20000)
	frappe.local.response.filename = f"contacts-{kind.lower()}.vcf"
	frappe.local.response.filecontent = cr.to_vcf(rows).encode("utf-8")
	frappe.local.response.type = "download"


@frappe.whitelist(methods=["POST"])
def import_vcf(kind: str = "Customer") -> dict:
	"""Multipart `file`: a .vcf from a phone, Google or Outlook → the address book as `kind`. Someone already there (same
	phone or email) is skipped. → {added, skipped, failed}."""
	from qtt_platform.api.customers import clean_customer

	ctx = _ctx()
	if kind not in cr.KINDS:
		kind = "Customer"
	up = frappe.request.files.get("file") if frappe.request else None
	if not up:
		frappe.throw(_("Choose a .vcf contacts file."))
	data = up.stream.read(10 * 1024 * 1024 + 1)
	if len(data) > 10 * 1024 * 1024:
		frappe.throw(_("A contacts file can be up to 10 MB."))
	cards = cr.parse_vcf(data.decode("utf-8", "ignore"))
	if not cards:
		frappe.throw(_("No contacts with a name and a number or email were found in that file."))
	country = frappe.db.get_value("QTT Tenant", ctx.tenant, "country")
	added = skipped = failed = 0
	for card in cards[:5000]:
		try:
			values = clean_customer(card, country)
		except Exception:
			failed += 1
			continue
		dup = any(values.get(f) and frappe.db.exists(DT, {"tenant": ctx.tenant, f: values[f]}) for f in ("phone", "email"))
		if dup:
			skipped += 1
			continue
		frappe.get_doc({"doctype": DT, "tenant": ctx.tenant, "status": "Active", "source": "Import", "kind": kind, **values}).insert(ignore_permissions=True)
		added += 1
	from qtt_platform.audit import write_audit_event

	write_audit_event("contacts_imported", tenant=ctx.tenant, target_doctype=DT, metadata={"added": added, "skipped": skipped, "kind": kind, "file": cstr(up.filename)[:80]})
	return {"added": added, "skipped": skipped, "failed": failed}
