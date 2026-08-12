"""
The bootstrap session API — create a tenant, switch between tenants, list a
user's own memberships. See the whitelisted-API pattern (hardening review
section 14) — every function below follows it exactly, using only the
steps that actually apply to it.

Note: earlier drafts of this architecture had a separate `resolve_session`
endpoint here for a standalone Node AI Gateway to call. That gateway was
retired in favor of porting the AI service directly into this app (see the
single-application specification) — there is no external service left that
needs to resolve a session from the outside, so that endpoint does not
exist here and should not be re-added without a new, real reason.
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.context import switch_tenant as _switch_tenant
from qtt_platform.tenant.context import resolve_active_tenant


@frappe.whitelist()
def create_tenant(tenant_name: str, slug: str) -> dict:
	"""Self-service tenant bootstrap — the one whitelisted method that
	requires no pre-existing tenant/membership, per the API review's
	explicit carve-out (hardening review section 14). Creates the Tenant
	and its Tenant Owner membership atomically (both inserts share the
	same request-level DB transaction; Frappe rolls both back together if
	anything below raises — see the data consistency review, section 24),
	then activates it as the caller's active tenant.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("You must be logged in to create a tenant."), frappe.PermissionError)

	tenant_name = (tenant_name or "").strip()
	slug = (slug or "").strip().lower()
	if not tenant_name:
		frappe.throw(_("Tenant name is required."), frappe.ValidationError)
	if not slug:
		frappe.throw(_("Slug is required."), frappe.ValidationError)
	if frappe.db.exists("QTT Tenant", {"slug": slug}):
		frappe.throw(_("This slug is already taken."), frappe.ValidationError)

	tenant = frappe.get_doc(
		{
			"doctype": "QTT Tenant",
			"tenant_name": tenant_name,
			"slug": slug,
			"owner_user": user,
			"status": "trial",
		}
	)
	tenant.insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "QTT Tenant Membership",
			"user": user,
			"tenant": tenant.name,
			"tenant_role": "Tenant Owner",
			"status": "active",
		}
	).insert(ignore_permissions=True)

	write_audit_event("tenant_created", tenant=tenant.name, target_doctype="QTT Tenant", target_name=tenant.name)

	result = _switch_tenant(tenant.name, user=user)
	return {"tenant": tenant.name, **result}


@frappe.whitelist()
def switch_tenant(tenant: str) -> dict:
	"""Re-validates membership every call (see tenant/context.py) and
	overwrites the cached active-tenant pointer — never merges with
	whatever was selected before."""
	return _switch_tenant(tenant)


@frappe.whitelist()
def get_my_memberships() -> list[dict]:
	"""Every active membership for the current session user, with the
	tenant's display name attached — this is what the Flutter tenant
	picker (0 / 1 / many memberships) is built from. Filtered by the
	session user hardcoded server-side, never a client-supplied user id —
	using frappe.get_all here is intentional and safe: this doctype grants
	no DocPerm to any tenant-level role at all (see qtt_tenant_membership.json),
	so there is no permission layer to bypass, and the filter itself is
	never influenced by request data.
	"""
	user = frappe.session.user
	rows = frappe.get_all(
		"QTT Tenant Membership",
		filters={"user": user, "status": "active"},
		fields=["tenant", "tenant_role"],
	)
	if not rows:
		return []

	tenant_names = [r.tenant for r in rows]
	tenants = frappe.get_all(
		"QTT Tenant",
		filters={"name": ["in", tenant_names]},
		fields=["name", "tenant_name", "status"],
	)
	tenant_by_name = {t.name: t for t in tenants}

	return [
		{
			"tenant": row.tenant,
			"tenant_name": tenant_by_name.get(row.tenant, {}).get("tenant_name"),
			"tenant_status": tenant_by_name.get(row.tenant, {}).get("status"),
			"tenant_role": row.tenant_role,
		}
		for row in rows
	]


@frappe.whitelist()
def get_active_tenant() -> dict | None:
	"""What Flutter calls right after login to know whether a tenant is
	already selected — never what the server trusts as the acting tenant
	for any other operation; every other whitelisted method re-resolves
	this itself server-side."""
	tenant = resolve_active_tenant()
	if not tenant:
		return None
	tenant_doc = frappe.db.get_value("QTT Tenant", tenant, ["tenant_name", "status"], as_dict=True)
	if not tenant_doc:
		return None
	return {"tenant": tenant, "tenant_name": tenant_doc.tenant_name, "tenant_status": tenant_doc.status}
