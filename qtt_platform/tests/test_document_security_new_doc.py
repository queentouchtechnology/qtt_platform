"""
Bench-independent tests for
qtt_platform.document_security.resolve_tenant_for_new_doc() — added in
SaaS lifecycle Phase G as the first caller
(qmp_lms_bridge/roles.py) needed a way to resolve tenant from an
IN-MEMORY, possibly-unsaved document rather than re-querying the
database for it. Not yet imported by any other test file in this
project — safe as its own fresh fake-frappe environment (no cross-file
binding risk, unlike qtt_platform.audit/subscription.service/
billing.service, all documented elsewhere in this test suite).

Run manually from the qtt_platform repo root:

    python -m unittest qtt_platform.tests.test_document_security_new_doc -v
"""

import sys
import types
import unittest
from unittest import mock


def _install_fake_frappe():
	fake_frappe = types.ModuleType("frappe")
	fake_frappe._ = lambda s: s
	fake_frappe.PermissionError = Exception
	fake_frappe.throw = lambda msg, exc=None, **k: (_ for _ in ()).throw((exc or Exception)(msg))
	fake_frappe.get_meta = mock.Mock()
	fake_frappe.db = types.SimpleNamespace(get_value=mock.Mock(return_value=None))
	fake_frappe.cache = mock.Mock(
		return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
	)
	fake_frappe.get_hooks = mock.Mock(return_value={})
	sys.modules["frappe"] = fake_frappe
	return fake_frappe


fake_frappe = _install_fake_frappe()

from qtt_platform import document_security  # noqa: E402


def _fake_doc(doctype, **fields):
	doc = mock.Mock(doctype=doctype)
	doc.get = lambda key: fields.get(key)
	return doc


class ResolveTenantForNewDocTest(unittest.TestCase):
	def test_direct_tenant_field_read_from_the_in_memory_doc(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: f == "tenant"))
		doc = _fake_doc("LMS Course", tenant="tenant-1")
		self.assertEqual(document_security.resolve_tenant_for_new_doc(doc), "tenant-1")

	def test_never_queries_the_db_for_the_doc_itself(self):
		# The whole point of this function: for a doctype with a direct
		# tenant field, it must never call frappe.db.get_value(doctype,
		# doc.name, "tenant") — that would fail for an unsaved new doc.
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: f == "tenant"))
		fake_frappe.db.get_value = mock.Mock(side_effect=AssertionError("must not query DB for the doc itself"))
		doc = _fake_doc("LMS Course", tenant="tenant-1")
		self.assertEqual(document_security.resolve_tenant_for_new_doc(doc), "tenant-1")

	def test_static_parent_link_recurses_via_the_existing_parent_lookup(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: False))
		with mock.patch.object(
			document_security, "_get_static_parent_link", return_value=("course", "LMS Course")
		):
			with mock.patch.object(document_security, "_get_dynamic_parent_link", return_value=None):
				with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-1") as resolve_mock:
					doc = _fake_doc("Course Chapter", course="course-1")
					result = document_security.resolve_tenant_for_new_doc(doc)
		self.assertEqual(result, "tenant-1")
		resolve_mock.assert_called_once_with("LMS Course", "course-1")

	def test_dynamic_parent_link_reads_both_fields_off_the_doc(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: False))
		with mock.patch.object(document_security, "_get_dynamic_parent_link", return_value=("reference_doctype", "reference_docname")):
			with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-1") as resolve_mock:
				doc = _fake_doc("Discussion Topic", reference_doctype="LMS Batch", reference_docname="batch-1")
				result = document_security.resolve_tenant_for_new_doc(doc)
		self.assertEqual(result, "tenant-1")
		resolve_mock.assert_called_once_with("LMS Batch", "batch-1")

	def test_returns_none_when_parent_link_field_is_blank(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: False))
		with mock.patch.object(document_security, "_get_static_parent_link", return_value=("course", "LMS Course")):
			with mock.patch.object(document_security, "_get_dynamic_parent_link", return_value=None):
				doc = _fake_doc("Course Chapter", course=None)
				self.assertIsNone(document_security.resolve_tenant_for_new_doc(doc))

	def test_returns_none_when_doctype_is_ungoverned(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: False))
		with mock.patch.object(document_security, "_get_static_parent_link", return_value=None):
			with mock.patch.object(document_security, "_get_dynamic_parent_link", return_value=None):
				doc = _fake_doc("Some Unrelated Doctype")
				self.assertIsNone(document_security.resolve_tenant_for_new_doc(doc))


if __name__ == "__main__":
	unittest.main()
