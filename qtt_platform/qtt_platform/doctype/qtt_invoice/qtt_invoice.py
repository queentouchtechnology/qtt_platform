import frappe
from frappe import _
from frappe.model.document import Document


class QTTInvoice(Document):
	def validate(self):
		self._validate_amount_matches_items()
		self._validate_items_same_tenant()
		self._guard_frozen_after_draft()

	def _validate_amount_matches_items(self):
		items_total = sum((row.amount or 0) for row in self.items or [])
		if self.items and round(items_total, 2) != round(self.amount or 0, 2):
			frappe.throw(
				_("Invoice amount ({0}) must equal the sum of its line items ({1}).").format(
					self.amount, items_total
				),
				frappe.ValidationError,
			)

	def _validate_items_same_tenant(self):
		# Cross-reference guard, hardening review section 7 — every
		# subscription an invoice bills must belong to the same tenant as
		# the invoice itself.
		for row in self.items or []:
			sub_tenant = frappe.db.get_value("QTT Product Subscription", row.subscription, "tenant")
			if sub_tenant and sub_tenant != self.tenant:
				frappe.throw(
					_("Line item subscription {0} does not belong to this invoice's tenant.").format(
						row.subscription
					),
					frappe.ValidationError,
				)

	def _guard_frozen_after_draft(self):
		# Amount/items are fixed once an invoice leaves draft — hardening
		# review section 11. System Manager retains an emergency edit path
		# (e.g. correcting a genuine data-entry mistake before payment);
		# nothing in the normal billing flow ever edits a non-draft invoice.
		if self.is_new():
			return
		previous_status = frappe.db.get_value("QTT Invoice", self.name, "status")
		if previous_status and previous_status != "draft" and "System Manager" not in frappe.get_roles():
			previous_amount = frappe.db.get_value("QTT Invoice", self.name, "amount")
			if previous_amount != self.amount:
				frappe.throw(_("A non-draft invoice's amount cannot be changed."), frappe.PermissionError)
