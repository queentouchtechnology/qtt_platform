import frappe
from frappe import _
from frappe.model.document import Document


class QTTSEOPlan(Document):
	def validate(self):
		for p in self.pages:
			if p.title and len(p.title) > 60:
				frappe.throw(_("{0}: the search title is {1} characters — up to 60.").format(p.page, len(p.title)))
			if p.description and not 110 <= len(p.description) <= 160:
				frappe.throw(_("{0}: the search description is {1} characters — 110 to 160.").format(p.page, len(p.description)))
