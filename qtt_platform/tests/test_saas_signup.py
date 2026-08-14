"""
Bench-independent tests for qtt_platform.api.saas / qtt_platform.errors —
verifies the pure logic (input validation, slug generation, error-code
mapping, retry-on-collision behaviour) without a real Frappe bench,
database, or site, by installing a minimal fake `frappe` module before
import — same technique qmp_lms_bridge/tests/test_install.py established
for this project. Only `frappe` itself is faked; qtt_platform.errors,
qtt_platform.audit, and qtt_platform.subscription.service are imported
for real (they're already-reviewed, pre-existing modules — nothing here
needs to fake them, only avoid needing a live database underneath them).

What this file does NOT cover: the actual end-to-end DB-backed signup
flow (creating a real User/Tenant/Membership/Subscription/Product Access
row and confirming the database's own unique constraints fire under real
concurrency). See test_saas_signup_integration.py in this same directory
for that — a real FrappeTestCase, not executed this session (no bench
access), for whoever next has one to run.

qtt_platform.user_provisioning.create_user() (used internally by
signup() via _provision_user, since Phase F extracted it for
api.invitation.accept_invitation() to reuse too) is deliberately tested
in test_billing_subscriptions.py instead of here, even though it's
signup()'s own dependency — that file imports first alphabetically
under `discover`, so it's what actually binds user_provisioning's own
`import frappe` reference; testing it here as well would silently use a
STALE fake_frappe left over from whichever file's tests ran last, not
this file's own carefully-configured one (this was an actual, reproduced
failure while building Phase F, not a hypothetical).

Run manually from the qtt_platform repo root:

    python -m unittest qtt_platform.tests.test_saas_signup -v
"""

import sys
import types
import unittest
from unittest import mock


def _install_fake_frappe():
	class _ValidationError(Exception):
		pass

	class _DuplicateEntryError(_ValidationError):
		pass

	class _UniqueValidationError(_ValidationError):
		pass

	class _PermissionError(Exception):
		pass

	def _throw(msg, exc=None, **kwargs):
		raise (exc or _ValidationError)(msg)

	fake_frappe = types.ModuleType("frappe")
	fake_frappe.ValidationError = _ValidationError
	fake_frappe.DuplicateEntryError = _DuplicateEntryError
	fake_frappe.UniqueValidationError = _UniqueValidationError
	fake_frappe.PermissionError = _PermissionError
	fake_frappe.throw = _throw
	fake_frappe._ = lambda s: s
	fake_frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	fake_frappe.db = types.SimpleNamespace(
		get_value=mock.Mock(return_value=None),
		exists=mock.Mock(return_value=False),
		set_value=mock.Mock(),
	)
	fake_frappe.get_doc = mock.Mock()
	fake_frappe.get_all = mock.Mock(return_value=[])
	fake_frappe.log_error = mock.Mock()
	fake_frappe.get_traceback = mock.Mock(return_value="")
	fake_frappe.session = types.SimpleNamespace(user="Guest")
	fake_frappe.local = types.SimpleNamespace(request_ip=None)

	# A real submodule import (`from frappe.utils import add_days, ...`, in
	# qtt_platform.subscription.service) needs frappe.utils registered in
	# sys.modules, not just set as an attribute on the fake `frappe` module
	# — a plain attribute is enough for `import frappe; frappe.utils.x()`
	# but not for `from frappe.utils import x`.
	fake_frappe_utils = types.ModuleType("frappe.utils")
	fake_frappe_utils.add_days = lambda d, n: d
	fake_frappe_utils.now_datetime = lambda: "2026-08-12 00:00:00"
	fake_frappe_utils.today = lambda: "2026-08-12"
	fake_frappe.utils = fake_frappe_utils

	# qtt_platform.user_provisioning imports frappe.utils.password
	# directly (see that module's own docstring) — needed here too so
	# this file's own _install_fake_frappe() is self-sufficient if run
	# in isolation, even though test_billing_subscriptions.py is what
	# actually binds user_provisioning's `frappe` reference under
	# `discover` (see this file's module docstring).
	fake_frappe_utils_password = types.ModuleType("frappe.utils.password")
	fake_frappe_utils_password.update_password = mock.Mock()
	fake_frappe_utils.password = fake_frappe_utils_password

	sys.modules["frappe"] = fake_frappe
	sys.modules["frappe.utils"] = fake_frappe_utils
	sys.modules["frappe.utils.password"] = fake_frappe_utils_password
	return fake_frappe


fake_frappe = _install_fake_frappe()

# Real modules, imported against the fake frappe above — see module
# docstring for why these are NOT faked.
from qtt_platform.api import saas  # noqa: E402
from qtt_platform.errors import QttApiError, fail, ok  # noqa: E402


class SlugifyTest(unittest.TestCase):
	def test_basic(self):
		self.assertEqual(saas._slugify("John Academy"), "john-academy")

	def test_strips_punctuation(self):
		self.assertEqual(saas._slugify("Sathish & Co. Pvt. Ltd.!!"), "sathish-co-pvt-ltd")

	def test_blank_falls_back(self):
		self.assertEqual(saas._slugify("   "), "tenant")


class ValidateSignupInputTest(unittest.TestCase):
	def test_valid_input_does_not_raise(self):
		saas._validate_signup_input("John Doe", "john@example.com", "StrongPassword123!", "John Academy")

	def test_missing_full_name(self):
		with self.assertRaises(QttApiError) as ctx:
			saas._validate_signup_input("  ", "john@example.com", "StrongPassword123!", "John Academy")
		self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

	def test_missing_organization(self):
		with self.assertRaises(QttApiError) as ctx:
			saas._validate_signup_input("John Doe", "john@example.com", "StrongPassword123!", "")
		self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

	def test_invalid_email(self):
		with self.assertRaises(QttApiError) as ctx:
			saas._validate_signup_input("John Doe", "not-an-email", "StrongPassword123!", "John Academy")
		self.assertEqual(ctx.exception.code, "INVALID_EMAIL")

	def test_weak_password(self):
		with self.assertRaises(QttApiError) as ctx:
			saas._validate_signup_input("John Doe", "john@example.com", "short", "John Academy")
		self.assertEqual(ctx.exception.code, "WEAK_PASSWORD")


