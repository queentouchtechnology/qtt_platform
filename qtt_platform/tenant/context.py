"""
Server-side active-tenant session state (QTT SaaS Platform architecture,
section 9; hardening review section 6).

The active tenant is never read from Flutter — not from a request body, a
header, a query parameter, or a URL. It is server-side state, keyed by
`frappe.session.user` in Frappe's own cache (Redis-backed), set only by
`switch_tenant()` below after re-validating real membership. Every
tenant-scoped guard (tenant/guards.py) re-checks the underlying membership
on every call regardless of this cache, so a stale cache entry can never
grant access a revoked membership wouldn't otherwise allow — see the
hardening review section 6 for the exact reasoning.
"""

import frappe

from qtt_platform.tenant.guards import require_tenant_membership

_CACHE_PREFIX = "qtt_active_tenant"

#: Cache entries are not cleared on logout — resuming the app should resume
#: the same tenant. They are re-validated on every use regardless, so this
#: TTL only bounds how long a genuinely abandoned session's pointer lingers
#: in Redis, not how long access is valid for.
_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _cache_key(user: str) -> str:
	return f"{_CACHE_PREFIX}:{user}"


def resolve_active_tenant(user: str | None = None) -> str | None:
	"""Returns the currently-selected tenant for `user` (default: the
	current session user), or None if none is selected yet. Does NOT
	validate that the membership is still active — callers that are about
	to act on the result must still call require_tenant_membership /
	require_tenant_role, exactly as every whitelisted method in this
	codebase is required to."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return frappe.cache().get_value(_cache_key(user))


def switch_tenant(tenant: str, user: str | None = None) -> dict:
	"""The only function that writes the active-tenant cache. Re-validates
	membership every time — never trusts a previously-cached value, never
	trusts anything the caller supplied beyond the tenant they're asking
	to switch to. Raises frappe.PermissionError if the membership isn't
	valid; the cache is left untouched on failure."""
	user = user or frappe.session.user
	membership = require_tenant_membership(tenant, user=user)  # raises on failure

	frappe.cache().set_value(_cache_key(user), tenant, expires_in_sec=_CACHE_TTL_SECONDS)

	return {"tenant": tenant, "tenant_role": membership.tenant_role}


def clear_active_tenant(user: str | None = None) -> None:
	"""Not called on ordinary logout (see the module docstring) — provided
	for the cases that do need an explicit clear: an admin forcibly ending
	a user's active session context, or a test fixture tearing down
	state."""
	user = user or frappe.session.user
	frappe.cache().delete_value(_cache_key(user))
