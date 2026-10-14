"""
View as (Business › Team › a person › View as): the business owner opens the app as one of their
people, view only. start → a token the app sends with every read (qtt_platform.view_as); stop ends it.
"""

import frappe
from frappe.rate_limiter import rate_limit

from qtt_platform import view_as
from qtt_platform import view_as_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.errors import fail, ok
from qtt_platform.tenant.context import resolve_active_tenant


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=3600)
def start(user: str) -> dict:
	"""Start viewing the app as `user` (someone in the owner's active business)."""
	owner = frappe.session.user
	tenant = resolve_active_tenant(owner)
	if not tenant:
		return fail("NO_BUSINESS", "Choose your business first.")
	why = view_as.eligibility(owner, tenant, user)
	if why:
		return fail("NOT_ALLOWED", why)
	token = view_as.issue(owner, tenant, user)
	role = frappe.db.get_value("QTT Tenant Membership", {"user": user, "tenant": tenant, "status": "active"}, "tenant_role")
	write_audit_event("view_as.start", tenant=tenant, target_doctype="User", target_name=user, metadata={"owner": owner})
	return ok({"token": token, "user": user, "full_name": frappe.utils.get_fullname(user), "tenant_role": role,
			   "expires_in": rules.TTL_SECONDS})


@frappe.whitelist(methods=["POST"])
def stop(token: str | None = None) -> dict:
	"""End a view (the owner's own token only)."""
	data = view_as.lookup(token or "")
	if data and data.get("owner") == frappe.session.user:
		view_as.revoke(token)
		write_audit_event("view_as.stop", tenant=data["tenant"], target_doctype="User", target_name=data["target"],
						  metadata={"owner": data["owner"]})
	return ok({})
