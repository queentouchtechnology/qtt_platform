import frappe
from frappe import _
from frappe.model.document import Document

from qtt_platform.product.registry import get_product_roles


class QTTProductAccess(Document):
	def validate(self):
		self._sync_tenant_from_membership()
		self._validate_membership_tenant_match()
		self._validate_product_role()
		self._reject_duplicate()

	def _sync_tenant_from_membership(self):
		# `tenant` is denormalized for query/index performance (see the
		# hardening review section 18) — it is always derived from the
		# membership, never independently trusted, even if a caller
		# supplied a different value.
		membership_tenant = frappe.db.get_value("QTT Tenant Membership", self.membership, "tenant")
		if not membership_tenant:
			frappe.throw(_("Referenced membership {0} does not exist.").format(self.membership))
		self.tenant = membership_tenant

	def _validate_membership_tenant_match(self):
		# Cross-tenant reference smuggling guard — hardening review
		# section 7. Redundant with _sync_tenant_from_membership above by
		# construction (tenant is always overwritten from the membership),
		# but kept as an explicit, readable assertion rather than relying
		# solely on the side effect of the sync step.
		membership_tenant = frappe.db.get_value("QTT Tenant Membership", self.membership, "tenant")
		if self.tenant != membership_tenant:
			frappe.throw(
				_("Product Access tenant must match the referenced membership's tenant."),
				frappe.ValidationError,
			)

	def _validate_product_role(self):
		product_status = frappe.db.get_value("QTT Product", self.product, "status")
		if product_status is None:
			frappe.throw(_("Referenced product {0} does not exist.").format(self.product))
		if product_status != "active":
			frappe.throw(_("Cannot grant access to a disabled product."), frappe.ValidationError)

		valid_roles = get_product_roles(self.product)
		if self.product_role not in valid_roles:
			frappe.throw(
				_("'{0}' is not a role {1} declares in its role catalog.").format(
					self.product_role, self.product
				),
				frappe.ValidationError,
			)

	def _reject_duplicate(self):
		# Friendly pre-check before the database-level unique constraint —
		# see patches/v0_2/add_product_access_unique_constraint.py. Same
		# pattern as QTT Tenant Membership's own duplicate guard.
		duplicate = frappe.db.exists(
			"QTT Product Access",
			{"membership": self.membership, "product": self.product, "name": ["!=", self.name or ""]},
		)
		if duplicate:
			frappe.throw(
				_("This membership already has an access record for this product."),
				frappe.DuplicateEntryError,
			)
