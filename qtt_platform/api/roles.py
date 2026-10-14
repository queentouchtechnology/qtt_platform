"""
Business › Roles and access: what each role can do in each of the business's apps. The owner
and admins see every app's table and switch areas on or off for the roles an app lets them
change (Orbitra's Manager and Cashier); the app enforces the result on every request.
"""

import frappe
from frappe import _

from qtt_platform import abilities, role_access
from qtt_platform import role_access_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership


def _tenant() -> str:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."))
	abilities.require(require_tenant_membership(tenant), "business")
	return tenant


def _spec(tenant: str, product: str) -> dict:
	if product not in {p["product"] for p in role_access.tenant_products(tenant)}:
		frappe.throw(_("This app isn't part of your business."), frappe.DoesNotExistError)
	return role_access.spec(product)


@frappe.whitelist()
def tables() -> list[dict]:
	return role_access.tables(_tenant())


@frappe.whitelist(methods=["POST"])
def set_area(product: str, role: str, area: str, allowed) -> list[dict]:
	"""Switch one area on or off for one role; returns the updated tables."""
	tenant = _tenant()
	spec = _spec(tenant, product)
	before = role_access.areas(tenant, product, role, spec)
	try:
		after = rules.change(spec, before, role, area, str(allowed).lower() in ("1", "true"))
	except rules.AccessError as e:
		frappe.throw(_(str(e)))
	default = rules.effective(spec, role, None)
	role_access.save(tenant, product, role, None if after == default else after)
	write_audit_event("role_access_changed", tenant=tenant, product=product, target_doctype=role_access.DT,
					  target_name=role, before_state={"areas": before}, after_state={"areas": after})
	return role_access.tables(tenant)


@frappe.whitelist(methods=["POST"])
def reset(product: str, role: str) -> list[dict]:
	"""Back to the app's defaults for one role."""
	tenant = _tenant()
	spec = _spec(tenant, product)
	if role not in spec.get("editable", []):
		frappe.throw(_("This role's access is fixed."))
	before = role_access.areas(tenant, product, role, spec)
	role_access.save(tenant, product, role, None)
	write_audit_event("role_access_reset", tenant=tenant, product=product, target_doctype=role_access.DT,
					  target_name=role, before_state={"areas": before}, after_state={"areas": rules.effective(spec, role, None)})
	return role_access.tables(tenant)
