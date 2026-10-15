"""
Apps billed by invoice (QTT Admin assigned them to a paying business; invoice_billing_rules has the
rules): the first invoice, paying it (doc_events: QTT Invoice on_update), and the daily renewal.
House workspaces (QTT's own) are never invoiced.
"""

import frappe
from frappe.utils import getdate, today

from qtt_platform import invoice_billing_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.billing import service as billing_service

SUB = "QTT Product Subscription"


def _plan(plan: str):
	return frappe.db.get_value("QTT Plan", plan, ["display_name", "plan_code", "base_price", "billing_period"], as_dict=True) or frappe._dict()


def _product_name(product: str) -> str:
	return frappe.db.get_value("QTT Product", product, "display_name") or product


def open_invoice(sub_name: str) -> str | None:
	parents = frappe.get_all("QTT Invoice Item", filters={"subscription": sub_name, "parenttype": "QTT Invoice"}, pluck="parent")
	found = frappe.get_all("QTT Invoice", filters={"name": ["in", parents or [""]], "status": "open"}, pluck="name", limit=1)
	return found[0] if found else None


def invoice_period(sub_name: str, start) -> str | None:
	"""An open invoice for one period of this subscription from `start` (None when it costs nothing)."""
	sub = frappe.get_doc(SUB, sub_name)
	plan = _plan(sub.plan)
	price = float(plan.base_price or 0)
	if price <= 0:
		return None
	months = rules.months_for(plan.billing_period)
	inv = billing_service.create_invoice(sub.tenant, [{"subscription": sub.name, **rules.line(_product_name(sub.product),
							plan.display_name or plan.plan_code or sub.plan, getdate(start), months, price)}], due_in_days=rules.DUE_DAYS)
	if not inv.get("currency"):
		frappe.db.set_value("QTT Invoice", inv.name, "currency", "INR", update_modified=False)
	billing_service.issue_invoice(inv.name)
	write_audit_event("invoice_issued", tenant=sub.tenant, product=sub.product, target_doctype="QTT Invoice", target_name=inv.name,
					  metadata={"subscription": sub.name, "amount": price})
	return inv.name


def on_invoice_update(doc, method=None) -> None:
	"""A paid invoice extends each invoice-billed app on it (and turns a suspended one back on)."""
	if doc.status != "paid" or not doc.has_value_changed("status"):
		return
	for sub_name in {i.subscription for i in doc.items if i.subscription}:
		sub = frappe.get_doc(SUB, sub_name)
		if sub.get("billing_mode") != "invoice":
			continue
		months = rules.months_for(_plan(sub.plan).billing_period)
		sub.paid_until = rules.paid_through(getdate(sub.paid_until) if sub.paid_until else None, getdate(today()), months)
		if sub.status in ("suspended", "past_due", "trialing"):
			sub.status = "active"  # paid: on (a paid trial is simply active now)
		if getdate(sub.current_period_end) < getdate(sub.paid_until):
			sub.current_period_end = sub.paid_until
		sub.save(ignore_permissions=True)


def renew_daily() -> None:
	"""Scheduler (daily): the next invoice before the paid time runs out; suspended when long unpaid."""
	from qtt_platform.house import is_house

	now = getdate(today())
	for s in frappe.get_all(SUB, filters={"billing_mode": "invoice", "status": ["in", ["trialing", "active", "past_due", "suspended"]]},
							fields=["name", "tenant", "product", "plan", "status", "paid_until", "cancel_at_period_end"]):
		if is_house(s.tenant):
			continue
		try:
			has_open = bool(open_invoice(s.name))
			step = rules.next_step(status=s.status, price=float(_plan(s.plan).base_price or 0),
								   paid_until=getdate(s.paid_until) if s.paid_until else None, has_open_invoice=has_open,
								   cancelling=bool(s.cancel_at_period_end), today=now)
			if step == "invoice":
				invoice_period(s.name, s.paid_until)
			elif step == "suspend":
				frappe.db.set_value(SUB, s.name, "status", "suspended")
				write_audit_event("subscription_suspended_unpaid", tenant=s.tenant, product=s.product, target_doctype=SUB, target_name=s.name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Invoice billing: renewal failed for {s.name}", message=frappe.get_traceback())
