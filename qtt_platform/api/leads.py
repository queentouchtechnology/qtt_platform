"""
Content Hub › Leads (PROJ Content Hub, step 3) on Frappe CRM's own records, each with the business's qtt_tenant:

  CRM Lead     someone who asked (New / Talking)
  CRM Deal     made when the quote goes (Quote sent), closed Won or Lost (Frappe CRM's lost reason)
  CRM Task     the next step and "Remind me later" (its due date)
  FCRM Note    what happened (a note, a call, the quote)

  overview      the list — To do / All / Won, with counts
  lead          one lead: its stage, next step, what happened, the quote
  add           a new lead (name, phone or email, what they want, value, where it came from)
  note          what happened, in a line
  remind        Remind me later (in 2 hours / tomorrow / next week / a day)
  task_done     a next step done
  set_stage     New ⇄ Talking
  quote         the quote: lines and GST → a CRM Deal with its products + the WhatsApp message to send
  close         Won (they join Customers) or Lost (why)

Rules (pure, tested): qtt_platform.leads_rules. Everyone who may see customers (abilities "customers") uses it.
QTT's own leads (the Lead Engine, the website form) belong to the QTT house workspace: a CRM record made without a
business gets it (default_tenant, before_insert).
"""

import json
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from qtt_platform import leads_rules as rules
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership

TENANT = "qtt_tenant"
LEAD, DEAL, TASK, NOTE, CALL = "CRM Lead", "CRM Deal", "CRM Task", "FCRM Note", "CRM Call Log"
OPEN_TASK = ["Backlog", "Todo", "In Progress"]
CUSTOMER = "QTT Customer"


# ---- set-up (after migrate) ----------------------------------------------------------------------------------------
def setup() -> None:
	"""The business field on Frappe CRM's records, what the lead wants, the Phone Call source; records made before
	this belong to QTT's own workspace."""
	if not frappe.db.exists("DocType", LEAD):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	tenant_field = {"fieldname": TENANT, "label": "QTT Workspace", "fieldtype": "Link", "options": "QTT Tenant", "read_only": 1,
					"in_standard_filter": 1, "search_index": 1}
	fields = {dt: [dict(tenant_field)] for dt in (LEAD, DEAL, TASK, NOTE, CALL) if frappe.db.exists("DocType", dt)}
	for dt in (LEAD, DEAL):
		fields[dt].append({"fieldname": "qtt_need", "label": "What they want", "fieldtype": "Data", "insert_after": "status"})
	create_custom_fields(fields, update=True)
	if not frappe.db.exists("CRM Lead Source", "Phone Call"):
		frappe.get_doc({"doctype": "CRM Lead Source", "source_name": "Phone Call"}).insert(ignore_permissions=True)
	house = house_tenant()
	if house:
		for dt in fields:
			frappe.db.sql(f"update `tab{dt}` set `{TENANT}`=%s where ifnull(`{TENANT}`, '')=''", house)
	frappe.db.commit()


def house_tenant() -> str | None:
	"""QTT's own workspace — where the Lead Engine's and QTT website's leads belong (site config qtt_crm_tenant first)."""
	if frappe.conf.get("qtt_crm_tenant"):
		return frappe.conf.get("qtt_crm_tenant")
	if not frappe.db.has_column("QTT Tenant", "is_house"):
		return None
	return (frappe.db.get_value("QTT Tenant", {"is_house": 1, "tenant_name": "Queen Touch Technology"}, "name")
			or frappe.db.get_value("QTT Tenant", {"is_house": 1}, "name", order_by="creation asc"))


def default_tenant(doc, method=None):
	"""before_insert on Frappe CRM's records: one made without a business (the Lead Engine, Desk) gets its lead's /
	deal's business, else QTT's own."""
	if not frappe.get_meta(doc.doctype).has_field(TENANT) or doc.get(TENANT):
		return
	ref_dt, ref = doc.get("reference_doctype"), doc.get("reference_docname")
	tenant = None
	if ref_dt in (LEAD, DEAL) and ref:
		tenant = frappe.db.get_value(ref_dt, ref, TENANT)
	if not tenant and doc.doctype == DEAL and doc.get("lead"):
		tenant = frappe.db.get_value(LEAD, doc.lead, TENANT)
	doc.set(TENANT, tenant or house_tenant())


