import frappe


def execute():
	"""Desk UI fix — QTT Tenant Membership gained a new computed
	membership_title field (set going forward by the controller's own
	validate()); this backfills every row that already existed before the
	field did, including real production memberships like ABC School's
	owner (1bdpsvqakp), so no row is left showing a blank title until its
	next unrelated save."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_tenant_membership")

	memberships = frappe.get_all("QTT Tenant Membership", fields=["name", "user", "tenant"])
	for row in memberships:
		tenant_name = frappe.db.get_value("QTT Tenant", row.tenant, "tenant_name") or row.tenant
		frappe.db.set_value(
			"QTT Tenant Membership", row.name, "membership_title", f"{row.user} — {tenant_name}"
		)
