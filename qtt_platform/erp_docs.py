"""
The shared ERP document engine (PROJ-0019) — list, read, save, submit, cancel and "make the next document" for every kind in
erp_kinds.py, plus link lookups, ERPNext / HRMS reports, bank reconciliation and the customer portal. Orbitra ERP and
Office Pulse call it through their own APIs (qtt_orbitra.api.docs, qtt_office_pulse.api.hr_docs), which first check the
person's role and plan and hand over a Scope — the business's company and tenant, never read from the request.

Safety: only whitelisted fields are written (erp_kinds), every record read or written is checked to belong to this business
(company field, or the qtt_tenant field for company-less masters), and every link the app sends is checked the same way.
Records are saved with ignore_permissions after those checks (the person's ERPNext roles aren't used — as in the rest of
Orbitra and Office Pulse).
"""

import json
from dataclasses import dataclass, field
from typing import Callable

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from qtt_platform import erp_kinds as K

TENANT_FIELD = "qtt_tenant"
SEP = " · "
PAGE = 20


@dataclass
class Scope:
	company: str
	tenant: str
	abbr: str = ""
	currency: str = "INR"
	# Orbitra: GST on selling / buying documents (lines' tax templates, the taxes table) before they're saved
	prepare: Callable | None = field(default=None, repr=False)


def scope_for(company: str, tenant: str, prepare: Callable | None = None) -> Scope:
	c = frappe.db.get_value("Company", company, ["abbr", "default_currency"], as_dict=True) or {}
	return Scope(company=company, tenant=tenant, abbr=c.get("abbr") or "", currency=c.get("default_currency") or "INR", prepare=prepare)


# ---- set-up ------------------------------------------------------------------------------------------------------
def tenant_doctypes() -> set[str]:
	out = {k["doctype"] for k in K.KINDS if k["scope"] == "tenant"}
	out |= {dt for dt, scope, _l in K.LINKS.values() if scope == "tenant"}
	return {dt for dt in out if frappe.db.exists("DocType", dt)}


