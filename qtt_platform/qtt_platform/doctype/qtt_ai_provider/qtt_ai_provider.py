import frappe
from frappe import _
from frappe.model.document import Document


class QTTAIProvider(Document):
	def validate(self):
		self._reject_multiple_fallbacks()

	def _reject_multiple_fallbacks(self):
		if not self.is_fallback:
			return
		other_fallback = frappe.db.exists(
			"QTT AI Provider", {"is_fallback": 1, "name": ["!=", self.name or ""]}
		)
		if other_fallback:
			frappe.throw(
				_("{0} is already the fallback provider — only one is allowed.").format(other_fallback),
				frappe.ValidationError,
			)
