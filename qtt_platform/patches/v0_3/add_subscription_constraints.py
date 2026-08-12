import frappe


def execute():
	"""Two independent constraints, both from the hardening review:

	- (tenant, product) unique on the pointer table — section 9, the real
	  'at most one active subscription per (tenant, product)' guarantee.
	- (product, plan_code) unique on Plan — plan_code is only unique
	  within its own product, not globally (section 18).
	"""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_tenant_product_subscription_pointer")
	frappe.db.add_unique("QTT Tenant Product Subscription Pointer", ["tenant", "product"])

	frappe.reload_doc("qtt_platform", "doctype", "qtt_plan")
	frappe.db.add_unique("QTT Plan", ["product", "plan_code"])

	frappe.reload_doc("qtt_platform", "doctype", "qtt_product_subscription")
	frappe.db.add_index("QTT Product Subscription", ["tenant", "product"])
