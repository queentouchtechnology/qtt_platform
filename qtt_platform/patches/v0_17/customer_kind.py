"""The address book (PROJ-0016 C2): every customer made before suppliers and partners joined it is a Customer."""

import frappe


def execute():
	frappe.reload_doc("qtt_platform", "doctype", "qtt_customer")  # patches run before the model sync: add the field first
	frappe.db.sql("update `tabQTT Customer` set kind = 'Customer' where ifnull(kind, '') = ''")
