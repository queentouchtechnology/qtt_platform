import re

import frappe
from frappe import _
from frappe.model.document import Document

from qtt_platform.product.registry import get_product_roles

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class QTTInvitation(Document):
	def validate(self):
		self._normalize_and_validate_email()
		self._validate_product_role()

	def _normalize_and_validate_email(self):
		if self.email:
			self.email = self.email.strip().lower()
		if not self.email or not _EMAIL_RE.match(self.email):
			frappe.throw(_("Enter a valid email address."), frappe.ValidationError)

	def _validate_product_role(self):
		# Same rule QTT Product Access.validate() already enforces —
		# reused, not reimplemented: product_role must be one of the
		# product's own declared role_key values, never a platform
		# hardcoded list (SaaS lifecycle Phase F: "Manager / Instructor /
		# Staff / Student" is QMP_LMS's own catalog, resolved generically
		# here, never named directly in this platform-agnostic doctype).
		if not self.product:
			if self.product_role:
				frappe.throw(_("product_role can only be set together with product."), frappe.ValidationError)
			return

		product_status = frappe.db.get_value("QTT Product", self.product, "status")
		if product_status is None:
			frappe.throw(_("Referenced product {0} does not exist.").format(self.product))
		if product_status != "active":
			frappe.throw(_("Cannot invite to a disabled product."), frappe.ValidationError)

		if not self.product_role:
			frappe.throw(_("product_role is required when product is set."), frappe.ValidationError)

		valid_roles = get_product_roles(self.product)
		if self.product_role not in valid_roles:
			frappe.throw(
				_("'{0}' is not a role {1} declares in its role catalog.").format(self.product_role, self.product),
				frappe.ValidationError,
			)
