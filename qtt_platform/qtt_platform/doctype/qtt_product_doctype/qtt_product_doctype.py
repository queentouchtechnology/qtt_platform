import frappe
from frappe import _
from frappe.model.document import Document


class QTTProductDocType(Document):
	"""No role holds write/create/delete DocPerm on this doctype (see the
	.json permissions array) — every row is written by
	qtt_platform.product.registry functions with ignore_permissions=True,
	called only from a product's own install/uninstall hooks. validate()
	still runs on those writes and is the integrity backstop; it is not
	the access-control layer (DocPerm already is)."""

	def validate(self):
		self._validate_doctype_exists()

	def _validate_doctype_exists(self):
		if not self.doctype_name or not frappe.db.exists("DocType", self.doctype_name):
			frappe.throw(
				_("'{0}' is not a real, installed DocType.").format(self.doctype_name),
				frappe.ValidationError,
			)
