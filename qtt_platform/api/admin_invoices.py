"""
QTT Admin › Invoices: every business's invoices and payments in one place. QTT Platform Owners only; every hand action
is written to the audit log with its reason.

  invoices(show, q, start)     all invoices, newest first, with totals (open, overdue, paid this month) and counts;
                               `show`: all | open | overdue | paid | void
  invoice(name)                one invoice: the business, its lines, payments and gateway attempts, and its history
  mark_paid(name, reason, reference)  paid outside the app (bank transfer, cash, UPI): a payment is recorded and the
                               invoice is paid exactly as an online payment would (its apps on / extended)
  void(name, reason)           an invoice that shouldn't be paid any more
  remind(name)                 the business owner gets "QTT · Payment reminder" (amount, due date, how to pay in the app)
  pdf(name)                    the invoice as a PDF in QTT's own look (downloaded)

Rules (pure): qtt_platform.invoice_billing_rules (shown_status, can).
"""

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, get_first_day, getdate, now_datetime, today

from qtt_platform import invoice_billing_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_platform_owner

INVOICE = "QTT Invoice"
PAYMENT = "QTT Payment"
TXN = "QTT Payment Transaction"
REMINDER = "QTT · Payment reminder"


def _names() -> dict[str, str]:
	return {t.name: t.tenant_name for t in frappe.get_all("QTT Tenant", fields=["name", "tenant_name"], limit=0)}


def _row(inv, names: dict, paid_at: dict, now) -> dict:
	shown = rules.shown_status(inv.status, getdate(inv.due_date) if inv.due_date else None, now)
	return {
		"name": inv.name,
		"tenant": inv.tenant,
		"business": names.get(inv.tenant, inv.tenant),
		"amount": inv.amount or 0,
		"currency": inv.currency or "INR",
		"status": shown,
		"due_date": inv.due_date,
		"days_late": rules.days_late(getdate(inv.due_date), now) if shown == "overdue" else 0,
		"paid_at": paid_at.get(inv.name),
		"created": inv.creation,
	}


@frappe.whitelist(methods=["GET"])
def invoices(show: str | None = "all", q: str | None = None, start: int = 0) -> dict:
	"""QTT Admin › Invoices: all invoices (newest first) with totals — open, overdue and collected this month — and
	how many in each status."""
	require_platform_owner()
	now = getdate(today())
	names = _names()
	rows = frappe.get_all(INVOICE, fields=["name", "tenant", "amount", "currency", "status", "due_date", "creation"], order_by="creation desc",
						  limit=0)
	paid_at = {p.invoice: p.paid_at for p in frappe.get_all(PAYMENT, filters={"status": "succeeded"}, fields=["invoice", "paid_at"], limit=0)}
	all_rows = [_row(r, names, paid_at, now) for r in rows]
	text = (q or "").strip().lower()
	if text:
		all_rows = [r for r in all_rows if text in f"{r['name']} {r['business']}".lower()]
	counts = {s: 0 for s in ("all",) + rules.SHOWN}
	totals = {"open": 0.0, "overdue": 0.0, "collected_month": 0.0}
	month = get_first_day(now)
	for r in all_rows:
		counts["all"] += 1
		counts[r["status"]] = counts.get(r["status"], 0) + 1
		if r["status"] in ("open", "overdue"):
			totals["open"] += float(r["amount"])
		if r["status"] == "overdue":
			totals["overdue"] += float(r["amount"])
		if r["status"] == "paid" and r["paid_at"] and getdate(r["paid_at"]) >= month:
			totals["collected_month"] += float(r["amount"])
	show = show if show in counts else "all"
	shown = all_rows if show == "all" else [r for r in all_rows if r["status"] == show]
	start = max(0, int(start or 0))
	return {"invoices": shown[start:start + 100], "total": len(shown), "counts": counts, "totals": totals, "currency": "INR"}


def _get(name: str):
	if not frappe.db.exists(INVOICE, name):
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	return frappe.get_doc(INVOICE, name)