def ensure_tenant_fields() -> None:
	"""Company-less masters (Price List, Territory, Workstation, KRA, Skill…) get the qtt_tenant field (after migrate)."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	fields = {}
	for dt in tenant_doctypes():
		if not frappe.get_meta(dt).has_field(TENANT_FIELD):
			fields[dt] = [{"fieldname": TENANT_FIELD, "label": "QTT Workspace", "fieldtype": "Link", "options": "QTT Tenant",
						   "read_only": 1, "in_standard_filter": 1, "search_index": 1}]
	if fields:
		create_custom_fields(fields, update=True)


# ---- names: a business's own master is stored as "<name> · <ABBR>" so two businesses can both have "Retail" ----------
def plain(value, s: Scope):
	if isinstance(value, str) and s.abbr and value.endswith(SEP + s.abbr):
		return value[: -len(SEP + s.abbr)]
	return value


def _own_name(value: str, s: Scope) -> str:
	value = (value or "").strip()
	return value if not value or value.endswith(SEP + s.abbr) else f"{value}{SEP}{s.abbr}"


# ---- belonging ---------------------------------------------------------------------------------------------------
def _not_found():
	frappe.throw(_("Not found."), frappe.DoesNotExistError)


def belongs(doctype: str, name: str, scope: str, s: Scope) -> bool:
	if not name or not frappe.db.exists(doctype, name):
		return False
	if scope == "company":
		return frappe.db.get_value(doctype, name, "company") == s.company
	if scope == "company_bank":
		row = frappe.db.get_value(doctype, name, ["company", "account_type", "is_group"], as_dict=True) or {}
		return row.get("company") == s.company and row.get("account_type") in ("Bank", "Cash") and not row.get("is_group")
	if scope == "tenant":
		return frappe.db.get_value(doctype, name, TENANT_FIELD) == s.tenant
	if scope == "global":
		return True
	if scope == "item":  # Item Price, Batch: through the item
		item = frappe.db.get_value(doctype, name, "item_code" if doctype == "Item Price" else "item")
		return frappe.db.get_value("Item", item, TENANT_FIELD) == s.tenant
	if scope == "supplier":
		return frappe.db.get_value("Supplier", frappe.db.get_value(doctype, name, "supplier"), TENANT_FIELD) == s.tenant
	if scope == "employee":
		return frappe.db.get_value("Employee", frappe.db.get_value(doctype, name, "employee"), "company") == s.company
	if scope == "maintenance_plan":
		return frappe.db.get_value("Asset Maintenance", frappe.db.get_value(doctype, name, "asset_maintenance"), "company") == s.company
	if scope == "delivery_note":
		return frappe.db.get_value("Delivery Note", frappe.db.get_value(doctype, name, "delivery_note"), "company") == s.company
	if scope == "employee_user":
		return name in _team_users(s)
	return False


def _team_users(s: Scope) -> set[str]:
	return set(frappe.get_all("QTT Tenant Membership", filters={"tenant": s.tenant, "status": "active"}, pluck="user"))


def check_link(link: str, value, s: Scope):
	if value in (None, ""):
		return None
	doctype, scope, _label = K.LINKS[link]
	if not belongs(doctype, str(value), scope, s):
		frappe.throw(_("{0} isn't in your business.").format(frappe.bold(plain(value, s))), frappe.PermissionError)
	return value


def _kind(key: str, product: str) -> dict:
	k = K.BY_KEY.get(key)
	if not k or k["product"] != product:
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	return k


def _scope_filters(k: dict, s: Scope) -> dict | None:
	sc = k["scope"]
	if sc == "company":
		return {"company": s.company}
	if sc == "tenant":
		return {TENANT_FIELD: s.tenant}
	return None  # checked per row (item / supplier / employee / delivery note)


def _assert(k: dict, name: str, s: Scope):
	if not belongs(k["doctype"], name, k["scope"], s):
		_not_found()


# ---- read ----------------------------------------------------------------------------------------------------------
def _row(k: dict, d: dict, s: Scope) -> dict:
	title = d.get(k["title"]) or d.get("name")
	return {"name": d["name"], "title": plain(title, s), "sub": " · ".join(str(plain(d.get(f), s)) for f in k["sub"] if d.get(f)),
			"date": str(d.get(k["date"])) if k["date"] and d.get(k["date"]) else None,
			"amount": flt(d.get(k["amount"])) if k["amount"] else None,
			"status": d.get(k["status"]) if k["status"] else None, "docstatus": d.get("docstatus", 0)}


DOCSTATUS = {"Draft": 0, "Submitted": 1, "Cancelled": 2}


def list_docs(product: str, key: str, s: Scope, *, q: str = "", status: str = "", start: int = 0, size: int = PAGE) -> dict:
	k = _kind(key, product)
	meta = frappe.get_meta(k["doctype"])
	fields = ["name", "docstatus", "modified"] + [f for f in [k["title"], *k["sub"], k["date"], k["amount"], k["status"]]
												  if f and f not in ("name",) and meta.has_field(f)]
	fields = list(dict.fromkeys(fields))
	filters = _scope_filters(k, s) or {}
	if status in DOCSTATUS and meta.is_submittable:  # the app's Draft / Submitted / Cancelled are document states
		filters["docstatus"] = DOCSTATUS[status]
	elif status and k["status"] and meta.has_field(k["status"]):
		filters[k["status"]] = status
	or_filters = None
	if q:
		like = f"%{q.strip()[:60]}%"
		or_filters = [["name", "like", like]] + [[f, "like", like] for f in [k["title"], *k["sub"]] if f and meta.has_field(f)]
	size = max(1, min(cint(size) or PAGE, 50))
	rows = frappe.get_all(k["doctype"], filters=filters, or_filters=or_filters, fields=fields, order_by="modified desc",
						  start=cint(start), page_length=size + 1 if _scope_filters(k, s) else (size + 1) * 4)
	if _scope_filters(k, s) is None:  # checked per row
		rows = [r for r in rows if belongs(k["doctype"], r.name, k["scope"], s)]
	more = len(rows) > size
	return {"items": [_row(k, r, s) for r in rows[:size]], "has_more": more, "next_start": cint(start) + size}


def _value(f: dict, v, s: Scope):
	if f["type"] == "link":
		return {"value": v, "label": plain(_link_label(f["extra"], v), s) if v else None}
	if isinstance(v, (int, float, str)) or v is None:
		return plain(v, s)
	return str(v)


def _link_label(link: str, value) -> str | None:
	doctype, _sc, label = K.LINKS[link]
	if not value:
		return None
	return (frappe.db.get_value(doctype, value, label) if label != "name" else value) or value


def get_doc(product: str, key: str, s: Scope, name: str) -> dict:
	k = _kind(key, product)
	_assert(k, name, s)
	doc = frappe.get_doc(k["doctype"], name)
	def raw(f):
		if f["name"] == "__newname":
			return doc.name
		if f["name"] == "__receipt":
			return (doc.get("purchase_receipts") or [frappe._dict()])[0].get("receipt_document")
		return doc.get(f["name"])

	head = {f["name"]: _value(f, raw(f), s) for f in k["fields"]}
	lines = []
	if k["table"]:
		for r in doc.get(k["table"]["field"]) or []:
			lines.append({f["name"]: _value(f, r.get(f["name"]), s) for f in k["table"]["fields"]})
	totals = {f: flt(doc.get(f)) for f in ("total", "total_taxes_and_charges", "grand_total", "rounded_total", "outstanding_amount", "per_billed",
										   "per_delivered", "per_received", "total_cost", "final_score") if doc.meta.has_field(f)}
	return {"name": doc.name, "kind": key, "title": plain(doc.get(k["title"]) or doc.name, s), "docstatus": doc.docstatus,
			"status": doc.get(k["status"]) if k["status"] else None, "fields": head, "lines": lines, "totals": totals,
			"currency": doc.get("currency") or s.currency, "can_edit": doc.docstatus == 0, "can_submit": k["submit"] and doc.docstatus == 0,
			"can_cancel": k["submit"] and doc.docstatus == 1,
			"next": [{"index": i, "label": n["label"], "kind": n["kind"]} for i, n in enumerate(k["next"]) if doc.docstatus == 1 or not k["submit"]],
			"modified": str(doc.modified)}


# ---- write ---------------------------------------------------------------------------------------------------------
def _clean(f: dict, v, s: Scope):
	t = f["type"]
	if v in (None, "") and t not in ("check",):
		return None
	if t == "link":
		return check_link(f["extra"], v, s)
	if t in ("int",):
		return cint(v)
	if t in ("float", "currency"):
		return flt(v)
	if t == "check":
		return 1 if str(v).lower() in ("1", "true", "yes") else 0
	if t == "date":
		return str(getdate(v))
	if t == "select":
		opts = (f["extra"] or "").split("\n")
		if str(v) not in opts:
			frappe.throw(_("Choose one of: {0}").format(", ".join(o for o in opts if o)))
		return str(v)
	return str(v)[:2000 if t == "text" else 240]


def save_doc(product: str, key: str, s: Scope, data: dict, name: str | None = None) -> dict:
	k = _kind(key, product)
	data = data or {}
	if name:
		_assert(k, name, s)
		doc = frappe.get_doc(k["doctype"], name)
		if doc.docstatus != 0:
			frappe.throw(_("A submitted document can't be changed — cancel it first, or make a new one."))
	else:
		if not k["create"]:
			frappe.throw(_("These are made from another document."))
		doc = frappe.new_doc(k["doctype"])
		if doc.meta.has_field("company"):
			doc.company = s.company
		if k["scope"] == "tenant" or doc.meta.has_field(TENANT_FIELD):
			doc.set(TENANT_FIELD, s.tenant)
	head = data.get("fields") or {}
	title_field = k["title"]
	for f in k["fields"]:
		if f["name"] not in head:
			continue
		v = _clean(f, head[f["name"]], s)
		if f["name"] == "__receipt":
			if v and k["doctype"] == "Landed Cost Voucher" and not doc.get("purchase_receipts"):
				pr = frappe.db.get_value("Purchase Receipt", v, ["supplier", "grand_total", "posting_date", "docstatus"], as_dict=True)
				if pr.docstatus != 1:
					frappe.throw(_("Submit the goods receipt first."))
				doc.append("purchase_receipts", {"receipt_document_type": "Purchase Receipt", "receipt_document": v, "supplier": pr.supplier,
												 "grand_total": pr.grand_total, "posting_date": pr.posting_date})
				doc.get_items_from_purchase_receipts()
			continue
		if f["name"] == "__newname":
			if not name:
				doc.name = _own_name(str(v or ""), s)
				doc.flags.name_set = True
			continue
		if not name and k["scope"] == "tenant" and f["name"] == title_field and isinstance(v, str) and k["doctype"] not in ("Batch", "Non Conformance", "Job Applicant", "Interview"):
			v = _own_name(v, s)  # this business's own master, unique across businesses
		doc.set(f["name"], v)
	if k["table"] and "lines" in data:
		tf = k["table"]
		doc.set(tf["field"], [])
		for line in (data.get("lines") or [])[:300]:
			row = {f["name"]: _clean(f, line.get(f["name"]), s) for f in tf["fields"] if f["name"] in line}
			if any(v not in (None, "", 0) for v in row.values()):
				doc.append(tf["field"], row)
	if doc.meta.has_field("currency") and not doc.get("currency"):
		doc.currency = s.currency
	_dynamic_checks(doc, s)
	_defaults(doc, s)
	if s.prepare:
		s.prepare(doc)
	doc.flags.ignore_permissions = True
	try:
		doc.save() if name else doc.insert()
	except frappe.ValidationError:
		raise
	except Exception as e:  # ERPNext's own checks: say it plainly, keep the details for QTT
		frappe.log_error(title=f"ERP save: {k['doctype']}")
		frappe.throw(_("Couldn't save: {0}").format(str(e)[:300]))
	return get_doc(product, key, s, doc.name)


def _dynamic_checks(doc, s: Scope):
	"""Fields that point at one of several kinds of record (a customer or a lead, the document an inspection is for…)."""
	party_from = doc.get("opportunity_from") or doc.get("quotation_to")
	if doc.get("party_name") and party_from:
		check_link("customer" if party_from == "Customer" else "lead", doc.party_name, s)
	if doc.doctype == "Quality Inspection" and doc.get("reference_name"):
		if frappe.db.get_value(doc.reference_type, doc.reference_name, "company") != s.company:
			frappe.throw(_("That document isn't in your business."), frappe.PermissionError)
	if doc.doctype == "Asset Maintenance Log" and doc.get("asset_maintenance"):
		if frappe.db.get_value("Asset Maintenance", doc.asset_maintenance, "company") != s.company:
			frappe.throw(_("That maintenance plan isn't in your business."), frappe.PermissionError)


def _defaults(doc, s: Scope):
	"""What ERPNext needs that the app doesn't ask for."""
	today = nowdate()
	for f in ("transaction_date", "posting_date"):
		if doc.meta.has_field(f) and not doc.get(f):
			doc.set(f, today)
	if doc.doctype in ("Purchase Order", "Material Request") and not doc.get("schedule_date"):
		doc.schedule_date = frappe.utils.add_days(today, 7)
	if doc.doctype == "Sales Order" and not doc.get("delivery_date"):
		doc.delivery_date = frappe.utils.add_days(today, 7)
	for r in doc.get("items") or []:
		if r.meta.has_field("schedule_date") and not r.get("schedule_date"):
			r.schedule_date = doc.get("schedule_date") or today
		if r.meta.has_field("delivery_date") and not r.get("delivery_date"):
			r.delivery_date = doc.get("delivery_date") or today
		if r.meta.has_field("uom") and not r.get("uom") and r.get("item_code"):
			r.uom = frappe.db.get_value("Item", r.item_code, "stock_uom")
	if doc.doctype == "Request for Quotation" and not doc.get("suppliers"):
		pass  # suppliers are added on the RFQ page (supplier lines)
	if hasattr(doc, "set_missing_values"):
		try:
			doc.set_missing_values()
		except Exception:
			pass


