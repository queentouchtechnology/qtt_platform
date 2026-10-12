"""
QTT Midnight: minimal borderless cards and 14px corners (app_defaults). Only
moves values still at the previous built-in defaults; Desk edits stay.
"""

import frappe


def execute():
	if not frappe.db.exists("QTT App Theme", "qtt-midnight"):
		return
	doc = frappe.get_doc("QTT App Theme", "qtt-midnight")
	changed = False
	if (doc.get("card_style") or "outlined") == "outlined":
		doc.card_style = "flat"
		changed = True
	if int(doc.get("corner_radius") or 12) == 12:
		doc.corner_radius = 14
		changed = True
	if changed:
		doc.save(ignore_permissions=True)
