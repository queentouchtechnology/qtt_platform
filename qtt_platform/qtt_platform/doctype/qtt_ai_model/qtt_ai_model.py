import frappe
from frappe import _
from frappe.model.document import Document


class QTTAIModel(Document):
	def validate(self):
		self._validate_provider_exists()
		self._reject_ambiguous_task_default()

	def _validate_provider_exists(self):
		if not frappe.db.exists("QTT AI Provider", self.provider):
			frappe.throw(_("Referenced provider {0} does not exist.").format(self.provider))

	def _reject_ambiguous_task_default(self):
		if not self.default_for_task:
			return
		other = frappe.db.exists(
			"QTT AI Model",
			{"default_for_task": self.default_for_task, "name": ["!=", self.name or ""]},
		)
		if other:
			frappe.throw(
				_("{0} is already the default model for task '{1}' — routing would be ambiguous.").format(
					other, self.default_for_task
				),
				frappe.ValidationError,
			)