def submit_doc(product: str, key: str, s: Scope, name: str) -> dict:
	k = _kind(key, product)
	_assert(k, name, s)
	doc = frappe.get_doc(k["doctype"], name)
	if not k["submit"] or doc.docstatus != 0:
		frappe.throw(_("This can't be submitted."))
	doc.flags.ignore_permissions = True
	doc.submit()
	return get_doc(product, key, s, name)


def cancel_doc(product: str, key: str, s: Scope, name: str) -> dict:
	k = _kind(key, product)
	_assert(k, name, s)
	doc = frappe.get_doc(k["doctype"], name)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted document can be cancelled."))
	doc.flags.ignore_permissions = True
	doc.cancel()
	return get_doc(product, key, s, name)


def delete_doc(product: str, key: str, s: Scope, name: str) -> dict:
	k = _kind(key, product)
	_assert(k, name, s)
	if frappe.db.get_value(k["doctype"], name, "docstatus") == 1:
		frappe.throw(_("Cancel it first."))
	frappe.delete_doc(k["doctype"], name, ignore_permissions=True)
	return {"deleted": name}


def make_next(product: str, key: str, s: Scope, name: str, index: int) -> dict:
	"""The next document (delivery note from a sales order…) made by ERPNext's own mapper, saved as a draft."""
	k = _kind(key, product)
	_assert(k, name, s)
	nexts = k["next"]
	if not 0 <= cint(index) < len(nexts):
		frappe.throw(_("Not found."))
	n = nexts[cint(index)]
	target = K.BY_KEY[n["kind"]]
	if n["mapper"].startswith("prefill:"):  # a new form, already pointing at this document (the person fills the rest)
		return {"kind": target["key"], "name": None, "prefill": {n["mapper"][len("prefill:"):]: name}}
	fn = frappe.get_attr(n["mapper"])
	out = fn(name) if not n["mapper"].startswith("qtt_platform.erp_docs.") else fn(name, s)
	if isinstance(out, str):  # some mappers save and return a name
		new_name = out
	else:
		doc = frappe.get_doc(out) if isinstance(out, dict) else out
		if doc.meta.has_field("company") and not doc.get("company"):
			doc.company = s.company
		if s.prepare:
			s.prepare(doc)
		doc.flags.ignore_permissions = True
		doc.insert()
		new_name = doc.name
	if target["product"] != product:
		frappe.throw(_("Not found."))
	return {"kind": target["key"], "name": new_name}


