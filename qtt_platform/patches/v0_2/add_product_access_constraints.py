import frappe


def execute():
	"""Database-level guarantees for QTT Product Access — see the hardening
	review sections 4, 18, and 23. frappe.db.add_unique / add_index are
	both safe to re-run (they check whether the index already exists
	before creating it)."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_product_access")

	# (membership, product): one role per user per product per tenant.
	frappe.db.add_unique("QTT Product Access", ["membership", "product"])

	# (tenant, product) / (tenant, product, status): the hottest lookup in
	# the whole authorization engine — every tenant-scoped request that
	# touches a product-owned document calls require_product_access, which
	# queries exactly this shape.
	frappe.db.add_index("QTT Product Access", ["tenant", "product"])
	frappe.db.add_index("QTT Product Access", ["tenant", "product", "status"])