@frappe.whitelist(methods=["GET"])
def invoice(name: str) -> dict:
	"""QTT Admin › Invoices › one invoice: business and owner, its lines, payments, gateway attempts and history, and
	which hand actions it allows."""
	require_platform_owner()
	inv = _get(name)
	now = getdate(today())
	t = frappe.db.get_value("QTT Tenant", inv.tenant, ["tenant_name", "owner_user"], as_dict=True) or frappe._dict()
	payments = frappe.get_all(PAYMENT, filters={"invoice": name}, fields=["name", "amount", "currency", "status", "paid_at"], order_by="creation")
	txns = frappe.get_all(TXN, filters={"invoice": name}, fields=["gateway", "gateway_reference", "status", "creation"], order_by="creation")
	history = frappe.get_all("QTT Audit Log", filters={"target_doctype": INVOICE, "target_name": name},
							 fields=["event_type", "actor", "occurred_at", "metadata"], order_by="occurred_at desc", limit=20) \
		if frappe.db.table_exists("QTT Audit Log") else []
	shown = rules.shown_status(inv.status, getdate(inv.due_date) if inv.due_date else None, now)
	return {
		"name": inv.name,
		"tenant": inv.tenant,
		"business": t.tenant_name or inv.tenant,
		"owner": t.owner_user,
		"amount": inv.amount or 0,
		"currency": inv.currency or "INR",
		"status": shown,
		"due_date": inv.due_date,
		"days_late": rules.days_late(getdate(inv.due_date), now) if shown == "overdue" else 0,
		"created": inv.creation,
		"lines": [{"description": i.description, "amount": i.amount, "subscription": i.subscription} for i in inv.items],
		"payments": payments,
		"attempts": txns,
		"history": history,
		"can": {a: rules.can(a, shown) for a in ("mark_paid", "remind", "void")},
	}


def _need(action: str, inv) -> str:
	shown = rules.shown_status(inv.status, getdate(inv.due_date) if inv.due_date else None, getdate(today()))
	if not rules.can(action, shown):
		frappe.throw(_("This invoice is {0} — that can't be done now.").format(_(shown)))
	return shown


def _reason(reason: str | None) -> str:
	reason = " ".join(str(reason or "").split())[:500]
	if len(reason) < 3:
		frappe.throw(_("Say why (it's kept in the history)."))
	return reason


@frappe.whitelist(methods=["POST"])
def mark_paid(name: str, reason: str, reference: str | None = None) -> dict:
	"""Paid outside the app (bank transfer, cash, UPI): a payment is recorded and the invoice is paid as an online
	payment would be — its apps switch on or are extended. `reason` goes into the history."""
	require_platform_owner()
	inv = _get(name)
	_need("mark_paid", inv)
	why = _reason(reason)
	ref = " ".join(str(reference or "").split())[:140] or None
	from qtt_platform.billing.service import _mark_invoice_paid_and_activate_subscriptions

	payment = frappe.get_doc({"doctype": PAYMENT, "invoice": inv.name, "amount": inv.amount, "currency": inv.currency, "status": "succeeded",
							  "paid_at": now_datetime()}).insert(ignore_permissions=True)
	if inv.status != "open":  # a draft paid by hand: it is due first, then paid
		frappe.db.set_value(INVOICE, inv.name, "status", "open")
	_mark_invoice_paid_and_activate_subscriptions(inv.name)
	write_audit_event("invoice.marked_paid", target_doctype=INVOICE, target_name=inv.name, tenant=inv.tenant,
					  metadata={"reason": why, "reference": ref, "payment": payment.name, "amount": inv.amount})
	return invoice(inv.name)


@frappe.whitelist(methods=["POST"])
def void(name: str, reason: str) -> dict:
	"""An invoice that shouldn't be paid any more (wrong amount, given free…): void, with the reason in its history."""
	require_platform_owner()
	inv = _get(name)
	_need("void", inv)
	why = _reason(reason)
	frappe.db.set_value(INVOICE, inv.name, "status", "void")
	write_audit_event("invoice.voided", target_doctype=INVOICE, target_name=inv.name, tenant=inv.tenant, metadata={"reason": why})
	return invoice(inv.name)


@frappe.whitelist(methods=["POST"])
def remind(name: str) -> dict:
	"""The business owner gets "QTT · Payment reminder": the amount, the due date and where to pay in the app."""
	require_platform_owner()
	from qtt_platform import emails

	inv = _get(name)
	shown = _need("remind", inv)
	t = frappe.db.get_value("QTT Tenant", inv.tenant, ["tenant_name", "owner_user"], as_dict=True) or frappe._dict()
	if not t.owner_user:
		frappe.throw(_("This business has no owner to remind."))
	from qtt_platform.leads_rules import money

	emails.send(REMINDER, [t.owner_user], {
		"business": t.tenant_name, "invoice": inv.name, "amount": money(inv.amount or 0, inv.currency or "INR"),
		"due": formatdate(inv.due_date, "d MMM yyyy") if inv.due_date else "", "overdue": shown == "overdue",
		"days_late": rules.days_late(getdate(inv.due_date), getdate(today())) if inv.due_date else 0,
		"lines": [i.description for i in inv.items if i.description],
		"preheader": f"{inv.name} for {t.tenant_name}",
	}, now=True)
	write_audit_event("invoice.reminded", target_doctype=INVOICE, target_name=inv.name, tenant=inv.tenant, metadata={"to": t.owner_user})
	return {"sent_to": t.owner_user}


