"""
Branding and GST helpers for printed documents (PDFs) — available in every print
format as `qtt_brand(company)`, `qtt_gst_summary(doc)` and `qtt_hsn(item)` (hooks.jenv).

Each business's logo, name, address, GSTIN, contacts, bank and brand colour come
from its own Business profile (QTT Business Profile + the workspace logo), so a
change in the app updates every PDF. A company with no workspace (or no profile
yet) falls back to what ERPNext's Company has.
"""

import json
import re

import frappe

DEFAULT_COLOR = "#3B5CFF"  # queentouchtech.com blue


def _tenant_for_company(company: str | None) -> str | None:
	if not company:
		return None
	for doctype in ("Orbitra Workspace", "Office Pulse Workspace"):
		if frappe.db.table_exists(doctype):
			tenant = frappe.db.get_value(doctype, {"company": company}, "tenant")
			if tenant:
				return tenant
	return frappe.db.get_value("QTT Tenant", {"tenant_name": company}, "name")


def _color(value: str | None) -> str:
	value = (value or "").strip()
	return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else DEFAULT_COLOR


def brand(company: str | None = None) -> dict:
	"""Everything a document header/footer needs, as plain values (already safe to print)."""
	company = company or frappe.defaults.get_user_default("Company")
	c = frappe.db.get_value("Company", company, ["company_name", "company_logo", "tax_id", "phone_no", "email", "website",
												 "default_currency"], as_dict=True) if company else None
	c = c or frappe._dict()
	tenant = _tenant_for_company(company)
	p = frappe.db.get_value("QTT Business Profile", tenant, ["*"], as_dict=True) if tenant and frappe.db.table_exists("QTT Business Profile") else None
	p = p or frappe._dict()
	t = frappe.db.get_value("QTT Tenant", tenant, ["tenant_name", "legal_name", "logo"], as_dict=True) if tenant else frappe._dict()
	t = t or frappe._dict()
	address = [x for x in (p.address_line1, p.address_line2, " ".join(x for x in (p.city, p.pincode) if x), p.state) if x]
	if not address and company:
		from frappe.contacts.doctype.address.address import get_company_address

		addr = get_company_address(company)
		if addr and addr.get("company_address_display"):
			address = [x.strip() for x in re.split(r"<br\s*/?>", addr.company_address_display) if x.strip()]
	return frappe._dict({
		"name": t.get("legal_name") or t.get("tenant_name") or c.company_name or company or "",
		"tagline": p.tagline or "",
		"logo": t.get("logo") or c.company_logo or "",
		"address": address,
		"gstin": p.gstin or c.tax_id or "",
		"pan": p.pan or "",
		"phone": p.phone or c.phone_no or "",
		"whatsapp": p.whatsapp or "",
		"email": p.email or c.email or "",
		"website": p.website or c.website or "",
		"color": _color(p.brand_color),
		"footer": p.letterhead_footer or "",
		"bank": frappe._dict({"account_name": p.bank_account_name or "", "bank": p.bank_name or "", "branch": p.bank_branch or "",
							  "number": p.bank_account_number or "", "ifsc": p.bank_ifsc or "", "upi": p.upi_id or ""}),
		"currency": c.default_currency or "INR",
		"state_code": (p.gstin or c.tax_id or "")[:2],
		# Orbitra's "message at the bottom of every bill" (Business settings)
		"invoice_footer": (frappe.db.get_value("Orbitra Workspace", {"company": company}, "invoice_footer")
						   if company and frappe.db.table_exists("Orbitra Workspace") else "") or "",
	})


def hsn(item_code: str | None) -> str:
	"""HSN/SAC code of an item (Orbitra keeps it in Item.qtt_hsn); blank when unknown."""
	if not item_code or not frappe.db.has_column("Item", "qtt_hsn"):
		return ""
	return frappe.db.get_value("Item", item_code, "qtt_hsn") or ""


def _tax_kind(account: str) -> str | None:
	a = (account or "").upper()
	for kind in ("CGST", "SGST", "UTGST", "IGST", "CESS"):
		if kind in a:
			return "SGST" if kind == "UTGST" else kind
	return None


def gst_summary(doc) -> dict:
	"""HSN-wise taxable value and CGST/SGST/IGST for an invoice-like document.
	Uses each tax row's item_wise_tax_detail (ERPNext), and the item's HSN (Orbitra's qtt_hsn)."""
	hsn_of = {}
	rows: dict[str, dict] = {}
	for it in doc.get("items") or []:
		code = it.item_code
		if code not in hsn_of:
			hsn_of[code] = hsn(code) or it.get("gst_hsn_code") or "-"
		r = rows.setdefault(hsn_of[code], {"hsn": hsn_of[code], "taxable": 0.0, "CGST": 0.0, "SGST": 0.0, "IGST": 0.0, "CESS": 0.0, "rate": 0.0})
		r["taxable"] += float(it.net_amount or it.amount or 0)
	totals = {"taxable": 0.0, "CGST": 0.0, "SGST": 0.0, "IGST": 0.0, "CESS": 0.0}
	for tax in doc.get("taxes") or []:
		kind = _tax_kind(tax.account_head) or _tax_kind(tax.description)
		if not kind:
			continue
		try:
			detail = json.loads(tax.item_wise_tax_detail or "{}")
		except ValueError:
			detail = {}
		for code, val in detail.items():
			rate, amount = (val[0], val[1]) if isinstance(val, (list, tuple)) else (val.get("tax_rate", 0), val.get("tax_amount", 0))
			code_hsn = hsn_of.get(code, "-")
			r = rows.setdefault(code_hsn, {"hsn": code_hsn, "taxable": 0.0, "CGST": 0.0, "SGST": 0.0, "IGST": 0.0, "CESS": 0.0, "rate": 0.0})
			r[kind] += float(amount or 0)
			if kind in ("CGST", "SGST", "IGST"):
				r["rate"] = max(r["rate"], float(rate or 0) * (2 if kind in ("CGST", "SGST") else 1))
		totals[kind] += float(tax.tax_amount or 0)
	totals["taxable"] = sum(r["taxable"] for r in rows.values())
	out = []
	for r in rows.values():
		r["tax"] = r["CGST"] + r["SGST"] + r["IGST"] + r["CESS"]
		out.append(r)
	totals["tax"] = totals["CGST"] + totals["SGST"] + totals["IGST"] + totals["CESS"]
	return {"rows": sorted(out, key=lambda r: r["hsn"]), "totals": totals, "interstate": totals["IGST"] > 0}
