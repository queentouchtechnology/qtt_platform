"""/pay — pay one QTT invoice with Razorpay Checkout (link from the app; see billing/paylink.py)."""

import frappe

from qtt_platform.billing import paylink

no_cache = 1


def get_context(context):
	invoice = (frappe.form_dict.get("invoice") or "").strip()
	token = (frappe.form_dict.get("t") or "").strip()
	context.no_cache = 1
	context.title = "Payment"
	context.state = "invalid"
	if not paylink.verify(invoice, token) or not frappe.db.exists("QTT Invoice", invoice):
		return context
	inv = frappe.db.get_value("QTT Invoice", invoice, ["name", "tenant", "amount", "currency", "status", "due_date"], as_dict=True)
	context.invoice = inv
	context.business = frappe.db.get_value("QTT Tenant", inv.tenant, "tenant_name") or ""
	context.lines = frappe.get_all("QTT Invoice Item", filters={"parent": invoice, "parenttype": "QTT Invoice"},
								   fields=["description", "amount"], order_by="idx asc")
	if inv.status == "paid":
		context.state = "paid"
		return context
	if inv.status != "open":
		context.state = "closed"
		return context
	if not paylink.online_payments_on():
		context.state = "offline"
		return context
	try:
		order = paylink.checkout_payload(invoice)
	except Exception:
		frappe.log_error(title="qtt_platform /pay: could not create order")
		context.state = "error"
		return context
	owner = frappe.db.get_value("QTT Tenant", inv.tenant, "owner_user")
	context.state = "pay"
	context.checkout = frappe.as_json({
		**order,
		"name": "Queen Touch Technology",
		"description": f"Invoice {invoice}",
		"prefill": {"email": owner or "", "name": context.business},
		"notes": {"invoice": invoice},
	})
	return context
