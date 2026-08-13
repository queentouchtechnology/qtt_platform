"""
Bench-independent tests for qtt_platform.permissions.handlers — never
tested before this pass (confirmed: no other test file imports this
module). The has_permission() new-document branch is a real bug fix
found via live testing (Part C-J multi-tenant verification): see that
function's own docstring for the full story.

Self-contained fake-frappe install, same technique as
test_document_security_new_doc.py (this module isn't imported by any
other test file, so there's no cross-file fake-frappe binding risk).

Run manually from the qtt_platform repo root:

    python -m unittest qtt_platform.tests.test_permissions_handlers -v
"""

import sys
import types
import unittest
from unittest import mock


def _install_fake_frappe():
	class _PermissionError(Exception):
		pass

	fake_frappe = types.ModuleType("frappe")
	fake_frappe.PermissionError = _PermissionError
	fake_frappe._ = lambda s: s
	fake_frappe.throw = mock.Mock(side_effect=lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg)))
	fake_frappe.session = types.SimpleNamespace(user="someone@example.com")
	fake_frappe.db = types.SimpleNamespace(get_value=mock.Mock(return_value=None))
	fake_frappe.get_roles = mock.Mock(return_value=["All"])
	sys.modules["frappe"] = fake_frappe
	return fake_frappe


_install_fake_frappe()

from qtt_platform.permissions import handlers  # noqa: E402


class HasPermissionTest(unittest.TestCase):
	def test_no_active_tenant_is_denied(self):
		with mock.patch.object(handlers, "resolve_active_tenant", return_value=None):
			doc = mock.Mock(doctype="LMS Course")
			self.assertFalse(handlers.has_permission(doc))

	def test_new_document_uses_the_in_memory_resolver_not_a_db_lookup(self):
		# The regression this test exists for: a genuinely new
		# (not-yet-inserted) document has no database row for the
		# DB-lookup path to find — resolve_tenant_for_doc() would always
		# return None for it. resolve_tenant_for_new_doc() must be used
		# instead whenever doc.is_new() is true.
		doc = mock.Mock(doctype="Course Chapter")
		doc.is_new.return_value = True
		with mock.patch.object(handlers, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(handlers, "resolve_tenant_for_new_doc", return_value="tenant-1") as resolve_mock:
				with mock.patch.object(handlers, "resolve_product_for_doctype", return_value=None):
					result = handlers.has_permission(doc, permission_type="create")
		self.assertTrue(result)
		resolve_mock.assert_called_once_with(doc)

	def test_new_document_with_mismatched_tenant_is_denied(self):
		doc = mock.Mock(doctype="Course Chapter")
		doc.is_new.return_value = True
		with mock.patch.object(handlers, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(handlers, "resolve_tenant_for_new_doc", return_value="tenant-2"):
				result = handlers.has_permission(doc, permission_type="create")
		self.assertFalse(result)

	def test_new_document_also_checks_product_access_when_registered(self):
		doc = mock.Mock(doctype="LMS Course")
		doc.is_new.return_value = True
		with mock.patch.object(handlers, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(handlers, "resolve_tenant_for_new_doc", return_value="tenant-1"):
				with mock.patch.object(handlers, "resolve_product_for_doctype", return_value="QMP_LMS"):
					with mock.patch.object(
						handlers, "require_product_access", side_effect=handlers.frappe.PermissionError("nope")
					) as require_mock:
						result = handlers.has_permission(doc, permission_type="create")
		self.assertFalse(result)
		require_mock.assert_called_once_with("tenant-1", "QMP_LMS", user="someone@example.com")

	def test_existing_document_still_uses_the_db_lookup_path(self):
		doc = mock.Mock(doctype="LMS Course")
		doc.name = "course-1"
		doc.is_new.return_value = False
		with mock.patch.object(handlers, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(handlers, "require_document_tenant_and_product") as require_mock:
				result = handlers.has_permission(doc, permission_type="write")
		self.assertTrue(result)
		require_mock.assert_called_once_with("LMS Course", "course-1", "tenant-1", user="someone@example.com")

	def test_existing_document_denied_on_mismatch(self):
		doc = mock.Mock(doctype="LMS Course")
		doc.name = "course-1"
		doc.is_new.return_value = False
		with mock.patch.object(handlers, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(
				handlers, "require_document_tenant_and_product", side_effect=handlers.frappe.PermissionError("nope")
			):
				result = handlers.has_permission(doc, permission_type="write")
		self.assertFalse(result)


if __name__ == "__main__":
	unittest.main()
