"""
Real bench integration tests for SaaS lifecycle Phase C — requires an
actual Frappe site (frappe.tests.utils.FrappeTestCase). NOT executed
this pass (no bench access); see test_billing_subscriptions.py in this
same directory for the bench-independent tests that WERE executed.

Deliberately still does NOT call the real Razorpay API even here — a
fake gateway is substituted via monkeypatching
qtt_platform.billing.service.get_gateway, so this test proves the real
DB read/write path (QTT Plan.razorpay_plan_id, QTT Product Subscription.
razorpay_subscription_id actually persisting against real doctypes)
without needing live/test Razorpay credentials, per Part 38's explicit
instruction. A THIRD file, for whoever has real Razorpay TEST
credentials to configure on a bench, would additionally exercise
RazorpayGateway itself against Razorpay's real sandbox — not written
here, since building it without any way to verify it end-to-end this
session would be exactly the kind of unverified claim this project
avoids making.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_billing_subscriptions_integration
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from qtt_platform.billing import service as billing_service
from qtt_platform.billing.gateways.base import SubscriptionCapableGateway, SubscriptionResult
from qtt_platform.subscription import service as subscription_service

_PRODUCT = "QMP_LMS"
_PLAN_CODE = "PHASE_C_INTEGRATION_TEST"


def _fake_subscription_gateway(plan_id="plan_fake_1", subscription_id="sub_fake_1"):
	gateway = mock.Mock(spec=SubscriptionCapableGateway)
	gateway.create_plan.return_value = plan_id
	gateway.create_subscription.return_value = SubscriptionResult(
		gateway_subscription_id=subscription_id, status="created", client_payload={"subscription_id": subscription_id}
	)
	return gateway


class RazorpaySubscriptionIntegrationTest(FrappeTestCase):
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

	def setUp(self):
		self.plan = frappe.get_doc(
			{
				"doctype": "QTT Plan",
				"plan_code": _PLAN_CODE,
				"product": _PRODUCT,
				"display_name": "Phase C Integration Test Plan",
				"base_price": 99,
				"billing_period": "monthly",
				"trial_days": 7,
				"is_public": 0,
			}
		)
		self.plan.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("QTT Plan", self.plan.name, force=1, ignore_permissions=True)
		super().tearDown()

	def test_ensure_razorpay_plan_persists_the_id_and_is_idempotent(self):
		fake_gateway = _fake_subscription_gateway(plan_id="plan_real_db_test")
		with mock.patch.object(billing_service, "get_gateway", return_value=fake_gateway):
			first = billing_service.ensure_razorpay_plan(self.plan.name)
			second = billing_service.ensure_razorpay_plan(self.plan.name)

		self.assertEqual(first, "plan_real_db_test")
		self.assertEqual(second, "plan_real_db_test")
		fake_gateway.create_plan.assert_called_once()  # second call reused the stored id
		self.assertEqual(frappe.db.get_value("QTT Plan", self.plan.name, "razorpay_plan_id"), "plan_real_db_test")

	def test_create_razorpay_subscription_links_a_real_local_subscription(self):
		tenant = frappe.get_doc(
			{
				"doctype": "QTT Tenant",
				"tenant_name": "Phase C Integration Tenant",
				"slug": "phase-c-integration-tenant",
				"owner_user": "Administrator",
				"status": "trial",
			}
		)
		tenant.insert(ignore_permissions=True)
		try:
			subscription = subscription_service.create_subscription(tenant.name, _PRODUCT, self.plan.name)
			self.assertEqual(subscription.status, "trialing")
			self.assertIsNotNone(subscription.trial_end)

			fake_gateway = _fake_subscription_gateway(plan_id="plan_x", subscription_id="sub_real_db_test")
			with mock.patch.object(billing_service, "get_gateway", return_value=fake_gateway):
				result = billing_service.create_razorpay_subscription(subscription.name)

			self.assertEqual(result["razorpay_subscription_id"], "sub_real_db_test")
			self.assertEqual(
				frappe.db.get_value("QTT Product Subscription", subscription.name, "razorpay_subscription_id"),
				"sub_real_db_test",
			)

			# start_at must have been derived from the real trial_end, in
			# whole-second Unix-timestamp form, not left None.
			_, kwargs = fake_gateway.create_subscription.call_args
			self.assertIsNotNone(kwargs["start_at"])

			# Double-linking must be refused, not silently overwritten.
			with self.assertRaises(frappe.ValidationError):
				billing_service.create_razorpay_subscription(subscription.name)
		finally:
			frappe.delete_doc("QTT Tenant", tenant.name, force=1, ignore_permissions=True)
