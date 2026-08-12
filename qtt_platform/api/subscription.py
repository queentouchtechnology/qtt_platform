"""
Tenant-facing subscription management. Per the hardening review's
authorization matrix (section 5), changing a subscription is a financial
governance action — Tenant Owner only by default, not Tenant Admin, absent
an explicit tenant-level configuration to widen that (not built in Phase 4;
the default is deliberately the narrower, safer one).
"""

import frappe
from frappe import _

from qtt_platform.subscription import service
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

_SUBSCRIPTION_MANAGER_ROLES = ["Tenant Owner"]


def _as_bool(value, default: bool) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() not in ("0", "false", "no", "")


@frappe.whitelist()
def subscribe(tenant: str, product: str, plan_code: str) -> dict:
	require_tenant_role(tenant, _SUBSCRIPTION_MANAGER_ROLES)

	plan_name = frappe.db.get_value("QTT Plan", {"product": product, "plan_code": plan_code}, "name")
	if not plan_name:
		frappe.throw(_("No plan '{0}' found for this product.").format(plan_code))

	existing = service.get_current_subscription(tenant, product)
	if existing and existing.status in OPEN_SUBSCRIPTION_STATUSES:
		frappe.throw(
			_("This tenant already has a subscription for this product — use change_plan instead."),
			frappe.ValidationError,
		)

	subscription = service.create_subscription(tenant, product, plan_name)
	return {"subscription": subscription.name, "plan": plan_name, "status": subscription.status}


@frappe.whitelist()
def get_my_subscription(tenant: str, product: str) -> dict | None:
	"""Read-only — any active tenant member may see the tenant's own
	subscription state, not only Tenant Owner/Admin."""
	require_tenant_membership(tenant)

	current = service.get_current_subscription(tenant, product)
	if not current:
		return None
	return {
		"subscription": current.name,
		"plan": current.plan,
		"status": current.status,
		"current_period_start": str(current.current_period_start),
		"current_period_end": str(current.current_period_end),
		"cancel_at_period_end": bool(current.cancel_at_period_end),
	}


@frappe.whitelist()
def change_plan(tenant: str, product: str, new_plan_code: str) -> dict:
	require_tenant_role(tenant, _SUBSCRIPTION_MANAGER_ROLES)

	new_plan_name = frappe.db.get_value(
		"QTT Plan", {"product": product, "plan_code": new_plan_code}, "name"
	)
	if not new_plan_name:
		frappe.throw(_("No plan '{0}' found for this product.").format(new_plan_code))

	new_subscription = service.change_plan(tenant, product, new_plan_name)
	return {"subscription": new_subscription.name, "plan": new_subscription.plan, "status": new_subscription.status}


@frappe.whitelist()
def cancel(tenant: str, product: str, at_period_end=True) -> dict:
	require_tenant_role(tenant, _SUBSCRIPTION_MANAGER_ROLES)

	current = service.cancel_subscription(tenant, product, at_period_end=_as_bool(at_period_end, True))
	return {
		"subscription": current.name,
		"status": current.status,
		"cancel_at_period_end": bool(current.cancel_at_period_end),
	}
