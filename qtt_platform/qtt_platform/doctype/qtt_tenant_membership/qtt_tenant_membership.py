import frappe
from frappe import _
from frappe.model.document import Document


class QTTTenantMembership(Document):
	def validate(self):
		self._reject_duplicate()
		self._set_title()

	def _set_title(self):
		# Desk UI fix — Link fields pointing at this doctype otherwise show
		# the hashed document name. tenant_name is read fresh rather than
		# trusting any cached value, so renaming a tenant later corrects
		# every membership's title on its own next save (and via the
		# one-off backfill patch for rows that never get resaved).
		tenant_name = frappe.db.get_value("QTT Tenant", self.tenant, "tenant_name") or self.tenant
		self.membership_title = f"{self.user} — {tenant_name}"

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