class ResolveProductTest(unittest.TestCase):
	def test_unknown_product(self):
		fake_frappe.db.get_value = mock.Mock(return_value=None)
		with self.assertRaises(QttApiError) as ctx:
			saas._resolve_product("QTT_HRMS")
		self.assertEqual(ctx.exception.code, "INVALID_PRODUCT")

	def test_disabled_product(self):
		fake_frappe.db.get_value = mock.Mock(
			return_value=types.SimpleNamespace(name="QMP_LMS", status="disabled")
		)
		with self.assertRaises(QttApiError) as ctx:
			saas._resolve_product("QMP_LMS")
		self.assertEqual(ctx.exception.code, "INVALID_PRODUCT")

	def test_active_product_resolves(self):
		fake_frappe.db.get_value = mock.Mock(
			return_value=types.SimpleNamespace(name="QMP_LMS", status="active")
		)
		product = saas._resolve_product("QMP_LMS")
		self.assertEqual(product.name, "QMP_LMS")


class ResolvePlanTest(unittest.TestCase):
	def test_missing_plan_key(self):
		with self.assertRaises(QttApiError) as ctx:
			saas._resolve_plan("QMP_LMS", None)
		self.assertEqual(ctx.exception.code, "INVALID_PLAN")

	def test_unknown_plan_key(self):
		fake_frappe.db.get_value = mock.Mock(return_value=None)
		with self.assertRaises(QttApiError) as ctx:
			saas._resolve_plan("QMP_LMS", "NOT_A_PLAN")
		self.assertEqual(ctx.exception.code, "INVALID_PLAN")

	def test_known_plan_key_resolves(self):
		fake_frappe.db.get_value = mock.Mock(return_value="plan-hash-1")
		fake_plan = types.SimpleNamespace(name="plan-hash-1", plan_code="STARTER")
		fake_frappe.get_doc = mock.Mock(return_value=fake_plan)
		plan = saas._resolve_plan("QMP_LMS", "STARTER")
		self.assertEqual(plan.plan_code, "STARTER")


class ValidateLocaleRefsTest(unittest.TestCase):
	def test_blank_values_are_skipped(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		saas._validate_locale_refs(None, None)  # must not raise

	def test_unknown_country_raises(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		with self.assertRaises(QttApiError) as ctx:
			saas._validate_locale_refs("Narnia", None)
		self.assertEqual(ctx.exception.code, "INVALID_COUNTRY")

	def test_unknown_language_raises(self):
		fake_frappe.db.exists = mock.Mock(side_effect=[True, False])
		with self.assertRaises(QttApiError) as ctx:
			saas._validate_locale_refs("India", "xx")
		self.assertEqual(ctx.exception.code, "INVALID_LANGUAGE")

	def test_known_values_pass(self):
		fake_frappe.db.exists = mock.Mock(return_value=True)
		saas._validate_locale_refs("India", "en")  # must not raise


class CreateTenantTest(unittest.TestCase):
	def test_retries_slug_on_collision_then_succeeds(self):
		fake_tenant = mock.Mock()
		# First two attempts collide, third succeeds.
		fake_tenant.insert.side_effect = [
			fake_frappe.UniqueValidationError("slug taken"),
			fake_frappe.UniqueValidationError("slug taken"),
			None,
		]
		fake_frappe.get_doc = mock.Mock(return_value=fake_tenant)
		result = saas._create_tenant("owner@example.com", "John Academy", "India", "en")
		self.assertIs(result, fake_tenant)
		self.assertEqual(fake_tenant.insert.call_count, 3)
		# Confirm the slug actually changed across retries, not the same
		# value re-submitted three times.
		slugs_tried = [call.args[0]["slug"] if call.args else None for call in fake_frappe.get_doc.call_args_list]
		self.assertEqual(slugs_tried, ["john-academy", "john-academy-2", "john-academy-3"])

	def test_exhausting_retries_raises_internal_error(self):
		fake_tenant = mock.Mock()
		fake_tenant.insert.side_effect = fake_frappe.UniqueValidationError("slug taken")
		fake_frappe.get_doc = mock.Mock(return_value=fake_tenant)
		with self.assertRaises(QttApiError) as ctx:
			saas._create_tenant("owner@example.com", "John Academy", None, None)
		self.assertEqual(ctx.exception.code, "INTERNAL_ERROR")
		self.assertEqual(fake_tenant.insert.call_count, saas._MAX_SLUG_RETRIES)


class ErrorEnvelopeTest(unittest.TestCase):
	def test_ok_shape(self):
		self.assertEqual(ok({"a": 1}), {"success": True, "data": {"a": 1}})
		self.assertEqual(ok(), {"success": True, "data": {}})

	def test_fail_shape(self):
		self.assertEqual(
			fail("INVALID_EMAIL", "bad email"),
			{"success": False, "error": {"code": "INVALID_EMAIL", "message": "bad email"}},
		)

	def test_qtt_api_error_carries_code_and_message(self):
		exc = QttApiError("PLAN_LIMIT_REACHED", "Student limit reached.")
		self.assertEqual(exc.code, "PLAN_LIMIT_REACHED")
		self.assertEqual(str(exc), "Student limit reached.")


if __name__ == "__main__":
	unittest.main()
