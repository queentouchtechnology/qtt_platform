"""Explore QTT OS: what each app does, a line each (QTT Product › What it does). Filled once; edited in Desk after."""

import frappe

HIGHLIGHTS = {
	"QTT_ORBITRA": "Bills and POS on your phone\nStock and low-stock alerts\nPurchases and suppliers\nAccounts and GST reports\nMore than one store or branch",
	"QTT_ONBOX": "WhatsApp, website chat, Facebook, Instagram and email in one inbox\nYour whole team answers together\nAI replies when you're busy\nCustomer history in one place",
	"QTT_OFFICE_PULSE": "Attendance with GPS check-in\nLeave requests and approvals\nExpenses and claims\nPayroll and payslips\nHoliday calendar for your team",
}


def execute():
	frappe.reload_doc("qtt_platform", "doctype", "qtt_product")  # the field first (these patches run before the sync)
	for key, text in HIGHLIGHTS.items():
		if frappe.db.exists("QTT Product", key) and not frappe.db.get_value("QTT Product", key, "highlights"):
			frappe.db.set_value("QTT Product", key, "highlights", text, update_modified=False)
