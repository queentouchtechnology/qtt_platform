"""
The one bootstrap call for the QTT client app: who am I, which workspaces
am I in, which products can I use in the active one (with my role and the
workspace's subscription state), and am I QTT staff — in a single round
trip, instead of the app stitching it together from N calls per tenant.

Read-only and scoped to frappe.session.user by construction; it never
grants anything. Every product endpoint still runs its own
require_product_access / require_product_role check — this response only
decides what the app SHOWS.

Product-agnostic: products come from QTT Product rows, never named here.
"""

import frappe
from frappe import _
from frappe.utils import get_url

from qtt_platform.realtime import CONTEXT_CHANGED_EVENT
from qtt_platform.subscription import service as subscription_service
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import PLATFORM_OWNER_ROLE

_OPERABLE_TENANT_STATUSES = ("trial", "active")
_GOVERNANCE_ROLES = ("Tenant Owner", "Tenant Admin")


@frappe.whitelist()
def get_app_context() -> dict:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Login required."), frappe.PermissionError)

	profile = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
	memberships = _memberships(user)
	active = resolve_active_tenant(user)
	active_membership = next(
		(m for m in memberships if m["tenant"] == active and m["tenant_status"] in _OPERABLE_TENANT_STATUSES),
		None,
	)

	return {
		"user": {
			"id": user,
			"full_name": profile.get("full_name") or user,
			"image": profile.get("user_image"),
			"is_platform_owner": PLATFORM_OWNER_ROLE in frappe.get_roles(user),
		},
		"workspaces": memberships,
		"active_workspace": active_membership["tenant"] if active_membership else None,
		"products": _products(active_membership) if active_membership else [],
		"can_manage_workspace": bool(active_membership and active_membership["tenant_role"] in _GOVERNANCE_ROLES),
		"realtime": {"context_event": CONTEXT_CHANGED_EVENT},
	}


def _memberships(user: str) -> list[dict]:
	rows = frappe.get_all(
		"QTT Tenant Membership",
		filters={"user": user, "status": "active"},
		fields=["name", "tenant", "tenant_role"],
	)
	if not rows:
		return []
	tenants = {
		t.name: t
		for t in frappe.get_all(
			"QTT Tenant",
			filters={"name": ["in", [r.tenant for r in rows]]},
			fields=["name", "tenant_name", "status", "logo", "currency", "language", "timezone", "country"],
		)
	}
	result = []
	for r in rows:
		t = tenants.get(r.tenant)
		if not t:
			continue
		result.append(
			{
				"tenant": r.tenant,
				"membership": r.name,
				"tenant_name": t.tenant_name or r.tenant,
				"tenant_status": t.status,
				"tenant_role": r.tenant_role,
				"logo": get_url(t.logo) if t.logo and not t.logo.startswith("http") else t.logo,
				# Workspace-level formatting defaults for the app (money is
				# always shown in the workspace's currency).
				"currency": t.currency,
				"language": t.language,
				"timezone": t.timezone,
				"country": t.country,
			}
		)
	return sorted(result, key=lambda m: (m["tenant_name"] or "").lower())


def _products(membership: dict) -> list[dict]:
	access = frappe.get_all(
		"QTT Product Access",
		filters={"membership": membership["membership"], "status": "active"},
		fields=["product", "product_role"],
	)
	if not access:
		return []
	catalog = {
		p.name: p
		for p in frappe.get_all(
			"QTT Product",
			filters={"name": ["in", [a.product for a in access]], "status": "active"},
			fields=["name", "display_name", "icon", "description"],
		)
	}
	products = []
	for a in access:
		product = catalog.get(a.product)
		if not product:
			continue  # disabled product: hidden, and its guards refuse access anyway
		products.append(
			{
				"product": a.product,
				"display_name": product.display_name or a.product,
				"icon": product.icon,
				"description": product.description,
				"role": a.product_role,
				"subscription": _subscription_summary(membership["tenant"], a.product),
			}
		)
	return sorted(products, key=lambda p: p["display_name"].lower())


def _subscription_summary(tenant: str, product: str) -> dict | None:
	sub = subscription_service.get_current_subscription(tenant, product)
	if not sub:
		return None
	return {
		"status": sub.status,
		"plan_code": frappe.db.get_value("QTT Plan", sub.plan, "plan_code"),
		"trial_end": str(sub.trial_end) if sub.trial_end else None,
		"current_period_end": str(sub.current_period_end) if sub.current_period_end else None,
	}
