"""
View as: the business owner sees the app as one of their people (Business › Team › a person ›
View as) — every screen, as that person would see it, and nothing can be changed.

How a request becomes "as them" (hook `auth_hooks`, after Frappe has signed in the owner):
  - the app sends header X-QTT-View-As with a token from api.view_as.start (30 minutes, renewed on use);
  - the token must belong to the signed-in owner, who must still own that business, and the person
    must still be in it (checked on every request);
  - only reads (GET) of the QTT apps' own methods are allowed (view_as_rules.request_allowed);
  - the request runs in a read-only database transaction (Frappe's read-only mode), as the person,
    in the owner's business — and the owner's own session is never touched.
Start and stop are written to QTT Audit Log.
"""

import frappe

from qtt_platform import view_as_rules as rules

HEADER = "X-QTT-View-As"
_KEY = "qtt_view_as:"


def issue(owner: str, tenant: str, target: str) -> str:
	token = frappe.generate_hash(length=40)
	frappe.cache.set_value(_KEY + token, {"owner": owner, "tenant": tenant, "target": target}, expires_in_sec=rules.TTL_SECONDS)
	return token


def lookup(token: str) -> dict | None:
	return frappe.cache.get_value(_KEY + token) if token else None


def revoke(token: str) -> None:
	frappe.cache.delete_value(_KEY + token)


def eligibility(owner: str, tenant: str, target: str) -> str | None:
	"""Why not (None = may view), from the live memberships and roles."""
	owner_role = frappe.db.get_value("QTT Tenant Membership", {"user": owner, "tenant": tenant, "status": "active"}, "tenant_role")
	member = bool(frappe.db.exists("QTT Tenant Membership", {"user": target, "tenant": tenant, "status": "active"}))
	enabled = frappe.db.get_value("User", target, "enabled")
	roles = frappe.get_roles(target) if member and enabled else []
	return rules.can_view(owner=owner, owner_role=owner_role, target=target, target_member=member and bool(enabled), target_roles=roles)


def current() -> dict | None:
	"""{owner, tenant, target} while this request is a view as someone."""
	return getattr(frappe.local, "qtt_view_as", None)


def auth_hook() -> None:
	"""Frappe `auth_hooks`: turn the owner's request into a read-only one as the person."""
	token = frappe.get_request_header(HEADER)
	if not token:
		return
	owner = frappe.session.user
	data = lookup(token)
	if not owner or owner == "Guest" or not data or data.get("owner") != owner or eligibility(owner, data["tenant"], data["target"]):
		frappe.throw(rules.ENDED, frappe.PermissionError)
	ok, _why = rules.request_allowed(frappe.request.method, frappe.request.path)
	if not ok:
		frappe.throw(rules.VIEW_ONLY.format(name=frappe.utils.get_fullname(data["target"])), frappe.PermissionError)
	frappe.cache.set_value(_KEY + token, data, expires_in_sec=rules.TTL_SECONDS)  # renewed while in use

	# The owner's own session must never be saved as the person: Frappe saves the request's session
	# at the end, and set_user below changes it — so this request doesn't save one.
	frappe.local.session_obj = None
	# Nothing can be written: Frappe's read-only mode (errors are logged later, not in this transaction).
	frappe.flags.read_only = True
	frappe.db.rollback()
	frappe.db.begin(read_only=True)
	frappe.local.qtt_view_as = dict(data)
	form = frappe.local.form_dict  # set_user clears the request's parameters
	frappe.set_user(data["target"])
	frappe.local.form_dict = form
