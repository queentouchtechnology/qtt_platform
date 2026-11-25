"""
QTT's invoice to a business as a PDF, in QTT's own look (qtt_look: the print format "QTT Proposal") with the business it's for. The same PDF in
QTT Admin › Invoices (api.admin_invoices.pdf) and in the business's own Plans and billing (api.billing.invoice_pdf).
Whoever calls this has checked who may see the invoice.
"""

import frappe
from frappe.utils import formatdate, getdate, today

from qtt_platform import invoice_billing_rules as rules


def render(name: str) -> bytes:
	from qtt_platform import qtt_look
	from qtt_platform.leads_rules import money
	from qtt_platform.print_brand import brand

	inv = frappe.get_doc("QTT Invoice", name)
	to = brand(tenant=inv.tenant)
	cur = inv.currency or "INR"
	status = rules.shown_status(inv.status, getdate(inv.due_date) if inv.due_date else None, getdate(today()))
	paid_at = frappe.db.get_value("QTT Payment", {"invoice": name, "status": "succeeded"}, "paid_at", order_by="creation")
	due = formatdate(inv.due_date, "d MMMM yyyy") if inv.due_date else ""
	if status == "paid":
		right, note = "Paid" + (f" {formatdate(paid_at, 'd MMMM yyyy')}" if paid_at else ""), "Paid — thank you."
	elif status == "void":
		right, note = "Cancelled", "This invoice was cancelled. Nothing to pay."
	else:
		right, note = (f"{'Was due' if status == 'overdue' else 'Due'}: {due}" if due else "To pay"), "Pay in QTT OS › Business › Plans and billing."
	return qtt_look.render(
		title="QTT OS — Invoice", left=f"Date: {formatdate(inv.creation, 'd MMMM yyyy')}  ·  Invoice No: {inv.name}", right=right,
		color={"paid": "#15803D", "overdue": "#B91C1C", "void": "#64748B"}.get(status, ""),
		to_label="Bill to", to=[frappe.db.get_value("QTT Tenant", inv.tenant, "tenant_name") or inv.tenant, ", ".join(to.address),
								f"GSTIN {to.gstin}" if to.gstin else ""],
		columns=["Description", "Amount"], rows=[[r.description or "", money(r.amount or 0, cur)] for r in inv.items],
		totals=[("Total", money(inv.amount or 0, cur), True)], note=note)


def respond(name: str) -> None:
	frappe.local.response.filename = f"{name}.pdf"
	frappe.local.response.filecontent = render(name)
	frappe.local.response.type = "pdf"
