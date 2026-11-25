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
				 "total": doc.get("deal_value") or doc.get("net_total") or 0, "pdf_url": _latest_pdf(doc.name)}
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
	same = _open_by_contact(tenant, v.get("mobile_no"), v.get("email"))
	if same:
		return {"id": _id(*same), "existing": True}
	doc = frappe.get_doc({"doctype": LEAD, TENANT: tenant, "status": "New", "lead_owner": frappe.session.user,
						  **{k: val for k, val in v.items() if val is not None}})
	doc.insert(ignore_permissions=True)
	if (data.get("note") or "").strip():
		_note(tenant, LEAD, doc.name, data["note"].strip())
	following = _start_follow_up(tenant, doc, source="Content Hub")
	return {"id": _id(LEAD, doc.name), "existing": False, "following": following}


def _start_follow_up(tenant: str, doc, *, source: str, message: str | None = None) -> bool:
	"""Lead follow-up (AI & WhatsApp automation), when the business has it on: answered at once on WhatsApp, then days 1,
	3 and 7 until they reply. Noted on the lead."""
	if not doc.get("mobile_no"):
		return False
	try:
		from qtt_services.api.automations import follow_up
	except ImportError:
		return False
	try:
		sent = follow_up(tenant, name=_display(doc), phone=doc.mobile_no, email=doc.get("email"), about=doc.get("qtt_need"), message=message,
						 source=source)
	except Exception:
		frappe.log_error(title="Leads: follow-up not started")
		return False
	if sent:
		_note(tenant, LEAD, doc.name, "Answered on WhatsApp — follow-ups on days 1, 3 and 7 until they reply.", "WhatsApp")
	return sent


def from_enquiry(tenant: str, data: dict) -> str | None:
	"""A website enquiry (store hooks) is a lead in the Content Hub too — the same phone or email adds a note to the open
	one instead. Lead follow-up itself starts in qtt_services (on_enquiry)."""
	name = " ".join(str(data.get("name") or "").split())[:140]
	try:
		phone = rules.clean_phone(data.get("phone"))
	except rules.LeadError:
		phone = None
	try:
		email = rules.clean_email(data.get("email"))
	except rules.LeadError:
		email = None
	if not (phone or email):
		return None
	text = " ".join(x for x in (str(data.get("choice") or "").strip(), str(data.get("message") or "").strip()) if x)[:2000]
	same = _open_by_contact(tenant, phone, email)
	if same:
		if text:
			_note(tenant, same[0], same[1], text, "Website")
		return same[1]
	first, _sep, last = (name or phone or email).partition(" ")
	doc = frappe.get_doc({"doctype": LEAD, TENANT: tenant, "status": "New", "first_name": first, "last_name": last or None, "mobile_no": phone,
						  "email": email, "source": "Website Form", "qtt_need": str(data.get("choice") or "").strip()[:140] or None})
	doc.insert(ignore_permissions=True)
	if text:
		_note(tenant, LEAD, doc.name, text, "Website")
	return doc.name


def _open_by_contact(tenant: str, phone: str | None, email: str | None) -> tuple[str, str] | None:
	"""The open lead or deal with this phone (last 10 digits) or email."""
	key = rules.phone_key(phone)
	for dt, extra in ((LEAD, {"converted": 0}), (DEAL, {"status": ["not in", ["Won", "Lost"]]})):
		for r in frappe.get_all(dt, filters={TENANT: tenant, **extra}, fields=["name", "mobile_no", "email"], order_by="modified desc", limit=0):
			if (key and rules.phone_key(r.mobile_no) == key) or (email and (r.email or "").lower() == email):
				return dt, r.name
	return None


