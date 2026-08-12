import frappe


def execute():
	"""(user, tenant) must be unique at the database level, not only checked
	in Python — see the hardening review section 18. frappe.db.add_unique
	is idempotent-safe to re-run (it checks whether the index already
	exists before creating it)."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_tenant_membership")
	frappe.db.add_unique("QTT Tenant Membership", ["user", "tenant"])
