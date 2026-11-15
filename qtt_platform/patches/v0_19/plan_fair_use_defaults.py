"""PROJ-0024 (15 Nov 2026): the plan's fair use and top-up fields on QTT App Settings start with the owner's choices on
a site that already had the settings (Frappe doesn't fill a Single's new fields with their defaults). A field already
set in Desk — even to 0 (unlimited) — is kept."""

import frappe

from qtt_platform import free_use

VALUES = {"free_limit_newsletters": free_use.DEFAULT_LIMITS["newsletters"],
		  **{f"plan_limit_{k}": v for k, v in free_use.DEFAULT_PLAN_LIMITS.items()},
		  **{f"topup_{pack}_amount": amount for pack, (_n, _a, amount, _p) in free_use.TOPUPS.items()},
		  **{f"topup_{pack}_price": price for pack, (_n, _a, _amount, price) in free_use.TOPUPS.items()}}


def execute():
	if not frappe.db.exists("DocType", "QTT App Settings"):
		return
	frappe.reload_doc("qtt_platform", "doctype", "qtt_app_settings")
	have = set(frappe.db.sql_list("select field from `tabSingles` where doctype = 'QTT App Settings'"))
	for field, value in VALUES.items():
		if field not in have:
			frappe.db.set_single_value("QTT App Settings", field, value)