def on_reply(tenant: str, phone: str, message: str | None) -> None:
	"""Lead follow-up: the customer replied on WhatsApp — the lead moves to Talking with what they said, and its next step
	is to reply to them."""
	same = _open_by_contact(tenant, phone, None)
	if not same:
		return
	dt, name = same
	_note(tenant, dt, name, (message or "").strip()[:2000] or "Replied", "WhatsApp")
	if dt == LEAD and frappe.db.get_value(LEAD, name, "status") == "New":
		frappe.db.set_value(LEAD, name, "status", "Contacted")
	_close_tasks(tenant, dt, name, "Canceled")
	_task(tenant, dt, name, "Reply to them — they answered on WhatsApp", now_datetime())


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
	pdf_url = None
	try:
		pdf_url = _quote_pdf(tenant, deal, q, currency)
	except Exception:
		frappe.log_error(title="Leads: quote PDF failed")  # the message still goes, without the link
	message = rules.quote_message(_display(deal).split(" ")[0] or _display(deal), business, q, currency, pdf_url=pdf_url)
	_note(tenant, DEAL, deal.name, f"Quote · {rules.money(q['total'], currency)}", "Quote")
	follow_up = now_datetime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=2)
	_task(tenant, DEAL, deal.name, "Ask if the quote is OK", follow_up)
	out = _lead_out(tenant, frappe.get_doc(DEAL, deal.name))
	out["message"] = message
	out["pdf_url"] = pdf_url
	return out


_QUOTE_HTML = """
<div style="font-family: Helvetica, Arial, sans-serif; color: #1E293B; font-size: 12px; padding: 8px 4px">
  <table style="width: 100%; border-collapse: collapse"><tr>
    <td style="vertical-align: top">
      {% if b.logo %}<img src="{{ logo }}" style="max-height: 56px; max-width: 180px; margin-bottom: 6px"><br>{% endif %}
      <div style="font-size: 18px; font-weight: bold; color: {{ b.color }}">{{ b.name }}</div>
      {% if b.tagline %}<div style="color: #64748B">{{ b.tagline }}</div>{% endif %}
      {% for line in b.address %}<div style="color: #64748B">{{ line }}</div>{% endfor %}
      {% if b.gstin %}<div style="color: #64748B">GSTIN {{ b.gstin }}</div>{% endif %}
      <div style="color: #64748B">{{ [b.phone, b.email, b.website] | select | join(" · ") }}</div>
    </td>
    <td style="vertical-align: top; text-align: right">
      <div style="font-size: 22px; font-weight: bold; color: {{ b.color }}">QUOTATION</div>
      <div style="color: #64748B">{{ number }}</div>
      <div style="color: #64748B">{{ date }}</div>
      <div style="color: #64748B">Valid for 15 days</div>
    </td>
  </tr></table>
  <div style="margin: 18px 0 10px; padding: 10px 12px; background: #F5F8FF; border-radius: 6px">
    <div style="color: #64748B; font-size: 11px">FOR</div>
    <div style="font-size: 14px; font-weight: bold">{{ customer }}</div>
    {% if phone %}<div style="color: #64748B">{{ phone }}</div>{% endif %}
  </div>
  <table style="width: 100%; border-collapse: collapse">
    <tr style="background: {{ b.color }}; color: #FFFFFF">
      <th style="text-align: left; padding: 8px">#</th><th style="text-align: left; padding: 8px">Item</th>
      <th style="text-align: right; padding: 8px">Qty</th><th style="text-align: right; padding: 8px">Price</th>
      <th style="text-align: right; padding: 8px">Amount</th>
    </tr>
    {% for r in q.rows %}
    <tr style="border-bottom: 1px solid #E5E7EB">
      <td style="padding: 8px">{{ loop.index }}</td><td style="padding: 8px">{{ r.name }}</td>
      <td style="padding: 8px; text-align: right">{{ r.qty_text }}</td><td style="padding: 8px; text-align: right">{{ r.rate_text }}</td>
      <td style="padding: 8px; text-align: right">{{ r.amount_text }}</td>
    </tr>
    {% endfor %}
  </table>
  <table style="width: 46%; margin-left: 54%; margin-top: 10px; border-collapse: collapse">
    <tr><td style="padding: 5px 8px; color: #64748B">Subtotal</td><td style="padding: 5px 8px; text-align: right">{{ net }}</td></tr>
    {% if q.tax %}<tr><td style="padding: 5px 8px; color: #64748B">GST {{ gst }}%</td><td style="padding: 5px 8px; text-align: right">{{ tax }}</td></tr>{% endif %}
    <tr><td style="padding: 8px; font-weight: bold; border-top: 2px solid {{ b.color }}">Total</td>
        <td style="padding: 8px; text-align: right; font-weight: bold; font-size: 15px; border-top: 2px solid {{ b.color }}">{{ total }}</td></tr>
  </table>
  {% if b.bank.number or b.bank.upi %}
  <div style="margin-top: 22px; color: #64748B">
    <div style="font-weight: bold; color: #1E293B">Payment</div>
    {% if b.bank.number %}<div>{{ b.bank.account_name or b.name }} · {{ b.bank.bank }} · A/c {{ b.bank.number }}{% if b.bank.ifsc %} · IFSC {{ b.bank.ifsc }}{% endif %}</div>{% endif %}
    {% if b.bank.upi %}<div>UPI {{ b.bank.upi }}</div>{% endif %}
  </div>
  {% endif %}
  <div style="margin-top: 28px; color: #64748B">Thank you — {{ b.name }}{% if b.footer %}<br>{{ b.footer }}{% endif %}</div>
</div>
"""


