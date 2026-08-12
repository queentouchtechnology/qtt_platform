import frappe


def execute():
	"""Indexes for the billing tables' hot paths — gateway_reference's
	uniqueness on QTT Payment Transaction is already declared in that
	doctype's JSON ("unique": 1 on a single field is created automatically
	by `bench migrate`, unlike the composite constraints elsewhere in this
	app, which is why only these are needed as an explicit patch)."""
	for doctype_folder in ("qtt_invoice", "qtt_payment", "qtt_payment_transaction", "qtt_audit_log"):
		frappe.reload_doc("qtt_platform", "doctype", doctype_folder)

	frappe.db.add_index("QTT Invoice", ["tenant", "status"])
	frappe.db.add_index("QTT Payment", ["invoice"])
	frappe.db.add_index("QTT Payment Transaction", ["invoice"])
	frappe.db.add_index("QTT Audit Log", ["tenant", "occurred_at"])
	frappe.db.add_index("QTT Audit Log", ["target_doctype", "target_name"])
