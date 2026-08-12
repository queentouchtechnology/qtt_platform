"""
Tenant-facing billing endpoints, plus the inbound webhook handler.

The webhook function is deliberately the only `allow_guest=True`
whitelisted method in this entire app — everything else requires a real
Frappe session. A payment gateway's server calls it with no session at
all; the ONLY authentication is the signature check inside
billing.service.process_webhook(), which runs before a single payload
field is read (hardening review section 10).
"""

import frappe
from frappe import _

from qtt_platform.billing import service as billing_service
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

_BILLING_MANAGER_ROLES = ["Tenant Owner"]


@frappe.whitelist()
def get_my_invoices(tenant: str) -> list[dict]:
	"""Read-only — any active tenant member may see the tenant's own
	invoices, not only Tenant Owner/Admin (matches get_my_subscription's
	same reasoning in api/subscription.py)."""
	require_tenant_membership(tenant)
	rows = frappe.get_all(
		"QTT Invoice",
		filters={"tenant": tenant},
		fields=["name", "amount", "currency", "status", "due_date", "creation"],
		order_by="creation desc",
	)
	return rows


@frappe.whitelist()
def create_payment_order(tenant: str, invoice: str, *, gateway_key: str = "razorpay") -> dict:
	require_tenant_role(tenant, _BILLING_MANAGER_ROLES)

	invoice_tenant = frappe.db.get_value("QTT Invoice", invoice, "tenant")
	if invoice_tenant != tenant:
		frappe.throw(_("This invoice does not belong to your tenant."), frappe.PermissionError)

	return billing_service.create_payment_order(invoice, gateway_key=gateway_key)


@frappe.whitelist(allow_guest=True)
def razorpay_webhook():
	"""No session, no tenant/product/role checks — the signature IS the
	authentication. See billing/service.py's process_webhook() for the
	verify-before-read ordering. X-Razorpay-Event-Id (SaaS lifecycle
	Phase D) is only load-bearing for subscription.* events — see
	process_webhook()'s own docstring; harmless to always pass through."""
	payload_body = frappe.request.get_data()
	signature = frappe.request.headers.get("X-Razorpay-Signature", "")
	gateway_event_id = frappe.request.headers.get("X-Razorpay-Event-Id")

	result = billing_service.process_webhook("razorpay", payload_body, signature, gateway_event_id=gateway_event_id)
	return result