# ---- helpers -------------------------------------------------------------------------------------------------------
def _tenant() -> str:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."))
	membership = require_tenant_membership(tenant)
	from qtt_platform import abilities

	abilities.require(membership, "customers")
	return tenant


def _err(e: rules.LeadError):
	frappe.throw(_(str(e)))


def _split(id_: str) -> tuple[str, str]:
	kind, _sep, name = (id_ or "").partition(":")
	dt = {"lead": LEAD, "deal": DEAL}.get(kind)
	if not dt or not name:
		frappe.throw(_("Lead not found."), frappe.DoesNotExistError)
	return dt, name


def _doc(tenant: str, id_: str):
	dt, name = _split(id_)
	if frappe.db.get_value(dt, name, TENANT) != tenant:
		frappe.throw(_("Lead not found."), frappe.DoesNotExistError)
	return frappe.get_doc(dt, name)


def _id(doctype: str, name: str) -> str:
	return ("deal:" if doctype == DEAL else "lead:") + name


def _display(d) -> str:
	return (d.get("lead_name") or " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x) or d.get("organization")
			or d.get("mobile_no") or d.get("email") or "").strip()


def _currency(tenant: str) -> str:
	if frappe.db.has_column("QTT Tenant", "currency"):
		return frappe.db.get_value("QTT Tenant", tenant, "currency") or "INR"
	return "INR"


def _open_tasks(tenant: str, refs: list[tuple[str, str]] | None = None) -> dict:
	"""(doctype, name) → its earliest open task {name, title, due}."""
	filters = {TENANT: tenant, "status": ["in", OPEN_TASK], "reference_doctype": ["in", [LEAD, DEAL]]}
	if refs is not None:
		if not refs:
			return {}
		filters["reference_docname"] = ["in", [n for _d, n in refs]]
	out = {}
	for t in frappe.get_all(TASK, filters=filters, fields=["name", "title", "due_date", "reference_doctype", "reference_docname"],
							order_by="due_date asc", limit=0):
		key = (t.reference_doctype, t.reference_docname)
		if key not in out:
			out[key] = {"name": t.name, "title": t.title, "due": get_datetime(t.due_date) if t.due_date else None}
	return out


def _note(tenant: str, dt: str, name: str, text: str, title: str = "Note") -> None:
	frappe.get_doc({"doctype": NOTE, "title": title[:140], "content": frappe.utils.escape_html(text)[:5000], "reference_doctype": dt,
					"reference_docname": name, TENANT: tenant}).insert(ignore_permissions=True)


def _task(tenant: str, dt: str, name: str, title: str, at: datetime) -> str:
	t = frappe.get_doc({"doctype": TASK, "title": title[:140], "status": "Todo", "priority": "Medium", "due_date": at,
						"reference_doctype": dt, "reference_docname": name, "assigned_to": frappe.session.user if frappe.session.user != "Guest" else None,
						TENANT: tenant})
	t.insert(ignore_permissions=True)
	return t.name


def _close_tasks(tenant: str, dt: str, name: str, status: str = "Done") -> None:
	for t in frappe.get_all(TASK, filters={TENANT: tenant, "reference_doctype": dt, "reference_docname": name, "status": ["in", OPEN_TASK]},
							pluck="name"):
		frappe.db.set_value(TASK, t, "status", status)


