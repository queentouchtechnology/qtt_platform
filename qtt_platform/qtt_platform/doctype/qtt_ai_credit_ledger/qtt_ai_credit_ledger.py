import frappe
from frappe import _
from frappe.model.document import Document


class QTTAICreditLedger(Document):
	def validate(self):
		self._validate_references_exist()

	def _validate_references_exist(self):
		# Defense-in-depth, not the primary access control — ledger writes
		# are internal service-code writes (ignore_permissions=True), never
		# directly user-writable. Still worth guarding against a bug that
		# would otherwise grant/consume credit against a nonexistent
		# tenant/product (hardening review section 7).
		if not frappe.db.exists("QTT Tenant", self.tenant):
			frappe.throw(_("Referenced tenant {0} does not exist.").format(self.tenant))
		if not frappe.db.exists("QTT Product", self.product):
			frappe.throw(_("Referenced product {0} does not exist.").format(self.product))
