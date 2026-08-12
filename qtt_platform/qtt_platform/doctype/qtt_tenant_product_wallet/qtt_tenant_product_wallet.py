import frappe
from frappe import _
from frappe.model.document import Document


class QTTTenantProductWallet(Document):
	"""No role holds write/create/delete DocPerm here — every write goes
	through qtt_platform.ai.services.credit_service with
	ignore_permissions=True. validate() is the integrity backstop, not the
	access-control layer (same pattern as QTT Tenant Product Subscription
	Pointer, Phase 4)."""

	def validate(self):
		self._validate_references_exist()
		self._reject_negative_balance()

	def _validate_references_exist(self):
		if not frappe.db.exists("QTT Tenant", self.tenant):
			frappe.throw(_("Referenced tenant {0} does not exist.").format(self.tenant))
		if not frappe.db.exists("QTT Product", self.product):
			frappe.throw(_("Referenced product {0} does not exist.").format(self.product))

	def _reject_negative_balance(self):
		# NOTE: this only guards ORM-based saves (doc.insert()/doc.save()).
		# credit_service.deduct_credits() writes via raw frappe.db.sql(),
		# which does NOT run validate() at all — its own UPDATE ... WHERE
		# balance >= amount clause is the actual, independent mechanism
		# that prevents a negative balance on that path. This check exists
		# for the other write path: the initial zero-balance insert in
		# _ensure_wallet(), and any future direct Desk-UI edit by an
		# emergency System Manager session.
		if self.balance is not None and self.balance < 0:
			frappe.throw(_("Wallet balance cannot go negative."), frappe.ValidationError)
