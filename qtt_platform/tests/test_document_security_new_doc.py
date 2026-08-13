"""
Bench-independent tests for qtt_platform.document_security — SaaS
lifecycle Phase G added resolve_tenant_for_new_doc() here (see that
class's own docstring); Phase J (the dedicated test-completion phase)
extends this file to cover the REST of the module's own functions
(resolve_tenant_for_doc, require_document_tenant_and_product,
require_same_tenant_reference, assert_tenant_access) — these are the
actual mechanism behind "tenant isolation" / "cross-tenant security"
from that phase's own checklist, and had never been unit-tested in
isolation anywhere in this project before now, despite being exercised
indirectly (via has_permission/permission_query_conditions,
qmp_lms_bridge/roles.py, etc.) since Phase 3/7/10.

document_security still is not imported by any other test file in this
project, so this remains its own fresh fake-frappe environment — no
cross-file binding risk for `frappe` itself. Its sibling calls
(require_product_access, resolve_product_for_doctype,
resolve_active_tenant) ARE imported by other test files by this point
(via api.dashboard/api.subscription's own import chains in
test_billing_subscriptions.py) and so COULD be stale-bound if this file
called them for real; every test below instead patches them directly on
`document_security`'s own namespace (`mock.patch.object(document_security,
"require_product_access", ...)`) — patching "where used," the same
technique already used throughout this whole test suite — which sidesteps
that risk entirely regardless of which fake_frappe those sibling modules
themselves ended up bound to.

Run manually from the qtt_platform repo root:

    python -m unittest qtt_platform.tests.test_document_security_new_doc -v
"""

import sys
import types
import unittest
from unittest import mock


def _install_fake_frappe():
	class _ValidationError(Exception):
		pass

	class _PermissionError(Exception):
		pass

	fake_frappe = types.ModuleType("frappe")
	fake_frappe._ = lambda s: s
	fake_frappe.PermissionError = _PermissionError
	fake_frappe.ValidationError = _ValidationError
	fake_frappe.throw = lambda msg, exc=None, **k: (_ for _ in ()).throw((exc or _ValidationError)(msg))
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


class ResolveTenantForDocTest(unittest.TestCase):
	"""The DB-lookup-by-name sibling of resolve_tenant_for_new_doc() —
	the function has_permission/permission_query_conditions hooks are
	actually built on."""

	def test_direct_tenant_field_queries_the_db_by_name(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: f == "tenant"))
		fake_frappe.db.get_value = mock.Mock(return_value="tenant-1")
		result = document_security.resolve_tenant_for_doc("LMS Course", "course-1")
		self.assertEqual(result, "tenant-1")
		fake_frappe.db.get_value.assert_called_once_with("LMS Course", "course-1", "tenant")

	def test_static_parent_link_recurses_to_a_real_tenant_field(self):
		# Level 1 (Course Chapter): no tenant field, has a static parent
		# link. Level 2 (LMS Course, the RECURSIVE call): has a direct
		# tenant field. Exercises the real recursion, not a mocked one.
		meta_by_doctype = {
			"Course Chapter": mock.Mock(has_field=lambda f: False),
			"LMS Course": mock.Mock(has_field=lambda f: f == "tenant"),
		}
		fake_frappe.get_meta = mock.Mock(side_effect=lambda dt: meta_by_doctype[dt])
		fake_frappe.db.get_value = mock.Mock(
			side_effect=[
				"course-1",  # Course Chapter's own `course` field value
				"tenant-1",  # LMS Course's own `tenant` field value (the recursive call)
			]
		)
		with mock.patch.object(
			document_security,
			"_get_static_parent_link",
			side_effect=lambda dt: ("course", "LMS Course") if dt == "Course Chapter" else None,
		):
			with mock.patch.object(document_security, "_get_dynamic_parent_link", return_value=None):
				result = document_security.resolve_tenant_for_doc("Course Chapter", "chapter-1")
		self.assertEqual(result, "tenant-1")

	def test_returns_none_for_a_doctype_and_name_with_no_link_at_all(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: False))
		with mock.patch.object(document_security, "_get_static_parent_link", return_value=None):
			with mock.patch.object(document_security, "_get_dynamic_parent_link", return_value=None):
				self.assertIsNone(document_security.resolve_tenant_for_doc("Some Unrelated Doctype", "x-1"))

	def test_returns_none_when_the_document_itself_does_not_exist(self):
		fake_frappe.get_meta = mock.Mock(return_value=mock.Mock(has_field=lambda f: f == "tenant"))
		fake_frappe.db.get_value = mock.Mock(return_value=None)
		self.assertIsNone(document_security.resolve_tenant_for_doc("LMS Course", "does-not-exist"))


