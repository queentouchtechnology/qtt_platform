"""
Real bench integration tests for qtt_platform.api.saas.signup() — requires
an actual Frappe site with frappe.tests.utils.FrappeTestCase available.
NOT executed as part of Phase A (no bench access during development); see
test_saas_signup.py in this same directory for the bench-independent
tests that WERE actually executed while building this phase.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_saas_signup_integration

Concurrency note (SaaS lifecycle brief, Part 40 — "two simultaneous
signup requests for the same email"): a true concurrent-request test
needs two separate Frappe request/DB connections, not two Python threads
sharing one frappe.local inside a single FrappeTestCase — that's what
Phase J is for for (a dedicated concurrency-test pass, likely via
`bench execute` scripts run as separate OS processes or a real HTTP load
tool against a running site). What test_saas_signup.py's
test_concurrent_duplicate_at_insert_time_is_mapped_cleanly already proves
bench-independently is narrower but still real: that OUR code correctly
translates the DB's own primary-key collision (frappe.DuplicateEntryError
on User.name) into a clean DUPLICATE_EMAIL response rather than a raw
traceback — the actual race-safety guarantee is Frappe/MySQL's, not
application logic, exactly like every other concurrency guarantee already
documented in this codebase.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from qtt_platform.api import saas

_TEST_EMAIL = "qtt-saas-signup-test@example.com"
_TEST_PRODUCT = "QMP_LMS"
_TEST_PLAN_CODE = "SIGNUP_TEST_STARTER"


class SaasSignupIntegrationTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._ensure_test_product_and_plan()

	@classmethod
	def _ensure_test_product_and_plan(cls):
		# QMP_LMS is normally registered by qmp_lms_bridge's install hook;
		# create it directly here too so this test file can also run on a
		# bare qtt_platform-only test site, without requiring
		# qmp_lms_bridge to be installed. Idempotent — safe if it already
		# exists for real.
		if not frappe.db.exists("QTT Product", _TEST_PRODUCT):
			frappe.get_doc(
				{
					"doctype": "QTT Product",
					"product_key": _TEST_PRODUCT,
					"display_name": "QMP LMS",
					"app_name": "lms",
					"status": "active",
					"roles": [
						{"role_key": "Manager", "role_name": "Manager"},
						{"role_key": "Instructor", "role_name": "Instructor"},
						{"role_key": "Staff", "role_name": "Staff"},
						{"role_key": "Student", "role_name": "Student"},
					],
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("QTT Plan", {"product": _TEST_PRODUCT, "plan_code": _TEST_PLAN_CODE}):
			frappe.get_doc(
				{
					"doctype": "QTT Plan",
					"plan_code": _TEST_PLAN_CODE,
					"product": _TEST_PRODUCT,
					"display_name": "Signup Test Plan",
					"base_price": 99,
					"billing_period": "monthly",
					"trial_days": 7,
					"is_public": 0,
				}
			).insert(ignore_permissions=True)

	def tearDown(self):
		# FrappeTestCase normally rolls back per-test, but User is
		# sometimes excluded from that rollback depending on site config
		# (see frappe's own test harness) — clean up explicitly rather
		# than assume.
		if frappe.db.exists("User", _TEST_EMAIL):
			frappe.delete_doc("User", _TEST_EMAIL, force=1, ignore_permissions=True)
		super().tearDown()

	def test_happy_path_creates_full_chain(self):
		result = saas.signup(
			full_name="Integration Test",
			email=_TEST_EMAIL,
			password="StrongPassword123!",
			organization_name="Integration Test Academy",
			country="India",
			language="en",
			product_key=_TEST_PRODUCT,
			plan_key=_TEST_PLAN_CODE,
		)

		self.assertTrue(result["success"], result)
		data = result["data"]

		self.assertEqual(data["user"], _TEST_EMAIL)
		self.assertEqual(data["tenant_role"], "Tenant Owner")
		self.assertEqual(data["product_role"], "Manager")
		self.assertEqual(data["subscription_status"], "trialing")
		self.assertIsNotNone(data["trial_ends_on"])

		# Never leak the password/hash back to the caller.
		self.assertNotIn("password", data)
		self.assertNotIn("new_password", data)

		membership = frappe.db.get_value(
			"QTT Tenant Membership", {"user": _TEST_EMAIL, "tenant": data["tenant"]}, ["tenant_role", "status"], as_dict=True
		)
		self.assertEqual(membership.tenant_role, "Tenant Owner")
		self.assertEqual(membership.status, "active")

		access = frappe.db.get_value(
			"QTT Product Access",
			{"tenant": data["tenant"], "product": _TEST_PRODUCT},
			["product_role", "status"],
			as_dict=True,
		)
		self.assertEqual(access.product_role, "Manager")
		self.assertEqual(access.status, "active")

		tenant_status = frappe.db.get_value("QTT Tenant", data["tenant"], "status")
		self.assertEqual(tenant_status, "trial")

	def test_duplicate_email_rejected(self):
		saas.signup(
			full_name="Integration Test",
			email=_TEST_EMAIL,
			password="StrongPassword123!",
			organization_name="Integration Test Academy",
			country="India",
			language="en",
			product_key=_TEST_PRODUCT,
			plan_key=_TEST_PLAN_CODE,
		)
		result = saas.signup(
			full_name="Someone Else",
			email=_TEST_EMAIL,
			password="AnotherStrongPassword123!",
			organization_name="Someone Else Academy",
			product_key=_TEST_PRODUCT,
			plan_key=_TEST_PLAN_CODE,
		)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "DUPLICATE_EMAIL")

	def test_invalid_plan_rejected_before_any_write(self):
		result = saas.signup(
			full_name="Integration Test",
			email=_TEST_EMAIL,
			password="StrongPassword123!",
			organization_name="Integration Test Academy",
			product_key=_TEST_PRODUCT,
			plan_key="NOT_A_REAL_PLAN",
		)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "INVALID_PLAN")
		# Nothing should have been created — no partial state.
		self.assertFalse(frappe.db.exists("User", _TEST_EMAIL))

	def test_invalid_product_rejected(self):
		result = saas.signup(
			full_name="Integration Test",
			email=_TEST_EMAIL,
			password="StrongPassword123!",
			organization_name="Integration Test Academy",
			product_key="QTT_NOT_A_REAL_PRODUCT",
			plan_key=_TEST_PLAN_CODE,
		)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "INVALID_PRODUCT")
		self.assertFalse(frappe.db.exists("User", _TEST_EMAIL))

	def test_two_tenants_from_two_signups_are_isolated(self):
		result_a = saas.signup(
			full_name="Tenant A Owner",
			email=_TEST_EMAIL,
			password="StrongPassword123!",
			organization_name="Tenant A Academy",
			product_key=_TEST_PRODUCT,
			plan_key=_TEST_PLAN_CODE,
		)
		other_email = "qtt-saas-signup-test-2@example.com"
		try:
			result_b = saas.signup(
				full_name="Tenant B Owner",
				email=other_email,
				password="StrongPassword123!",
				organization_name="Tenant B Academy",
				product_key=_TEST_PRODUCT,
				plan_key=_TEST_PLAN_CODE,
			)
			self.assertNotEqual(result_a["data"]["tenant"], result_b["data"]["tenant"])

			from qtt_platform.tenant.guards import has_tenant_membership

			self.assertTrue(has_tenant_membership(result_a["data"]["tenant"], user=_TEST_EMAIL))
			self.assertFalse(has_tenant_membership(result_a["data"]["tenant"], user=other_email))
			self.assertFalse(has_tenant_membership(result_b["data"]["tenant"], user=_TEST_EMAIL))
		finally:
			if frappe.db.exists("User", other_email):
				frappe.delete_doc("User", other_email, force=1, ignore_permissions=True)
