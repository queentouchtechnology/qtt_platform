import frappe
from frappe import _
from frappe.model.document import Document


class QTTTenantMembership(Document):
	def validate(self):
		self._reject_duplicate()

	def _reject_duplicate(self):
		# Friendly, fast failure before the request ever reaches the
		# database-level unique constraint (see
		# patches/v0_1/add_tenant_membership_unique_constraint.py) — that
		# constraint is the actual concurrency-safe guarantee; this check
		# only makes the common, non-concurrent case fail with a clear
		# message instead of a raw DB integrity error.
		duplicate = frappe.db.exists(
			"QTT Tenant Membership",
			{"user": self.user, "tenant": self.tenant, "name": ["!=", self.name or ""]},
		)
		if duplicate:
			frappe.throw(
				_("{0} already has a membership in this tenant.").format(self.user),
				frappe.DuplicateEntryError,
			)
