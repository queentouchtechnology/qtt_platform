"""
Tenant-facing product access management. Granting, revoking, and changing
product access are TENANT governance actions (Tenant Owner / Tenant Admin),
not product-level ones — per the hardening review's authorization matrix
(section 5). A product may optionally layer its own self-service capability
on top of this later; the platform itself only provides this
tenant-governed path.
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

_GOVERNANCE_ROLES = ["Tenant Owner", "Tenant Admin"]


def _get_active_membership_or_throw(tenant: str, target_user: str) -> str:
	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": target_user, "tenant": tenant, "status": "active"}, "name"
	)
	if not membership_name:
		frappe.throw(
			_("{0} is not an active member of this tenant.").format(target_user),
			frappe.ValidationError,
		)
	return membership_name


@frappe.whitelist()
def grant_product_access(tenant: str, target_user: str, product: str, product_role: str) -> dict:
	"""Create-or-reactivate `target_user`'s Product Access to `product`
	within `tenant`. `product_role` is validated against the product's
	own role catalog inside QTT Product Access.validate() — never a
	platform-hardcoded list."""
	require_tenant_role(tenant, _GOVERNANCE_ROLES)
	membership_name = _get_active_membership_or_throw(tenant, target_user)

	existing_name = frappe.db.exists(
		"QTT Product Access", {"membership": membership_name, "product": product}
	)
	if existing_name:
		access = frappe.get_doc("QTT Product Access", existing_name)
		access.product_role = product_role
		access.status = "active"
		access.save(ignore_permissions=True)
	else:
		access = frappe.get_doc(
			{
				"doctype": "QTT Product Access",
				"membership": membership_name,
				"tenant": tenant,
				"product": product,
				"product_role": product_role,
				"status": "active",
			}
		)
		access.insert(ignore_permissions=True)

	write_audit_event(
		"product_access_granted",
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Access",
		target_name=access.name,
		metadata={"target_user": target_user, "product_role": product_role},
	)

	return {"name": access.name, "product_role": access.product_role, "status": access.status}


@frappe.whitelist()
def revoke_product_access(tenant: str, target_user: str, product: str) -> dict:
	"""Soft-revoke — status becomes 'removed', the row is never deleted,
	preserving the audit trail (consistent with how Tenant Membership
	removal is handled). A Tenant Owner/Admin may not revoke their OWN
	product access this way — doing so can lock them out of the very
	role-gated screens they'd need to grant it back from, with no other
	governance action left to recover it. Self-service leave, if ever
	needed, is a deliberately separate decision, not a side effect of
	this admin action."""
	if target_user == frappe.session.user:
		frappe.throw(_("You can't remove your own product access."), frappe.ValidationError)
	require_tenant_role(tenant, _GOVERNANCE_ROLES)
	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": target_user, "tenant": tenant}, "name"
	)
	if not membership_name:
		frappe.throw(_("{0} is not a member of this tenant.").format(target_user), frappe.ValidationError)

	access_name = frappe.db.exists(
		"QTT Product Access", {"membership": membership_name, "product": product}
	)
	if not access_name:
		frappe.throw(_("No product access record found for {0}.").format(target_user), frappe.ValidationError)

	access = frappe.get_doc("QTT Product Access", access_name)
	access.status = "removed"
	access.save(ignore_permissions=True)

	write_audit_event(
		"product_access_removed",
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Access",
		target_name=access.name,
		metadata={"target_user": target_user},
	)

	return {"name": access.name, "status": access.status}


@frappe.whitelist()
def change_product_role(tenant: str, target_user: str, product: str, new_role: str) -> dict:
	require_tenant_role(tenant, _GOVERNANCE_ROLES)
	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": target_user, "tenant": tenant}, "name"
	)
	if not membership_name:
		frappe.throw(_("{0} is not a member of this tenant.").format(target_user), frappe.ValidationError)

	access_name = frappe.db.exists(
		"QTT Product Access", {"membership": membership_name, "product": product}
	)
	if not access_name:
		frappe.throw(_("No product access record found for {0}.").format(target_user), frappe.ValidationError)

	access = frappe.get_doc("QTT Product Access", access_name)
	access.product_role = new_role  # re-validated against the role catalog in validate()
	access.save(ignore_permissions=True)

	write_audit_event(
		"product_role_changed",
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Access",
		target_name=access.name,
		metadata={"target_user": target_user, "new_role": new_role},
	)

	return {"name": access.name, "product_role": access.product_role}


@frappe.whitelist()
def remove_team_member(tenant: str, target_user: str) -> dict:
	"""Fully removes a member from the tenant — not just their product
	access (see `revoke_product_access` above for that, narrower,
	action). Soft-removes the `QTT Tenant Membership` itself (status ->
	'removed', never deleted, same audit-trail-preserving convention as
	every other revoke in this file) and cascades to soft-revoke every
	active `QTT Product Access` row under it — a removed member
	shouldn't be left holding live access to any product just because
	this call only touched the membership row.

	Same self-protection as `revoke_product_access`: a Tenant Owner/
	Admin can't remove themselves this way, for the same lockout
	reason."""
	if target_user == frappe.session.user:
		frappe.throw(_("You can't remove yourself from the organization."), frappe.ValidationError)
	require_tenant_role(tenant, _GOVERNANCE_ROLES)

	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": target_user, "tenant": tenant}, "name"
	)
	if not membership_name:
		frappe.throw(_("{0} is not a member of this tenant.").format(target_user), frappe.ValidationError)

	membership = frappe.get_doc("QTT Tenant Membership", membership_name)
	membership.status = "removed"
	membership.save(ignore_permissions=True)

	access_rows = frappe.get_all(
		"QTT Product Access", filters={"membership": membership_name, "status": "active"}, fields=["name"]
	)
	for row in access_rows:
		frappe.db.set_value("QTT Product Access", row.name, "status", "removed")

	write_audit_event(
		"team_member_removed",
		tenant=tenant,
		target_doctype="QTT Tenant Membership",
		target_name=membership_name,
		metadata={"target_user": target_user, "product_access_revoked": len(access_rows)},
	)

	return {"name": membership_name, "status": membership.status}


@frappe.whitelist()
def get_my_product_access(tenant: str) -> list[dict]:
	"""Every active Product Access row for the current session user within
	`tenant` — what a Flutter product-picker/dashboard is built from.
	Reads only the caller's own data by construction (filtered by their
	own membership), so this is not itself an authorization decision that
	needs further guarding."""
	user = frappe.session.user
	membership_name = frappe.db.get_value(
		"QTT Tenant Membership", {"user": user, "tenant": tenant, "status": "active"}, "name"
	)
	if not membership_name:
		return []

	rows = frappe.get_all(
		"QTT Product Access",
		filters={"membership": membership_name, "status": "active"},
		fields=["product", "product_role"],
	)
	if not rows:
		return []

	product_names = [r.product for r in rows]
	products = frappe.get_all(
		"QTT Product",
		filters={"name": ["in", product_names]},
		fields=["name", "display_name", "icon"],
	)
	product_by_name = {p.name: p for p in products}

	return [
		{
			"product": row.product,
			"display_name": product_by_name.get(row.product, {}).get("display_name"),
			"icon": product_by_name.get(row.product, {}).get("icon"),
			"product_role": row.product_role,
		}
		for row in rows
	]


@frappe.whitelist()
def get_team_members(tenant: str) -> list[dict]:
	"""SaaS lifecycle Phase H (dashboard "team members" section). Every
	active member of `tenant` with their tenant role and whatever active
	product access rows they hold. Visible to any active member, not
	gated to Owner/Admin — a team roster is read-only and materially less
	sensitive than the governance actions above (grant/revoke/change),
	which stay Owner/Admin-only, unchanged."""
	require_tenant_membership(tenant)

	memberships = frappe.get_all(
		"QTT Tenant Membership",
		filters={"tenant": tenant, "status": "active"},
		fields=["name", "user", "tenant_role"],
	)
	if not memberships:
		return []

	membership_names = [m.name for m in memberships]
	access_rows = frappe.get_all(
		"QTT Product Access",
		filters={"membership": ["in", membership_names], "status": "active"},
		fields=["membership", "product", "product_role"],
	)
	access_by_membership: dict[str, list[dict]] = {}
	for row in access_rows:
		access_by_membership.setdefault(row.membership, []).append(
			{"product": row.product, "product_role": row.product_role}
		)

	return [
		{
			"user": m.user,
			"tenant_role": m.tenant_role,
			"product_access": access_by_membership.get(m.name, []),
		}
		for m in memberships
	]
