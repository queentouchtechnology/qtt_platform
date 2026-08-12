import frappe


def execute():
	"""(tenant, product, feature_key) unique — at most one override per
	feature per tenant+product."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_tenant_feature_override")
	frappe.db.add_unique("QTT Tenant Feature Override", ["tenant", "product", "feature_key"])
