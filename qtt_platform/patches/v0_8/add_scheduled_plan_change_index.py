import frappe


def execute():
	"""SaaS lifecycle Phase E — supports the lookup shape the Phase I
	scheduled job (subscription/service.py::apply_due_scheduled_downgrades(),
	now built) needs: 'every QTT Product Subscription with a
	scheduled_plan whose effective date has arrived.' Not a
	uniqueness constraint — scheduled_plan/scheduled_plan_effective_date
	are plain fields on the single current subscription row per
	(tenant, product), already protected from duplication by the
	existing QTT Tenant Product Subscription Pointer constraint
	(patches/v0_3) — nothing new to enforce at the database level here,
	only a query-performance index."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_product_subscription")
	frappe.db.add_index("QTT Product Subscription", ["scheduled_plan_effective_date"])
