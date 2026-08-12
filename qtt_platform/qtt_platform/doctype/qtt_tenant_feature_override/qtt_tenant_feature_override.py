import frappe
from frappe import _
from frappe.model.document import Document


class QTTTenantFeatureOverride(Document):
	def validate(self):
		self._reject_duplicate()

	def _reject_duplicate(self):
		# Friendly pre-check before the database-level unique constraint —
		# see patches/v0_4/add_feature_override_unique_constraint.py.
		duplicate = frappe.db.exists(
			"QTT Tenant Feature Override",
			{
				"tenant": self.tenant,
				"product": self.product,
				"feature_key": self.feature_key,
				"name": ["!=", self.name or ""],
			},
		)
		if duplicate:
			frappe.throw(
				_("An override for '{0}' already exists for this tenant and product.").format(
					self.feature_key
				),
				frappe.DuplicateEntryError,
			)