class RequireDocumentTenantAndProductTest(unittest.TestCase):
	"""The core cross-tenant enforcement function — "Tenant A user trying
	to access Tenant B's document must be denied," directly."""

	def test_matching_tenant_and_registered_product_delegates_to_product_access(self):
		with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-1"):
			with mock.patch.object(document_security, "resolve_product_for_doctype", return_value="QMP_LMS"):
				with mock.patch.object(document_security, "require_product_access") as require_access_mock:
					document_security.require_document_tenant_and_product("LMS Course", "course-1", "tenant-1")
		require_access_mock.assert_called_once_with("tenant-1", "QMP_LMS", user=None)

	def test_cross_tenant_document_is_rejected_before_any_product_check(self):
		with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-B"):
			with mock.patch.object(document_security, "resolve_product_for_doctype") as resolve_product_mock:
				with mock.patch.object(document_security, "require_product_access") as require_access_mock:
					with self.assertRaises(fake_frappe.PermissionError):
						document_security.require_document_tenant_and_product(
							"LMS Course", "course-owned-by-tenant-b", "tenant-A"
						)
		resolve_product_mock.assert_not_called()
		require_access_mock.assert_not_called()

	def test_unregistered_product_is_a_clean_noop_not_a_crash(self):
		# A tenant-scoped doctype with no product registration at all —
		# resolve_product_for_doctype() returns None. Nothing further to
		# check; must not raise or call require_product_access with None.
		with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-1"):
			with mock.patch.object(document_security, "resolve_product_for_doctype", return_value=None):
				with mock.patch.object(document_security, "require_product_access") as require_access_mock:
					document_security.require_document_tenant_and_product("Some Doctype", "x-1", "tenant-1")
		require_access_mock.assert_not_called()


class RequireSameTenantReferenceTest(unittest.TestCase):
	"""The cross-tenant reference-smuggling guard qmp_lms_bridge/
	validators.py's own doc_events all call."""

	def test_same_tenant_reference_passes(self):
		with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-1"):
			document_security.require_same_tenant_reference(("LMS Course", "course-1"), tenant="tenant-1")  # must not raise

	def test_cross_tenant_reference_is_rejected(self):
		with mock.patch.object(document_security, "resolve_tenant_for_doc", return_value="tenant-B"):
			with self.assertRaises(fake_frappe.ValidationError):
				document_security.require_same_tenant_reference(("LMS Course", "course-owned-by-b"), tenant="tenant-A")

	def test_blank_reference_is_skipped_not_flagged(self):
		with mock.patch.object(document_security, "resolve_tenant_for_doc") as resolve_mock:
			document_security.require_same_tenant_reference(("LMS Course", None), tenant="tenant-1")  # must not raise
		resolve_mock.assert_not_called()

	def test_multiple_refs_all_checked_first_violation_wins(self):
		def _resolve(doctype, name):
			return "tenant-1" if name == "good-ref" else "tenant-B"

		with mock.patch.object(document_security, "resolve_tenant_for_doc", side_effect=_resolve):
			with self.assertRaises(fake_frappe.ValidationError):
				document_security.require_same_tenant_reference(
					("LMS Course", "good-ref"), ("LMS Batch", "bad-ref"), tenant="tenant-1"
				)


class AssertTenantAccessTest(unittest.TestCase):
	def test_no_active_tenant_is_rejected(self):
		with mock.patch.object(document_security, "resolve_active_tenant", return_value=None):
			with self.assertRaises(fake_frappe.PermissionError):
				document_security.assert_tenant_access("LMS Course", "course-1")

	def test_delegates_to_require_document_tenant_and_product_with_the_resolved_tenant(self):
		with mock.patch.object(document_security, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(document_security, "require_document_tenant_and_product") as require_mock:
				document_security.assert_tenant_access("LMS Course", "course-1", user="someone@example.com")
		require_mock.assert_called_once_with("LMS Course", "course-1", "tenant-1", user="someone@example.com")


class BuildLinkRegistryTest(unittest.TestCase):
	"""Regression coverage for a real bug caught via live production
	testing (Part C-J multi-tenant workflow verification): frappe.get_hooks()
	wraps EVERY key's value in a list of per-declaring-app contributions,
	even when the declared value is itself list/tuple-shaped — confirmed
	live: frappe.get_hooks("tenant_parent_links") returned
	{"Course Chapter": [["course", "LMS Course"]]}, a list CONTAINING the
	declared 2-element list, not the bare 2-element list. The previous
	code's "which shape is it" branching treated the outer dict as
	already-merged and left each value doubly-nested, so
	_get_static_parent_link()/_get_dynamic_parent_link() returned a
	1-tuple containing a list instead of unpacking to (field, doctype) —
	silently breaking tenant resolution for every hook-only doctype
	(Course Chapter, LMS Batch Timetable, LMS Timetable Legend,
	Discussion Topic) until caught by an actual real-site check. No
	existing test caught this because ResolveTenantForDocTest mocks
	_get_static_parent_link directly, never exercising the registry-
	building code these tests cover."""

	def setUp(self):
		# Fresh cache mock per test — _get_static_parent_link/
		# _get_dynamic_parent_link only call _build_link_registry() when
		# frappe.cache().get_value() reports a miss.
		fake_frappe.cache = mock.Mock(
			return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
		)

	def test_static_parent_link_unwraps_the_real_list_wrapped_hook_shape(self):
		fake_frappe.get_hooks = mock.Mock(
			return_value={"Course Chapter": [["course", "LMS Course"]], "LMS Batch Timetable": [["batch", "LMS Batch"]]}
		)
		result = document_security._get_static_parent_link("Course Chapter")
		self.assertEqual(result, ("course", "LMS Course"))

	def test_dynamic_parent_link_unwraps_the_real_list_wrapped_hook_shape(self):
		fake_frappe.get_hooks = mock.Mock(
			return_value={"Discussion Topic": [["reference_doctype", "reference_docname"]]}
		)
		result = document_security._get_dynamic_parent_link("Discussion Topic")
		self.assertEqual(result, ("reference_doctype", "reference_docname"))

	def test_unregistered_doctype_returns_none(self):
		fake_frappe.get_hooks = mock.Mock(return_value={"Course Chapter": [["course", "LMS Course"]]})
		self.assertIsNone(document_security._get_static_parent_link("Some Other Doctype"))


if __name__ == "__main__":
	unittest.main()
