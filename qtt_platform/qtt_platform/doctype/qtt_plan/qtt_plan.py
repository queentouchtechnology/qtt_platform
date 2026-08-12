import frappe
from frappe import _
from frappe.model.document import Document


class QTTPlan(Document):
	def validate(self):
		self._validate_product_exists()
		self._reject_duplicate_feature_keys()

	def _validate_product_exists(self):
		if not frappe.db.exists("QTT Product", self.product):
			frappe.throw(_("Referenced product {0} does not exist.").format(self.product))

	def _reject_duplicate_feature_keys(self):
		seen = set()
		for row in self.features or []:
			if row.feature_key in seen:
				frappe.throw(
					_("Duplicate feature_key '{0}' in this plan.").format(row.feature_key),
					frappe.ValidationError,
				)
			seen.add(row.feature_key)
