import re

import frappe
from frappe import _
from frappe.model.document import Document

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class QTTTenant(Document):
	def validate(self):
		self._normalize_slug()
		self._validate_slug_format()

	def _normalize_slug(self):
		if self.slug:
			self.slug = self.slug.strip().lower()

	def _validate_slug_format(self):
		if not self.slug or not SLUG_RE.match(self.slug):
			frappe.throw(
				_("Slug must be lowercase letters, numbers, and hyphens only (e.g. 'abc-academy')."),
				frappe.ValidationError,
			)

	def before_insert(self):
		# A tenant with no bootstrap membership is an unrecoverable dead end
		# (no one could ever administer it) — the whitelisted create_tenant
		# API is responsible for creating the Tenant Owner membership in the
		# same transaction as this insert. This controller only guards that
		# owner_user is set; it does not create the membership itself, to
		# keep this doctype's own responsibility narrow (see api/tenant.py).
		if not self.owner_user:
			frappe.throw(_("A tenant must have an owner_user set at creation."))