def wo_transfer(work_order: str, s: Scope):
	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

	return frappe.get_doc(make_stock_entry(work_order, "Material Transfer for Manufacture"))


def wo_finish(work_order: str, s: Scope):
	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

	return frappe.get_doc(make_stock_entry(work_order, "Manufacture"))


def landed_cost_from_receipt(receipt: str, s: Scope):
	doc = frappe.new_doc("Landed Cost Voucher")
	doc.company = s.company
	pr = frappe.db.get_value("Purchase Receipt", receipt, ["supplier", "grand_total", "posting_date"], as_dict=True)
	doc.append("purchase_receipts", {"receipt_document_type": "Purchase Receipt", "receipt_document": receipt, "supplier": pr.supplier,
									 "grand_total": pr.grand_total, "posting_date": pr.posting_date})
	doc.get_items_from_purchase_receipts()
	return doc


# ---- links -----------------------------------------------------------------------------------------------------------
def lookup(link: str, s: Scope, q: str = "", limit: int = 20) -> list[dict]:
	if link not in K.LINKS:
		frappe.throw(_("Not found."))
	doctype, scope, label = K.LINKS[link]
	meta = frappe.get_meta(doctype)
	filters, or_filters = {}, None
	if scope == "company":
		filters["company"] = s.company
	elif scope == "company_bank":
		filters.update({"company": s.company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0})
	elif scope == "tenant":
		filters[TENANT_FIELD] = s.tenant
	elif scope == "employee_user":
		filters["name"] = ["in", list(_team_users(s)) or ["-"]]
	if doctype == "Account" and scope == "company":
		filters["is_group"] = 0
	for f in ("disabled",):
		if meta.has_field(f):
			filters[f] = 0
	if q:
		like = f"%{q.strip()[:60]}%"
		or_filters = [["name", "like", like]] + ([[label, "like", like]] if label != "name" and meta.has_field(label) else [])
	fields = ["name"] + ([label] if label != "name" and meta.has_field(label) else [])
	rows = frappe.get_all(doctype, filters=filters, or_filters=or_filters, fields=fields, order_by="modified desc", limit=min(cint(limit) or 20, 50))
	return [{"value": r.name, "label": plain(r.get(label) or r.name, s)} for r in rows]


