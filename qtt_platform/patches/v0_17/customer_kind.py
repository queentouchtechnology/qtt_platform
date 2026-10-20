"""The address book (PROJ-0016 C2): every customer made before suppliers and partners joined it is a Customer."""

import frappe


def execute():
	frappe.db.sql("update `tabQTT Customer` set kind = 'Customer' where ifnull(kind, '') = ''")
