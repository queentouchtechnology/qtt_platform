"""PROJ-0024: the free-use fields on QTT App Settings start with the owner's choices on a site that already had the
settings (Frappe doesn't fill a Single's new fields with their defaults): everyone gets all 8 apps, free use on, the
Standard limits, ₹1,999 / ₹19,990. Values already set in Desk are kept."""

import frappe

from qtt_platform import free_use

VALUES = {"all_apps_included": 1, "free_use_enabled": 1, "one_plan_monthly": 1999, "one_plan_yearly": 19990,
		  **{f"free_limit_{k}": v for k, v in free_use.DEFAULT_LIMITS.items()}}


def execute():
	if not frappe.db.exists("DocType", "QTT App Settings"):
		return
	frappe.reload_doc("qtt_platform", "doctype", "qtt_app_settings")
	if frappe.db.get_single_value("QTT App Settings", "free_limit_hr"):
		return  # already set (in Desk, or by hand on 14 Nov)
	for field, value in VALUES.items():
		frappe.db.set_single_value("QTT App Settings", field, value)