# ---- reports ---------------------------------------------------------------------------------------------------------
def _fy(s: Scope, on=None) -> str | None:
	from erpnext.accounts.utils import get_fiscal_year

	try:
		return get_fiscal_year(on or nowdate(), company=s.company)[0]
	except Exception:
		return None


def report(product: str, key: str, s: Scope, filters: dict | None = None) -> dict:
	r = K.REPORTS.get(key)
	if not r or r[6] != product:
		frappe.throw(_("Not found."))
	label, _g, _a, _p, module, kind_of_filters, _prod = r
	f = frappe._dict(company=s.company)
	given = filters or {}
	start = given.get("from_date") or str(getdate(nowdate()).replace(month=4, day=1) if getdate(nowdate()).month >= 4 else getdate(nowdate()).replace(year=getdate(nowdate()).year - 1, month=4, day=1))
	end = given.get("to_date") or nowdate()
	fy = _fy(s, end)
	if kind_of_filters in ("fy", "fy_period", "budget", "fy_dates"):
		f.update(fiscal_year=fy, from_fiscal_year=fy, to_fiscal_year=fy, from_date=start, to_date=end, period_start_date=start, period_end_date=end,
				 periodicity="Yearly", filter_based_on="Date Range", period="Yearly", show_zero_values=0)
	if kind_of_filters == "budget":
		f.update(budget_against="Cost Center", period="Yearly")
	if kind_of_filters in ("dates", "fy_dates"):
		f.update(from_date=start, to_date=end)
	if kind_of_filters == "funnel":
		from erpnext.selling.page.sales_funnel.sales_funnel import get_funnel_data

		data = get_funnel_data(start, end, s.company)
		return {"label": label, "columns": [{"label": "Stage", "fieldname": "title"}, {"label": "Count", "fieldname": "value", "fieldtype": "Int"}],
				"rows": [{"title": d.get("title"), "value": d.get("value")} for d in data or []], "from_date": start, "to_date": end}
	try:
		mod = frappe.get_module(module)
		out = mod.execute(f)
	except Exception as e:
		frappe.log_error(title=f"ERP report: {key}")
		frappe.throw(_("This report couldn't be made: {0}").format(str(e)[:200]))
	columns, data = (out[0], out[1]) if isinstance(out, (list, tuple)) else ([], [])
	cols = []
	for c in columns or []:
		if isinstance(c, str):  # "Label:Type:width"
			parts = c.split(":")
			cols.append({"label": parts[0], "fieldname": frappe.scrub(parts[0]), "fieldtype": (parts[1] if len(parts) > 1 else "Data").split("/")[0]})
		else:
			cols.append({"label": c.get("label"), "fieldname": c.get("fieldname"), "fieldtype": c.get("fieldtype") or "Data"})
	rows = []
	for d in (data or [])[:500]:
		if isinstance(d, dict):
			rows.append({c["fieldname"]: _cell(d.get(c["fieldname"]), s) for c in cols})
		elif isinstance(d, (list, tuple)):
			rows.append({c["fieldname"]: _cell(v, s) for c, v in zip(cols, d)})
	return {"label": label, "columns": cols, "rows": rows, "from_date": start, "to_date": end}


