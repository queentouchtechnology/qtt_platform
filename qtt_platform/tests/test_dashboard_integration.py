"""
Real bench integration test for SaaS lifecycle Phase H — requires an
actual Frappe site (frappe.tests.utils.FrappeTestCase). NOT executed
this pass (no bench access); see test_billing_subscriptions.py's Phase H
test classes (GetEntitlementsWithUsageTest, GetMyPaymentsTest,
GetTeamMembersTest, GetDashboardTest) for the 10 bench-independent tests
that WERE actually executed while building this phase.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_dashboard_integration
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from qtt_platform.api import dashboard as api_dashboard
from qtt_platform.subscription import service as subscription_service

_PRODUCT = "QMP_LMS"
_PLAN_CODE = "PHASE_H_INTEGRATION_TEST"


class DashboardIntegrationTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("QTT Product", _PRODUCT):
			frappe.get_doc(
				{
					"doctype": "QTT Product",
					"product_key": _PRODUCT,
					"display_name": "QMP LMS",
					"app_name": "lms",
					"status": "active",
					"roles": [{"role_key": "Manager", "role_name": "Manager"}],
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("QTT Plan", {"product": _PRODUCT, "plan_code": _PLAN_CODE}):
			frappe.get_doc(
				{
					"doctype": "QTT Plan",
					"plan_code": _PLAN_CODE,
					"product": _PRODUCT,
					"display_name": "Phase H Integration Test Plan",
					"base_price": 99,
					"billing_period": "monthly",
					"trial_days": 7,
					"is_public": 0,
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		self.tenant = frappe.get_doc(
			{
				"doctype": "QTT Tenant",
				"tenant_name": "Phase H Integration Tenant",
				"slug": "phase-h-integration-tenant",
				"owner_user": "Administrator",
				"status": "active",
			}
		)
		self.tenant.insert(ignore_permissions=True)
		self.membership = frappe.get_doc(
			{
				"doctype": "QTT Tenant Membership",
				"user": "Administrator",
				"tenant": self.tenant.name,
				"tenant_role": "Tenant Owner",
				"status": "active",
			}
		)
		self.membership.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "QTT Product Access",
				"membership": self.membership.name,
				"tenant": self.tenant.name,
				"product": _PRODUCT,
				"product_role": "Manager",
				"status": "active",
			}
		).insert(ignore_permissions=True)
		plan_name = frappe.db.get_value("QTT Plan", {"product": _PRODUCT, "plan_code": _PLAN_CODE}, "name")
		subscription_service.create_subscription(self.tenant.name, _PRODUCT, plan_name)

	def tearDown(self):
		frappe.delete_doc("QTT Tenant", self.tenant.name, force=1, ignore_permissions=True)
		super().tearDown()

	def test_dashboard_aggregates_organization_subscription_and_team(self):
		with mock.patch.object(api_dashboard, "resolve_active_tenant", return_value=self.tenant.name):
			result = api_dashboard.get_dashboard(_PRODUCT)

		self.assertTrue(result["success"], result)
		data = result["data"]
		self.assertEqual(data["organization"]["tenant"], self.tenant.name)
		self.assertEqual(data["organization"]["tenant_name"], "Phase H Integration Tenant")
		self.assertEqual(data["user"]["tenant_role"], "Tenant Owner")
		self.assertEqual(data["product"]["product_role"], "Manager")
		self.assertEqual(data["subscription"]["plan_code"], _PLAN_CODE)
		self.assertIsNotNone(data["next_billing_date"])
		self.assertEqual(len(data["team_members"]), 1)
		self.assertEqual(data["team_members"][0]["user"], "Administrator")
		self.assertIsInstance(data["entitlements"], list)
		self.assertIsInstance(data["billing"]["invoices"], list)
		self.assertIsInstance(data["billing"]["payments"], list)
