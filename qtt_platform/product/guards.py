"""
The product-level slice of the authorization engine, paired with
tenant/guards.py's tenant-level slice. Every function re-queries the
database on every call — same non-caching discipline as tenant/guards.py,
for the same reason (hardening review section 6).
"""

import frappe
from frappe import _

from qtt_platform.tenant.guards import require_tenant_membership

_ACTIVE_ACCESS_STATUS = "active"
_OPERABLE_PRODUCT_STATUSES = ("active",)


def require_product_access(tenant: str, product: str, user: str | None = None):
	"""Raises frappe.PermissionError unless `user` holds active Product
	Access to `product` within `tenant`. Three independent things must
	all be true, checked in this order so the error message is always
	specific: the underlying Tenant Membership must still be active (a
	removed/suspended membership implicitly voids every Product Access
	grant it owns — no cascade-delete needed, see the hardening review
	section 22), the product itself must not be disabled (one flag change
	locks out every tenant at once, section 3), and a real, active
	Product Access row must exist. Returns the access document on
	success."""
	user = user or frappe.session.user

	# Also re-validates tenant status/membership status — a suspended
	# tenant or a removed membership fails right here.
	require_tenant_membership(tenant, user=user)

	product_status = frappe.db.get_value("QTT Product", product, "status")
	if product_status is None:
		frappe.throw(_("Product not found."), frappe.PermissionError)
	if product_status not in _OPERABLE_PRODUCT_STATUSES:
		frappe.throw(_("This product is not currently available."), frappe.PermissionError)

	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": user, "tenant": tenant}, "name"
	)
	if not membership_name:
		frappe.throw(_("You are not a member of this tenant."), frappe.PermissionError)

	access_name = frappe.db.get_value(
		"QTT Product Access", {"membership": membership_name, "product": product}, "name"
	)
	if not access_name:
		frappe.throw(_("You do not have access to this product."), frappe.PermissionError)

	access = frappe.get_doc("QTT Product Access", access_name)
	if access.status != _ACTIVE_ACCESS_STATUS:
		frappe.throw(_("Your access to this product is not active."), frappe.PermissionError)

	return access


def require_product_role(tenant: str, product: str, allowed_roles: list[str], user: str | None = None):
	"""Like require_product_access, additionally requiring product_role to
	be one of `allowed_roles`."""
	access = require_product_access(tenant, product, user=user)
	if access.product_role not in allowed_roles:
		frappe.throw(
			_("This action requires one of these product roles: {0}.").format(", ".join(allowed_roles)),
			frappe.PermissionError,
		)
	return access


def has_product_access(tenant: str, product: str, user: str | None = None) -> bool:
	"""Non-raising check for UI-affordance decisions — never the actual
	access-control gate. See tenant/guards.py's has_tenant_membership for
	the identical reasoning."""
	try:
		require_product_access(tenant, product, user=user)
		return True
	except frappe.PermissionError:
		return False
