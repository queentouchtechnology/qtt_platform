"""
The tenant-level slice of the authorization engine (QTT SaaS Platform
architecture, section 19 / 4 across the six architecture documents).

Phase 1 implements the tenant-only functions. Product-aware functions
(require_product_access, require_product_role, require_document_tenant_and_product,
resolve_tenant_for_doc) are added in Phase 3 once QTT Product / QTT Product
Access exist — they are deliberately not stubbed here, so nothing in this
file references a doctype that doesn't exist yet.

Every function re-queries the database on every call. Nothing about tenant
or membership *validity* is ever cached — only which tenant is currently
selected is (see tenant/context.py) — so a revoked membership or a
suspended tenant takes effect on the very next request, never stale. See
the hardening review, section 6.
"""

import frappe
from frappe import _

#: Tenant statuses under which the tenant may be operated on at all.
#: suspended / cancelled / archived are all "locked out" states — see the
#: hardening review section 22 for the distinctions between them.
_OPERABLE_TENANT_STATUSES = ("trial", "active")

#: Membership statuses that count as "currently a member."
_ACTIVE_MEMBERSHIP_STATUS = "active"

#: The one Frappe Role that spans every tenant — checked independently of
#: the tenant/membership chain, never by faking a membership pass. See the
#: role model review, hardening review section 5.
PLATFORM_OWNER_ROLE = "QTT Platform Owner"


def require_platform_owner():
	"""Raises frappe.PermissionError unless the current session holds the
	platform-wide Frappe Role. Used for operations that are not scoped to
	any single tenant at all (suspend a tenant, modify the Product
	Registry, ...)."""
	if PLATFORM_OWNER_ROLE not in frappe.get_roles():
		frappe.throw(_("This action requires Platform Owner privileges."), frappe.PermissionError)


def require_tenant_membership(tenant: str, user: str | None = None):
	"""Raises frappe.PermissionError unless `user` (default: the current
	session user) has an active membership in an operable `tenant`.
	Returns the QTT Tenant Membership document on success — callers that
	also need `tenant_role` should use this return value rather than
	querying it again."""
	user = user or frappe.session.user

	if not tenant:
		frappe.throw(_("No active tenant."), frappe.PermissionError)

	tenant_status = frappe.db.get_value("QTT Tenant", tenant, "status")
	if tenant_status is None:
		frappe.throw(_("Tenant not found."), frappe.PermissionError)
	if tenant_status not in _OPERABLE_TENANT_STATUSES:
		frappe.throw(_("This tenant is not currently active."), frappe.PermissionError)

	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": user, "tenant": tenant}, "name"
	)
	if not membership_name:
		frappe.throw(_("You are not a member of this tenant."), frappe.PermissionError)

	membership = frappe.get_doc("QTT Tenant Membership", membership_name)
	if membership.status != _ACTIVE_MEMBERSHIP_STATUS:
		frappe.throw(_("Your membership in this tenant is not active."), frappe.PermissionError)

	return membership


def require_tenant_role(tenant: str, allowed_roles: list[str], user: str | None = None):
	"""Like require_tenant_membership, additionally requiring the
	membership's tenant_role to be one of `allowed_roles`. Returns the
	membership document on success."""
	membership = require_tenant_membership(tenant, user=user)
	if membership.tenant_role not in allowed_roles:
		frappe.throw(
			_("This action requires one of these tenant roles: {0}.").format(", ".join(allowed_roles)),
			frappe.PermissionError,
		)
	return membership


def has_tenant_membership(tenant: str, user: str | None = None) -> bool:
	"""Non-raising check, for call sites that want a boolean (e.g. deciding
	whether to show a UI affordance) rather than an exception. Never use
	this for the actual access-control decision — that's what the
	require_* functions above are for."""
	try:
		require_tenant_membership(tenant, user=user)
		return True
	except frappe.PermissionError:
		return False