def _quote_pdf(tenant: str, deal, q: dict, currency: str) -> str:
	"""The quote as a PDF in the business's own look (Business profile: logo, colour, address, GSTIN, bank), saved on the
	deal as a public file with an unguessable name (the customer opens it from WhatsApp). The deal's older quote PDFs go."""
	from frappe.utils import get_url
	from frappe.utils.pdf import get_pdf

	from qtt_platform.print_brand import brand

	b = brand(tenant=tenant)

	def qty(v):
		return str(int(v)) if float(v).is_integer() else str(v)

	rows = [{**r, "qty_text": qty(r["qty"]), "rate_text": rules.money(r["rate"], currency), "amount_text": rules.money(r["amount"], currency)}
			for r in q["rows"]]
	from qtt_platform import qtt_look

	if qtt_look.is_qtt(tenant):  # QTT's own quotes: the look of the print format "QTT Proposal"
		pdf = qtt_look.render(
			title="Quotation", left=f"Date: {frappe.utils.formatdate(frappe.utils.today(), 'd MMMM yyyy')}  ·  Quotation No: {deal.name.replace('CRM-DEAL-', 'Q-')}",
			right="Quotation Validity: 15 days", to_label="Prepared for", to=[_display(deal), deal.mobile_no],
			columns=["Service", "Qty", "Price", "Amount"], rows=[[r["name"], r["qty_text"], r["rate_text"], r["amount_text"]] for r in rows],
			totals=[("Subtotal", rules.money(q["net"], currency), False)]
			+ ([(f"GST {qty(q['gst'])}%", rules.money(q["tax"], currency), False)] if q["tax"] else []) + [("Total", rules.money(q["total"], currency), True)])
		return _save_quote(deal, pdf)
	logo = b.logo if not b.logo or b.logo.startswith("http") else get_url(b.logo)
	html = frappe.render_template(_QUOTE_HTML, {
		"b": b, "logo": logo, "q": {**q, "rows": rows}, "number": deal.name.replace("CRM-DEAL-", "Q-"),
		"date": frappe.utils.formatdate(frappe.utils.today(), "d MMM yyyy"), "customer": _display(deal), "phone": deal.mobile_no,
		"net": rules.money(q["net"], currency), "tax": rules.money(q["tax"], currency), "total": rules.money(q["total"], currency),
		"gst": qty(q["gst"]),
	})
	return _save_quote(deal, get_pdf(html, {"page-size": "A4", "margin-top": "12mm", "margin-bottom": "12mm", "margin-left": "12mm", "margin-right": "12mm"}))


def _save_quote(deal, pdf: bytes) -> str:
	from frappe.utils import get_url

	for old in frappe.get_all("File", filters={"attached_to_doctype": DEAL, "attached_to_name": deal.name, "file_name": ["like", "Quote-%"]},
							  pluck="name"):
		frappe.delete_doc("File", old, ignore_permissions=True, force=True)
	f = frappe.get_doc({"doctype": "File", "file_name": f"Quote-{frappe.generate_hash(length=12)}.pdf", "content": pdf, "is_private": 0,
						"attached_to_doctype": DEAL, "attached_to_name": deal.name})
	f.insert(ignore_permissions=True)
	return get_url(f.file_url)


def _latest_pdf(deal: str) -> str | None:
	from frappe.utils import get_url

	url = frappe.db.get_value("File", {"attached_to_doctype": DEAL, "attached_to_name": deal, "file_name": ["like", "Quote-%"]}, "file_url",
							  order_by="creation desc")
	return get_url(url) if url else None


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
