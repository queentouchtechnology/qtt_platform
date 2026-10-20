"""Office Pulse Files moved off Nextcloud to QTT's own S3 storage (Garage, 20 Oct 2026): the Nextcloud accounts and
spaces QTT kept, and the passwords stored for them, go."""

import frappe


def execute():
	for dt in ("QTT Cloud Account", "QTT Cloud Space"):
		if frappe.db.table_exists(dt):
			frappe.db.delete(dt)
		frappe.delete_doc("DocType", dt, force=True, ignore_missing=True)
	frappe.db.delete("__Auth", {"doctype": ["in", ["QTT Cloud Account", "QTT Cloud Space"]]})
	frappe.db.delete("__Auth", {"doctype": "QTT Workplace Settings", "fieldname": "nextcloud_admin_password"})
