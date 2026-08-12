import re

import frappe
from frappe import _
from frappe.model.document import Document

PRODUCT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


class QTTProduct(Document):
	def validate(self):
		self._validate_product_key_format()
		self._reject_duplicate_role_keys()

	def _validate_product_key_format(self):
		if not self.product_key or not PRODUCT_KEY_RE.match(self.product_key):
			frappe.throw(
				_("Product Key must be uppercase letters, digits, and underscores only (e.g. 'QMP_LMS')."),
				frappe.ValidationError,
			)

	def _reject_duplicate_role_keys(self):
		seen = set()
		for row in self.roles or []:
			if row.role_key in seen:
				frappe.throw(
					_("Duplicate role_key '{0}' in this product's role catalog.").format(row.role_key),
					frappe.ValidationError,
				)
			seen.add(row.role_key)

	def on_update(self):
		# The role catalog is read by QTT Product Access.validate() (Phase 3)
		# to check a submitted product_role is legitimate — if that check
		# ever caches the catalog per product, this is the place to
		# invalidate it. No cache exists yet in Phase 2, so this is
		# intentionally a no-op for now rather than a premature cache.
		pass