# ---- the list ------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def overview(view: str = "todo", q: str = "") -> dict:
	"""The Leads tab: To do (due today, overdue, or new and not yet greeted), All open, Won — with the three counts."""
	tenant = _tenant()
	now = now_datetime()
	fields = ["name", "lead_name", "first_name", "last_name", "mobile_no", "email", "status", "source", "creation", "modified", "qtt_need"]
	leads = frappe.get_all(LEAD, filters={TENANT: tenant, "converted": 0}, fields=fields + ["organization"], limit=0)
	deals = frappe.get_all(DEAL, filters={TENANT: tenant}, fields=fields + ["organization_name as organization", "closed_date"], limit=0)
	tasks = _open_tasks(tenant)
	rows, counts = [], {"todo": 0, "all": 0, "won": 0}
	q = (q or "").strip().lower()
	for dt, items in ((LEAD, leads), (DEAL, deals)):
		for d in items:
			st = rules.stage(dt, d.status)
			task = tasks.get((dt, d.name))
			next_at = task["due"] if task else None
			todo = rules.on_todo(st, get_datetime(d.creation), next_at, now)
			counts["todo"] += todo
			counts["all"] += rules.is_open(st)
			counts["won"] += st == "Won"
			if (view == "todo" and not todo) or (view == "all" and not rules.is_open(st)) or (view == "won" and st != "Won"):
				continue
			name = _display(d)
			if q and q not in f"{name} {d.qtt_need or ''} {d.mobile_no or ''} {d.email or ''}".lower():
				continue
			line, overdue = rules.next_line(st, task["title"] if task else None, next_at, now, d.source)
			rows.append({"id": _id(dt, d.name), "name": name, "need": d.qtt_need, "stage": st, "line": line, "source": d.source,
						 "overdue": overdue, "due": str(next_at) if next_at else None, "phone": d.mobile_no,
						 "_sort": (0 if overdue else 1, next_at or datetime.max, -get_datetime(d.modified).timestamp())})
	rows.sort(key=lambda r: r["_sort"])  # overdue first, then the soonest step, then the latest change
	for r in rows:
		r.pop("_sort", None)
	return {"view": view, "counts": counts, "rows": rows[:200], "more": max(0, len(rows) - 200)}


# ---- one lead ------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def lead(id: str) -> dict:
	"""One lead: its stage, next step, what happened (newest first), the quote and how to reach them."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	return _lead_out(tenant, doc)


def _lead_out(tenant: str, doc) -> dict:
	now = now_datetime()
	dt = doc.doctype
	st = rules.stage(dt, doc.status)
	refs = [(dt, doc.name)] + ([(LEAD, doc.lead)] if dt == DEAL and doc.get("lead") else [])  # a deal shows its lead's notes too
	task = _open_tasks(tenant, [(dt, doc.name)]).get((dt, doc.name))
	notes = frappe.get_all(NOTE, filters={"reference_doctype": ["in", [r[0] for r in refs]], "reference_docname": ["in", [r[1] for r in refs]]},
						   fields=["title", "content", "creation", "owner"], order_by="creation desc", limit=30)
	line, overdue = rules.next_line(st, task["title"] if task else None, task["due"] if task else None, now, doc.get("source"))
	quote = None
	if dt == DEAL and doc.get("products"):
		quote = {"rows": [{"name": p.product_name, "qty": p.qty, "rate": p.rate, "amount": p.amount} for p in doc.products],
				 "total": doc.get("deal_value") or doc.get("net_total") or 0}
	value = doc.get("deal_value") if dt == DEAL else doc.get("annual_revenue")
	return {
		"id": _id(dt, doc.name), "name": _display(doc), "need": doc.get("qtt_need"), "stage": st, "status": doc.status,
		"phone": doc.get("mobile_no"), "email": doc.get("email"), "source": doc.get("source"), "value": value,
		"currency": _currency(tenant), "created": str(doc.creation),
		"next": {"task": task["name"], "title": task["title"], "due": str(task["due"]) if task["due"] else None, "overdue": overdue} if task else None,
		"line": line,
		"notes": [{"title": n.title, "text": frappe.utils.strip_html(n.content or ""), "at": str(n.creation),
				   "by": frappe.utils.get_fullname(n.owner)} for n in notes],
		"quote": quote, "lost_reason": doc.get("lost_reason") if dt == DEAL else None,
		"stages": list(rules.STAGES),
	}


# ---- changes -------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def add(data) -> dict:
	"""A new lead. Same phone or email as an open lead → that one opens instead (no duplicates)."""
	tenant = _tenant()
	data = json.loads(data) if isinstance(data, str) else (data or {})
	try:
		v = rules.clean_lead(data)
	except rules.LeadError as e:
		_err(e)
	for field in ("mobile_no", "email"):
		if v.get(field):
			same = frappe.db.get_value(LEAD, {TENANT: tenant, field: v[field], "converted": 0}, "name")
			if same:
				return {"id": _id(LEAD, same), "existing": True}
	doc = frappe.get_doc({"doctype": LEAD, TENANT: tenant, "status": "New", "lead_owner": frappe.session.user,
						  **{k: val for k, val in v.items() if val is not None}})
	doc.insert(ignore_permissions=True)
	if (data.get("note") or "").strip():
		_note(tenant, LEAD, doc.name, data["note"].strip())
	return {"id": _id(LEAD, doc.name), "existing": False}


@frappe.whitelist(methods=["POST"])
def note(id: str, text: str, kind: str = "Note") -> dict:
	"""What happened, in a line (a note, call, visit or WhatsApp). A New lead moves to Talking."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write what happened."))
	_note(tenant, doc.doctype, doc.name, text, kind if kind in ("Note", "Call", "Visit", "WhatsApp") else "Note")
	if doc.doctype == LEAD and doc.status == "New":
		doc.db_set("status", "Contacted")  # they've been talked to
	return _lead_out(tenant, frappe.get_doc(doc.doctype, doc.name))


