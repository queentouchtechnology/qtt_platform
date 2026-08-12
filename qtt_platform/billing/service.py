"""
Invoice/payment lifecycle — the only code path that creates or transitions
a QTT Invoice/QTT Payment/QTT Payment Transaction. Every write uses
ignore_permissions=True, matching the same billing-immutability pattern as
subscription/service.py: no tenant-facing role holds DocPerm on any of
these doctypes.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime, today

from qtt_platform.audit import write_audit_event
from qtt_platform.billing.gateways.registry import get_gateway


def create_invoice(tenant: str, items: list[dict], *, due_in_days: int = 7) -> "frappe.model.document.Document":
	"""items: [{"subscription": <name>, "description": <str>, "amount": <float>}, ...]
	Created in `draft` status — call issue_invoice() to move it to `open`
	before a payment can be collected against it."""
	total = sum(item["amount"] for item in items)
	invoice = frappe.get_doc(
		{
			"doctype": "QTT Invoice",
			"tenant": tenant,
			"amount": total,
			"status": "draft",
			"due_date": add_days(today(), due_in_days),
			"items": items,
		}
	)
	invoice.insert(ignore_permissions=True)
	return invoice


def issue_invoice(invoice_name: str) -> None:
	frappe.db.set_value("QTT Invoice", invoice_name, "status", "open")


def create_payment_order(invoice_name: str, *, gateway_key: str = "razorpay") -> dict:
	"""Reads amount/currency from the QTT Invoice itself — never from a
	request parameter. This is the concrete fix for the hardening review
	section 10's "no client-controlled amount" requirement: there is no
	code path anywhere in this module that accepts an amount from a
	caller for a real charge."""
	invoice = frappe.get_doc("QTT Invoice", invoice_name)
	if invoice.status not in ("open",):
		frappe.throw(_("Cannot create a payment order for an invoice that isn't open."))

	gateway = get_gateway(gateway_key)
	if not gateway.is_configured():
		frappe.throw(_("Payment gateway '{0}' is not configured.").format(gateway_key))

	order = gateway.create_order(invoice_name=invoice_name, amount=invoice.amount, currency=invoice.currency)

	frappe.get_doc(
		{
			"doctype": "QTT Payment Transaction",
			"invoice": invoice_name,
			"gateway": gateway_key,
			"gateway_reference": order.gateway_order_id,
			"status": "created",
		}
	).insert(ignore_permissions=True)

	return order.client_payload


def process_webhook(gateway_key: str, payload_body: bytes, signature: str) -> dict:
	"""The one entry point for inbound gateway webhooks. Verifies the
	signature BEFORE reading a single field of the payload (hardening
	review section 10) — an invalid signature is rejected outright, no
	processing, no state change, no exception detail leaked back to the
	caller beyond a generic rejection.
	"""
	gateway = get_gateway(gateway_key)

	if not gateway.verify_webhook_signature(payload_body, signature):
		_audit_webhook_rejected(gateway_key)
		frappe.throw(_("Invalid webhook signature."), frappe.PermissionError)

	event = gateway.parse_webhook_event(payload_body)

	# Idempotency: a redelivered webhook for a transaction we've already
	# recorded as succeeded is a safe no-op — checked before any write.
	existing_transaction = frappe.db.get_value(
		"QTT Payment Transaction", {"gateway_reference": event.gateway_reference}, ["name", "status"], as_dict=True
	)

	if existing_transaction and existing_transaction.status == "succeeded":
		return {"ok": True, "already_processed": True}

	if not existing_transaction:
		# A webhook arriving for a reference we never created an order for
		# is unusual (not necessarily malicious — could be a manual test
		# payment) but must still resolve to a real invoice via the
		# gateway's own reference, never trust a tenant/invoice id if the
		# payload happened to include one.
		frappe.throw(_("No matching payment transaction for this webhook."), frappe.ValidationError)

	transaction = frappe.get_doc("QTT Payment Transaction", existing_transaction.name)
	transaction.status = "succeeded"
	transaction.raw_payload = json.dumps(event.raw_payload)
	transaction.save(ignore_permissions=True)

	payment = frappe.get_doc(
		{
			"doctype": "QTT Payment",
			"invoice": transaction.invoice,
			"amount": event.amount,
			"currency": event.currency,
			"status": "succeeded",
			"paid_at": now_datetime(),
		}
	)
	payment.insert(ignore_permissions=True)

	transaction.payment = payment.name
	transaction.save(ignore_permissions=True)

	_mark_invoice_paid_and_activate_subscriptions(transaction.invoice)

	return {"ok": True}


def _mark_invoice_paid_and_activate_subscriptions(invoice_name: str) -> None:
	invoice = frappe.get_doc("QTT Invoice", invoice_name)
	# State-transition validation (hardening review section 10) — a stale
	# or duplicate webhook cannot un-void or re-pay an invoice that isn't
	# currently open.
	if invoice.status != "open":
		return
	invoice.status = "paid"
	invoice.save(ignore_permissions=True)
	write_audit_event(
		"payment_received", tenant=invoice.tenant, target_doctype="QTT Invoice", target_name=invoice.name
	)
	# Activating/renewing the subscription(s) this invoice covers is
	# deliberately left to whatever created the invoice in the first place
	# (api/subscription.py's subscribe()/change_plan() already activate a
	# subscription at creation time, independent of payment) — this
	# function's job ends at "the invoice is paid," matching the narrow
	# scope of what a webhook should decide.


def refund_payment(payment_name: str, amount: float, *, reference: str | None = None) -> "frappe.model.document.Document":
	"""Creates a NEW QTT Payment row — the original is never mutated, per
	the hardening review section 11's append-only classification.
	Idempotent per original payment: a payment can only be refunded once
	in this simple model (no partial-refund tracking) — a second call
	against an already-refunded payment returns the existing refund
	rather than creating a duplicate."""
	original = frappe.get_doc("QTT Payment", payment_name)
	if original.status != "succeeded":
		frappe.throw(_("Can only refund a succeeded payment."))

	existing_refund_name = frappe.db.exists("QTT Payment", {"refund_of": original.name})
	if existing_refund_name:
		return frappe.get_doc("QTT Payment", existing_refund_name)

	refund = frappe.get_doc(
		{
			"doctype": "QTT Payment",
			"invoice": original.invoice,
			"amount": amount,
			"currency": original.currency,
			"status": "refunded",
			"paid_at": now_datetime(),
			"refund_of": original.name,
		}
	)
	refund.insert(ignore_permissions=True)

	tenant = frappe.db.get_value("QTT Invoice", original.invoice, "tenant")
	write_audit_event(
		"payment_refunded",
		tenant=tenant,
		target_doctype="QTT Payment",
		target_name=refund.name,
		metadata={"original_payment": original.name, "amount": amount, "reference": reference},
	)
	return refund


def reconcile_payments() -> list[dict]:
	"""The recoverable-state mechanism from the hardening review section
	24: scans for QTT Payment(status=succeeded) whose invoice is not
	marked paid (the rare case where the payment write succeeded but the
	invoice-status write that should accompany it didn't — normally
	impossible given both happen in one Frappe request transaction, but
	this is the safety net for whatever edge case defeats that). Not
	registered as a scheduled job yet — same open scheduler_events
	convention gap noted in Phase 8's reconcile_wallet()."""
	corrections = []
	succeeded_payments = frappe.get_all(
		"QTT Payment", filters={"status": "succeeded"}, fields=["name", "invoice"]
	)
	for row in succeeded_payments:
		invoice_status = frappe.db.get_value("QTT Invoice", row.invoice, "status")
		if invoice_status not in ("paid",):
			frappe.db.set_value("QTT Invoice", row.invoice, "status", "paid")
			corrections.append({"invoice": row.invoice, "payment": row.name, "corrected_to": "paid"})
	return corrections


def _audit_webhook_rejected(gateway_key: str) -> None:
	write_audit_event("security_violation", metadata={"reason": "invalid_webhook_signature", "gateway": gateway_key})
	frappe.log_error(
		title=f"Rejected webhook: invalid signature ({gateway_key})",
		message="A webhook with an invalid signature was rejected.",
	)
