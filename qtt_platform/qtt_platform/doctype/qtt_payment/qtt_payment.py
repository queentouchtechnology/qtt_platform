import frappe
from frappe import _
from frappe.model.document import Document


class QTTPayment(Document):
	def validate(self):
		self._validate_refund_shape()

	def _validate_refund_shape(self):
		if self.status == "refunded" and not self.refund_of:
			frappe.throw(_("A refunded payment must reference the payment it refunds."))
		if self.status == "succeeded" and self.refund_of:
			frappe.throw(_("refund_of should only be set on a refunded row."))