def _cell(v, s: Scope):
	if isinstance(v, (int, float)) or v is None:
		return v
	return plain(str(v), s)


# ---- bank reconciliation (clearance dates) ---------------------------------------------------------------------------
def bank_open(s: Scope, account: str | None = None) -> dict:
	"""Payments in and out of a bank account not cleared yet, oldest first (the bank's date goes on each)."""
	accounts = lookup("bank_account", s, limit=50)
	account = account or (accounts[0]["value"] if accounts else None)
	if account:
		check_link("bank_account", account, s)
	rows = []
	if account:
		for pe in frappe.get_all("Payment Entry", filters={"company": s.company, "docstatus": 1, "clearance_date": ["is", "not set"]},
								 or_filters=[["paid_from", "=", account], ["paid_to", "=", account]],
								 fields=["name", "posting_date", "party", "paid_amount", "paid_from", "reference_no"], order_by="posting_date asc", limit=200):
			rows.append({"doctype": "Payment Entry", "name": pe.name, "date": str(pe.posting_date), "party": plain(pe.party, s),
						 "amount": flt(pe.paid_amount) * (-1 if pe.paid_from == account else 1), "reference": pe.reference_no})
		for je in frappe.db.sql("""select je.name, je.posting_date, je.cheque_no, sum(a.debit - a.credit) amt
			from `tabJournal Entry` je join `tabJournal Entry Account` a on a.parent = je.name
			where je.company=%s and je.docstatus=1 and je.clearance_date is null and a.account=%s
			group by je.name order by je.posting_date limit 200""", (s.company, account), as_dict=True):
			rows.append({"doctype": "Journal Entry", "name": je.name, "date": str(je.posting_date), "party": "", "amount": flt(je.amt), "reference": je.cheque_no})
	return {"accounts": accounts, "account": account, "rows": sorted(rows, key=lambda r: r["date"])}


