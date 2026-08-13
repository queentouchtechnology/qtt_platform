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
from qtt_platform.errors import QttApiError, fail, ok
from qtt_platform.subscription import service as subscription_service
from qtt_platform.tenant.context import resolve_active_tenant
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
def get_my_payments(tenant: str) -> list[dict]:
	"""SaaS lifecycle Phase H (dashboard "payments" section). Read-only,
	same any-active-member visibility as get_my_invoices() above — QTT
	Payment has no `tenant` field of its own (append-only, gateway-
	neutral, per Phase C/D's immutability design), so this joins through
	QTT Invoice.tenant rather than adding one; a payment's tenant is
	always its invoice's tenant, never independently meaningful."""
	require_tenant_membership(tenant)
	invoice_names = frappe.get_all("QTT Invoice", filters={"tenant": tenant}, pluck="name")
	if not invoice_names:
		return []
	return frappe.get_all(
		"QTT Payment",
		filters={"invoice": ["in", invoice_names]},
		fields=["name", "invoice", "amount", "currency", "status", "paid_at", "refund_of"],
		order_by="paid_at desc",
	)


@frappe.whitelist()
def create_payment_order(tenant: str, invoice: str, *, gateway_key: str = "razorpay") -> dict:
	require_tenant_role(tenant, _BILLING_MANAGER_ROLES)

	invoice_tenant = frappe.db.get_value("QTT Invoice", invoice, "tenant")
	if invoice_tenant != tenant:
		frappe.throw(_("This invoice does not belong to your tenant."), frappe.PermissionError)

	return billing_service.create_payment_order(invoice, gateway_key=gateway_key)


@frappe.whitelist()
def start_subscription_checkout(product: str) -> dict:
	"""Production-readiness audit, P0 — the missing link between local
	signup (Phase A, deliberately local-subscription-only) and Phase C's
	billing.service.create_razorpay_subscription(), which had no caller
	anywhere in this app until now. Tenant resolved from the active
	session, matching this project's newer customer-facing endpoints
	(change_plan/resume/dashboard/ai.generate) — Owner-only, matching
	create_payment_order()'s own existing billing-action gate above.

	Idempotent: if the tenant's current subscription for `product` is
	already linked to Razorpay, this does NOT call
	create_razorpay_subscription() again (that function itself refuses a
	double-link and would raise) — it returns the existing linkage
	instead, reconstructing a minimal checkout payload
	(subscription_id + key_id) from what's already stored rather than
	persisting a gateway-issued short_url that could go stale. A client
	retrying after a network blip gets a usable response either way,
	never a confusing error for something that already succeeded.
	"""
	try:
		tenant = resolve_active_tenant()
		if not tenant:
			raise QttApiError("TENANT_ACCESS_DENIED", "No active tenant.")

		try:
			require_tenant_role(tenant, _BILLING_MANAGER_ROLES)
		except frappe.PermissionError as exc:
			raise QttApiError("BILLING_ROLE_REQUIRED", str(exc)) from exc

		subscription = subscription_service.get_current_subscription(tenant, product)
		if not subscription:
			raise QttApiError("SUBSCRIPTION_NOT_FOUND", "No subscription exists for this product.")
		if subscription.status == "cancelled":
			raise QttApiError("SUBSCRIPTION_CANCELLED", "This subscription has already been cancelled.")

		if subscription.razorpay_subscription_id:
			key_id = billing_service.get_gateway_public_key()
			return ok(
				{
					"subscription": subscription.name,
					"razorpay_subscription_id": subscription.razorpay_subscription_id,
					"already_linked": True,
					"checkout": {"subscription_id": subscription.razorpay_subscription_id, "key_id": key_id},
				}
			)

		result = billing_service.create_razorpay_subscription(subscription.name)
		return ok({"subscription": subscription.name, "already_linked": False, **result})

	except QttApiError as exc:
		return fail(exc.code, str(exc))
	except frappe.ValidationError as exc:
		return fail("VALIDATION_ERROR", str(exc))
	except Exception:
		frappe.log_error(
			title="qtt_platform.api.billing.start_subscription_checkout failed", message=frappe.get_traceback()
		)
		return fail("PAYMENT_REQUIRED", "Could not start checkout. Please try again.")


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
