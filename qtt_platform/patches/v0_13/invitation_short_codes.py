"""Pending invitations made before short codes get one (K7M2-QX9P); their long token keeps working too."""

import frappe


def execute():
	frappe.reload_doc("qtt_platform", "doctype", "qtt_invitation")
	from qtt_platform.api.invitation import _unique_code

	for name in frappe.get_all("QTT Invitation", filters={"status": "pending", "code": ["in", ["", None]]}, pluck="name"):
		frappe.db.set_value("QTT Invitation", name, "code", _unique_code(), update_modified=False)