def bank_clear(s: Scope, doctype: str, name: str, clearance_date: str) -> dict:
	if doctype not in ("Payment Entry", "Journal Entry"):
		frappe.throw(_("Not found."))
	if frappe.db.get_value(doctype, name, "company") != s.company:
		_not_found()
	frappe.db.set_value(doctype, name, "clearance_date", getdate(clearance_date) if clearance_date else None)
	return {"ok": True}


# ---- customer portal ------------------------------------------------------------------------------------------------
def portal_invite(s: Scope, customer: str, email: str) -> dict:
	"""A customer's own login to see their orders, invoices and quotations on the web (ERPNext's customer portal)."""
	check_link("customer", customer, s)
	email = (email or "").strip().lower()
	if "@" not in email:
		frappe.throw(_("Enter the customer's email."))
	contact = frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
	if not contact:
		c = frappe.new_doc("Contact")
		c.first_name = plain(frappe.db.get_value("Customer", customer, "customer_name"), s) or email
		c.append("email_ids", {"email_id": email, "is_primary": 1})
		c.append("links", {"link_doctype": "Customer", "link_name": customer})
		c.flags.ignore_permissions = True
		c.insert()
		contact = c.name
	elif not frappe.db.exists("Dynamic Link", {"parent": contact, "link_doctype": "Customer", "link_name": customer}):
		c = frappe.get_doc("Contact", contact)
		c.append("links", {"link_doctype": "Customer", "link_name": customer})
		c.flags.ignore_permissions = True
		c.save()
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": frappe.db.get_value("Contact", contact, "first_name") or email,
							"user_type": "Website User", "send_welcome_email": 1})
		u.add_roles("Customer")
		u.flags.ignore_permissions = True
		u.insert()
	else:
		frappe.get_doc("User", email).add_roles("Customer")
	frappe.db.set_value("Contact", contact, "user", email)
	return {"ok": True, "url": frappe.utils.get_url("/orders")}


# ---- the catalogue the app draws from ------------------------------------------------------------------------------
def _with_required(k: dict) -> dict:
	"""The kind as the app gets it: each field marked required when ERPNext requires it."""
	meta = frappe.get_meta(k["doctype"])
	out = dict(k)
	out["fields"] = [{**f, "required": bool(f["name"] == "__newname" or (meta.get_field(f["name"]) and meta.get_field(f["name"]).reqd))}
					 for f in k["fields"]]
	if k["table"]:
		tf = meta.get_field(k["table"]["field"])
		child = frappe.get_meta(tf.options) if tf else None
		out["table"] = {**k["table"], "fields": [{**f, "required": bool(child and child.get_field(f["name"]) and child.get_field(f["name"]).reqd)}
												 for f in k["table"]["fields"]]}
	return out


def catalogue(product: str, areas: list[str], features: dict) -> dict:
	kinds = [_with_required(k) for k in K.kinds_for(product) if K.allowed(k["area"], k["plan"], areas, features)]
	reports = [{"key": key, "label": r[0], "group": r[1]} for key, r in K.REPORTS.items() if r[6] == product and K.allowed(r[2], r[3], areas, features)]
	tools = [{"key": key, "label": t[0], "group": t[1]} for key, t in K.TOOLS.items() if t[4] == product and K.allowed(t[2], t[3], areas, features)]
	locked = sorted({k["group"] for k in K.kinds_for(product)} - {k["group"] for k in kinds})
	return {"kinds": kinds, "reports": reports, "tools": tools, "groups": [g for g in K.GROUP_ORDER if any(
		x["group"] == g for x in kinds + reports + tools)], "locked": locked}