_PDF_HTML = """
<div style="font-family: Helvetica, Arial, sans-serif; color: #1E293B; font-size: 12px; padding: 8px 4px">
  <table style="width: 100%; border-collapse: collapse"><tr>
    <td style="vertical-align: top">
      {% if logo %}<img src="{{ logo }}" style="max-height: 56px; max-width: 180px; margin-bottom: 6px"><br>{% endif %}
      <div style="font-size: 18px; font-weight: bold; color: {{ b.color }}">{{ b.name }}</div>
      {% for line in b.address %}<div style="color: #64748B">{{ line }}</div>{% endfor %}
      {% if b.gstin %}<div style="color: #64748B">GSTIN {{ b.gstin }}</div>{% endif %}
      <div style="color: #64748B">{{ [b.phone, b.email, b.website] | select | join(" · ") }}</div>
    </td>
    <td style="vertical-align: top; text-align: right">
      <div style="font-size: 22px; font-weight: bold; color: {{ b.color }}">INVOICE</div>
      <div style="color: #64748B">{{ inv.name }}</div>
      <div style="color: #64748B">{{ date }}</div>
      {% if due %}<div style="color: #64748B">Due {{ due }}</div>{% endif %}
      <div style="margin-top: 6px; font-weight: bold; color: {{ status_color }}">{{ status }}</div>
    </td>
  </tr></table>
  <div style="margin: 18px 0 10px; padding: 10px 12px; background: #F5F8FF; border-radius: 6px">
    <div style="color: #64748B; font-size: 11px">BILL TO</div>
    <div style="font-size: 14px; font-weight: bold">{{ to.name }}</div>
    {% for line in to.address %}<div style="color: #64748B">{{ line }}</div>{% endfor %}
    {% if to.gstin %}<div style="color: #64748B">GSTIN {{ to.gstin }}</div>{% endif %}
  </div>
  <table style="width: 100%; border-collapse: collapse">
    <tr style="background: {{ b.color }}; color: #FFFFFF">
      <th style="text-align: left; padding: 8px">#</th><th style="text-align: left; padding: 8px">Description</th>
      <th style="text-align: right; padding: 8px">Amount</th>
    </tr>
    {% for r in lines %}
    <tr style="border-bottom: 1px solid #E5E7EB">
      <td style="padding: 8px">{{ loop.index }}</td><td style="padding: 8px">{{ r.description }}</td>
      <td style="padding: 8px; text-align: right">{{ r.amount_text }}</td>
    </tr>
    {% endfor %}
  </table>
  <table style="width: 46%; margin-left: 54%; margin-top: 10px; border-collapse: collapse">
    <tr><td style="padding: 8px; font-weight: bold; border-top: 2px solid {{ b.color }}">Total</td>
        <td style="padding: 8px; text-align: right; font-weight: bold; font-size: 15px; border-top: 2px solid {{ b.color }}">{{ total }}</td></tr>
  </table>
  {% if paid %}<div style="margin-top: 18px; color: #15803D">Paid {{ paid }} — thank you.</div>
  {% else %}<div style="margin-top: 18px; color: #64748B">Pay in QTT OS › Business › Plans and billing.</div>{% endif %}
  <div style="margin-top: 28px; color: #64748B">Thank you — {{ b.name }}</div>
</div>
"""


@frappe.whitelist(methods=["GET"])
def pdf(name: str):
	"""The invoice as a PDF in QTT's own look (logo, address, GSTIN), with the business it's for — downloaded."""
	require_platform_owner()
	from frappe.utils import get_url
	from frappe.utils.pdf import get_pdf

	from qtt_platform.api.leads import house_tenant
	from qtt_platform.leads_rules import money
	from qtt_platform.print_brand import brand

	d = invoice(name)
	b = brand(tenant=house_tenant())
	to = brand(tenant=d["tenant"])
	logo = b.logo if not b.logo or str(b.logo).startswith("http") else get_url(b.logo)
	paid = next((p for p in d["payments"] if p.status == "succeeded"), None)
	cur = d["currency"]
	html = frappe.render_template(_PDF_HTML, {
		"b": b, "logo": logo, "inv": frappe._dict(d), "to": {"name": d["business"], "address": to.address, "gstin": to.gstin},
		"date": formatdate(d["created"], "d MMM yyyy"), "due": formatdate(d["due_date"], "d MMM yyyy") if d["due_date"] else "",
		"status": {"paid": "PAID", "overdue": "OVERDUE", "void": "VOID"}.get(d["status"], "DUE"),
		"status_color": {"paid": "#15803D", "overdue": "#B91C1C", "void": "#64748B"}.get(d["status"], "#1E293B"),
		"lines": [{**ln, "amount_text": money(ln["amount"] or 0, cur)} for ln in d["lines"]], "total": money(d["amount"], cur),
		"paid": formatdate(paid.paid_at, "d MMM yyyy") if paid else None,
	})
	frappe.local.response.filename = f"{name}.pdf"
	frappe.local.response.filecontent = get_pdf(html, {"page-size": "A4", "margin-top": "12mm", "margin-bottom": "12mm", "margin-left": "12mm",
														"margin-right": "12mm"})
	frappe.local.response.type = "pdf"
