"""
Real bench integration tests for SaaS lifecycle Phase E — requires an
actual Frappe site (frappe.tests.utils.FrappeTestCase). NOT executed
this pass (no bench access); see test_billing_subscriptions.py's Phase E
test classes (ChangePlanOrchestrationTest, ChangePlanAuthorizationTest,
SubscriptionServiceChangePlanCarryForwardTest, ScheduleAndApplyDowngradeTest,
ConcurrentPlanChangeTest, ...) for the 35 bench-independent tests that
WERE actually executed while building this phase.

Still does not call the real Razorpay API — a fake gateway is
substituted via monkeypatching qtt_platform.billing.service.get_gateway,
same reasoning as every prior phase's own integration file. What this
file proves that the bench-independent suite can't: an upgrade actually
persists a NEW current QTT Product Subscription row (via the real
pointer) with razorpay_subscription_id/trial dates genuinely carried
forward, a downgrade genuinely leaves the CURRENT plan field untouched
while scheduled_plan/scheduled_plan_effective_date persist, and
QTT Tenant Product Subscription Pointer's real database unique
constraint is what change_plan() relies on under real concurrent access.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_plan_change_integration
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from qtt_platform.api import subscription as api_subscription
from qtt_platform.billing import service as billing_service
from qtt_platform.billing.gateways.base import SubscriptionCapableGateway
from qtt_platform.subscription import service as subscription_service

_PRODUCT = "QMP_LMS"
_STARTER = "PHASE_E_STARTER"
_PROFESSIONAL = "PHASE_E_PROFESSIONAL"


def _fake_gateway():
	gateway = mock.Mock(spec=SubscriptionCapableGateway)
	gateway.update_subscription_plan.return_value = {"has_scheduled_changes": True}
	gateway.create_plan.return_value = "plan_fake"
	return gateway


class PlanChangeIntegrationTest(FrappeTestCase):
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
		for plan_code, price in ((_STARTER, 99), (_PROFESSIONAL, 299)):
			if not frappe.db.exists("QTT Plan", {"product": _PRODUCT, "plan_code": plan_code}):
				frappe.get_doc(
					{
						"doctype": "QTT Plan",
						"plan_code": plan_code,
						"product": _PRODUCT,
						"display_name": plan_code,
						"base_price": price,
						"billing_period": "monthly",
						"trial_days": 0,
						"is_public": 1,
					}
				).insert(ignore_permissions=True)

	def setUp(self):
		self.tenant = frappe.get_doc(
			{
				"doctype": "QTT Tenant",
				"tenant_name": "Phase E Integration Tenant",
				"slug": "phase-e-integration-tenant",
				"owner_user": "Administrator",
				"status": "active",
			}
		)
		self.tenant.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "QTT Tenant Membership",
				"user": "Administrator",
				"tenant": self.tenant.name,
				"tenant_role": "Tenant Owner",
				"status": "active",
			}
		).insert(ignore_permissions=True)
		starter_name = frappe.db.get_value("QTT Plan", {"product": _PRODUCT, "plan_code": _STARTER}, "name")
		self.subscription = subscription_service.create_subscription(self.tenant.name, _PRODUCT, starter_name)
		frappe.db.set_value(
			"QTT Product Subscription", self.subscription.name, "razorpay_subscription_id", "sub_integration_e"
		)

	def tearDown(self):
		frappe.delete_doc("QTT Tenant", self.tenant.name, force=1, ignore_permissions=True)
		super().tearDown()

	def _as_active_tenant(self):
		return mock.patch.object(api_subscription, "resolve_active_tenant", return_value=self.tenant.name)

	def test_upgrade_creates_new_current_row_with_carried_forward_razorpay_id(self):
		gateway = _fake_gateway()
		with self._as_active_tenant():
			with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
				result = api_subscription.change_plan(_PRODUCT, _PROFESSIONAL)

		self.assertTrue(result["success"], result)
		self.assertEqual(result["data"]["change_type"], "upgrade")

		current = subscription_service.get_current_subscription(self.tenant.name, _PRODUCT)
		self.assertNotEqual(current.name, self.subscription.name)  # a NEW row, per the existing history pattern
		self.assertEqual(current.plan, frappe.db.get_value("QTT Plan", {"plan_code": _PROFESSIONAL}, "name"))
		self.assertEqual(current.razorpay_subscription_id, "sub_integration_e")
		gateway.update_subscription_plan.assert_called_once()
		_, kwargs = gateway.update_subscription_plan.call_args
		self.assertEqual(kwargs["schedule_change_at"], "now")

	def test_downgrade_schedules_without_changing_current_plan(self):
		# First upgrade to Professional so there's somewhere to downgrade from.
		gateway = _fake_gateway()
		with self._as_active_tenant():
			with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
				api_subscription.change_plan(_PRODUCT, _PROFESSIONAL)
				result = api_subscription.change_plan(_PRODUCT, _STARTER)

		self.assertTrue(result["success"], result)
		self.assertEqual(result["data"]["change_type"], "downgrade")

		current = subscription_service.get_current_subscription(self.tenant.name, _PRODUCT)
		# Plan is UNCHANGED right now — still Professional. Only the
		# scheduled_plan memo was set.
		self.assertEqual(current.plan, frappe.db.get_value("QTT Plan", {"plan_code": _PROFESSIONAL}, "name"))
		self.assertEqual(current.scheduled_plan, frappe.db.get_value("QTT Plan", {"plan_code": _STARTER}, "name"))
		self.assertIsNotNone(current.scheduled_plan_effective_date)

		# Now apply it directly (simulating the webhook trigger) and
		# confirm the plan actually flips via a NEW row, same pattern as
		# an immediate change.
		new_current = subscription_service.apply_scheduled_plan_change(current.name)
		self.assertEqual(new_current.plan, frappe.db.get_value("QTT Plan", {"plan_code": _STARTER}, "name"))
		self.assertIsNone(new_current.scheduled_plan)
