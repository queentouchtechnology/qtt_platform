"""
SaaS customer dashboard — SaaS lifecycle Phase H. Pure composition: every
piece of data here is already produced by an existing function from an
earlier phase (session, product_access, subscription, entitlement,
billing). This module adds ZERO new business logic — its only job is
assembling one response so a dashboard screen doesn't have to make eight
separate calls and stitch them together itself. The three genuinely new
pieces this phase needed (a full entitlements-with-usage listing, a
payments listing, a team-members listing) were added to their own
existing, natural homes (qtt_platform.entitlement.engine, api/billing.py,
api/product_access.py respectively) — not here — so this file stays a
pure aggregator, reusable if a future product ever wants the same shape.

Tenant is resolved from the caller's active tenant session
(resolve_active_tenant), not a request parameter — same convention Phase
E established for change_plan()/resume() (a "show me me" endpoint has no
reason to accept a client-supplied tenant). `product` IS a required
parameter with no default, deliberately: qtt_platform stays
product-agnostic even for this endpoint — nothing here assumes QMP_LMS.
"""

import frappe

from qtt_platform.api.billing import get_my_invoices, get_my_payments
from qtt_platform.api.product_access import get_team_members
from qtt_platform.api.subscription import get_my_subscription
from qtt_platform.entitlement.engine import get_entitlements_with_usage
from qtt_platform.errors import fail, ok
from qtt_platform.product.guards import has_product_access, require_product_access
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership


@frappe.whitelist()
def get_dashboard(product: str) -> dict:
	tenant = resolve_active_tenant()
	if not tenant:
		return fail("TENANT_ACCESS_DENIED", "No active tenant.")

	try:
		membership = require_tenant_membership(tenant)
	except frappe.PermissionError as exc:
		return fail("TENANT_ACCESS_DENIED", str(exc))

	tenant_doc = frappe.db.get_value(
		"QTT Tenant", tenant, ["tenant_name", "status", "owner_user"], as_dict=True
	)

	product_access = None
	if has_product_access(tenant, product):
		access = require_product_access(tenant, product)
		product_access = {"product": product, "product_role": access.product_role, "status": access.status}

	subscription = get_my_subscription(tenant, product)
	entitlements = get_entitlements_with_usage(tenant, product) if product_access else []

	return ok(
		{
			"organization": {
				"tenant": tenant,
				"tenant_name": tenant_doc.tenant_name if tenant_doc else None,
				"status": tenant_doc.status if tenant_doc else None,
				"owner": tenant_doc.owner_user if tenant_doc else None,
			},
			"user": {"email": frappe.session.user, "tenant_role": membership.tenant_role},
			"product": product_access,
			"subscription": subscription,
			"next_billing_date": subscription["current_period_end"] if subscription else None,
			"entitlements": entitlements,
			"billing": {
				"invoices": get_my_invoices(tenant),
				"payments": get_my_payments(tenant),
			},
			"team_members": get_team_members(tenant),
		}
	)
