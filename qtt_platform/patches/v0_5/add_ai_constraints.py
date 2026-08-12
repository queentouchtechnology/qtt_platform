import frappe


def execute():
	"""Two independent constraints:

	- (tenant, product) unique on QTT Tenant Product Wallet — the
	  hardening review section 8 fix: the real database guarantee that
	  makes credit_service.deduct_credits()'s atomic UPDATE race-free.
	- (provider, model_id) unique on QTT AI Model — a provider shouldn't
	  have the same model_id registered twice.

	Plus indexes for the AI Credit Ledger / Usage Record hot paths
	(tenant + product scoped queries, per the hardening review section
	17/21's index strategy applied to every new tenant-scoped table).
	"""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_tenant_product_wallet")
	frappe.db.add_unique("QTT Tenant Product Wallet", ["tenant", "product"])

	frappe.reload_doc("qtt_platform", "doctype", "qtt_ai_model")
	frappe.db.add_unique("QTT AI Model", ["provider", "model_id"])

	frappe.reload_doc("qtt_platform", "doctype", "qtt_ai_credit_ledger")
	frappe.db.add_index("QTT AI Credit Ledger", ["tenant", "product"])

	frappe.reload_doc("qtt_platform", "doctype", "qtt_ai_usage_record")
	frappe.db.add_index("QTT AI Usage Record", ["tenant", "product"])
	frappe.db.add_index("QTT AI Usage Record", ["tenant", "user"])