@frappe.whitelist(methods=["POST"])
def remind(id: str, choice: str, day: str | None = None, title: str | None = None) -> dict:
	"""Remind me later: a task on this lead, due when chosen (it shows on To do that day)."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	try:
		at = rules.remind_at(choice, now_datetime(), get_datetime(day) if day else None)
	except rules.LeadError as e:
		_err(e)
	_close_tasks(tenant, doc.doctype, doc.name, "Canceled")  # one next step at a time
	_task(tenant, doc.doctype, doc.name, (title or "").strip() or "Follow up", at)
	return _lead_out(tenant, doc)


@frappe.whitelist(methods=["POST"])
def task_done(id: str) -> dict:
	"""The next step is done (its open tasks close)."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	_close_tasks(tenant, doc.doctype, doc.name, "Done")
	return _lead_out(tenant, doc)


@frappe.whitelist(methods=["POST"])
def set_stage(id: str, stage: str) -> dict:
	"""Move a lead between New and Talking (Quote sent, Won and Lost come from quote and close)."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	if doc.doctype != LEAD or stage not in ("New", "Talking"):
		frappe.throw(_("Send the quote, or choose Won or lost, to move it on."))
	doc.db_set("status", "New" if stage == "New" else "Contacted")
	return _lead_out(tenant, frappe.get_doc(LEAD, doc.name))


@frappe.whitelist(methods=["POST"])
def quote(id: str, lines, gst=0) -> dict:
	"""The quote: a CRM Deal with what they're buying (made from the lead the first time), and the short WhatsApp
	message that carries it. The app opens WhatsApp with it; a follow-up is set for two days later."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	lines = json.loads(lines) if isinstance(lines, str) else (lines or [])
	try:
		q = rules.clean_quote(lines, gst)
	except rules.LeadError as e:
		_err(e)
	products = [{"product_name": r["name"], "qty": r["qty"], "rate": r["rate"], "amount": r["amount"], "net_amount": r["amount"]} for r in q["rows"]]
	if doc.doctype == LEAD:
		deal = frappe.get_doc({"doctype": DEAL, TENANT: tenant, "lead": doc.name, "status": "Proposal/Quotation", "first_name": doc.first_name,
							   "last_name": doc.last_name, "lead_name": doc.lead_name, "mobile_no": doc.mobile_no, "email": doc.email,
							   "source": doc.source, "qtt_need": doc.get("qtt_need"), "organization_name": doc.organization,
							   "deal_owner": frappe.session.user, "currency": _currency(tenant)})
		deal.set("products", products)
		deal.deal_value = q["total"]
		deal.total = deal.net_total = q["net"]
		deal.insert(ignore_permissions=True)
		doc.db_set("converted", 1)
		_close_tasks(tenant, LEAD, doc.name, "Done")
	else:
		deal = doc
		if deal.status in ("Won", "Lost"):
			frappe.throw(_("This one is closed."))
		deal.set("products", products)
		deal.deal_value = q["total"]
		deal.total = deal.net_total = q["net"]
		deal.status = "Proposal/Quotation"
		deal.save(ignore_permissions=True)
		_close_tasks(tenant, DEAL, deal.name, "Done")
	currency = _currency(tenant)
	business = frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or ""
	message = rules.quote_message(_display(deal).split(" ")[0] or _display(deal), business, q, currency)
	_note(tenant, DEAL, deal.name, f"Quote · {rules.money(q['total'], currency)}", "Quote")
	follow_up = now_datetime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=2)
	_task(tenant, DEAL, deal.name, "Ask if the quote is OK", follow_up)
	out = _lead_out(tenant, frappe.get_doc(DEAL, deal.name))
	out["message"] = message
	return out


@frappe.whitelist(methods=["POST"])
def close(id: str, won, reason: str | None = None, notes: str | None = None) -> dict:
	"""Won: they join Customers (unless already there). Lost: why (Frappe CRM's lost reasons)."""
	tenant = _tenant()
	doc = _doc(tenant, id)
	won = str(won).lower() in ("1", "true", "yes")
	if not won and reason not in rules.LOST_REASONS:
		frappe.throw(_("Choose why it was lost."))
	if doc.doctype == LEAD:
		deal = frappe.get_doc({"doctype": DEAL, TENANT: tenant, "lead": doc.name, "first_name": doc.first_name, "last_name": doc.last_name,
							   "lead_name": doc.lead_name, "mobile_no": doc.mobile_no, "email": doc.email, "source": doc.source,
							   "qtt_need": doc.get("qtt_need"), "deal_owner": frappe.session.user, "currency": _currency(tenant),
							   "deal_value": doc.get("annual_revenue") or 0, "status": "Won" if won else "Lost"})
		deal.insert(ignore_permissions=True)
		doc.db_set("converted", 1)
		_close_tasks(tenant, LEAD, doc.name, "Canceled")
	else:
		deal = doc
		deal.status = "Won" if won else "Lost"
	if not won:
		lost = rules.LOST_REASONS[reason]
		deal.lost_reason = lost if frappe.db.exists("CRM Lost Reason", lost) else None
		deal.lost_notes = (notes or reason or "")[:1000]
	deal.closed_date = frappe.utils.today()
	deal.save(ignore_permissions=True)
	_close_tasks(tenant, DEAL, deal.name, "Done" if won else "Canceled")
	customer = _add_customer(tenant, deal) if won else None
	out = _lead_out(tenant, frappe.get_doc(DEAL, deal.name))
	out["customer"] = customer
	return out


def _add_customer(tenant: str, deal) -> str | None:
	"""A won lead joins the business's Customers (found by phone or email first)."""
	for field, value in (("phone", deal.mobile_no), ("email", deal.email)):
		if value:
			same = frappe.db.get_value(CUSTOMER, {"tenant": tenant, field: value}, "name")
			if same:
				return same
	name = _display(deal)
	if not name:
		return None
	values = {"doctype": CUSTOMER, "tenant": tenant, "customer_name": name[:140], "customer_type": "Individual", "kind": "Customer",
			  "phone": deal.mobile_no, "whatsapp": deal.mobile_no, "email": deal.email, "status": "Active"}
	meta = frappe.get_meta(CUSTOMER)
	src = meta.get_field("source")
	if src and src.fieldtype == "Select":
		opts = (src.options or "").split("\n")
		values["source"] = "Lead" if "Lead" in opts else ("Manual" if "Manual" in opts else None)
	try:
		doc = frappe.get_doc({k: v for k, v in values.items() if v is not None})
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(title="Leads: won lead not added to Customers")
		return None
