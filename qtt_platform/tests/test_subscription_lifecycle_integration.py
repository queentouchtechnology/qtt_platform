"""
Real bench integration tests for SaaS lifecycle Phase D — requires an
actual Frappe site (frappe.tests.utils.FrappeTestCase). NOT executed
this pass (no bench access); see test_billing_subscriptions.py's Phase D
test classes (ProcessWebhookRoutingTest, ProcessSubscriptionWebhookEndToEndTest,
ReconcileSubscriptionsTest, CancelSubscriptionFieldsTest, ...) for the
bench-independent tests that WERE executed.

Still does not call the real Razorpay API — a fake gateway is
substituted via monkeypatching qtt_platform.billing.service.get_gateway,
same reasoning as test_billing_subscriptions_integration.py. What this
file proves that the bench-independent suite can't: QTT Webhook Event's
own DATABASE-level unique constraint on gateway_event_id actually
rejects a real redelivered row (not just a mocked exception), and that
subscription status transitions/audit rows persist against real
doctypes with their real validate()/before_save hooks running.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_subscription_lifecycle_integration
"""

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from qtt_platform.billing import service as billing_service
from qtt_platform.billing.gateways.base import SubscriptionCapableGateway
from qtt_platform.subscription import service as subscription_service

_PRODUCT = "QMP_LMS"
_PLAN_CODE = "PHASE_D_INTEGRATION_TEST"


def _fake_gateway():
	gateway = mock.Mock(spec=SubscriptionCapableGateway)
	return gateway


class SubscriptionWebhookIntegrationTest(FrappeTestCase):
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
					"display_name": "Phase D Integration Test Plan",
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
				"tenant_name": "Phase D Integration Tenant",
				"slug": "phase-d-integration-tenant",
				"owner_user": "Administrator",
				"status": "trial",
			}
		)
		self.tenant.insert(ignore_permissions=True)
		plan_name = frappe.db.get_value("QTT Plan", {"product": _PRODUCT, "plan_code": _PLAN_CODE}, "name")
		self.subscription = subscription_service.create_subscription(self.tenant.name, _PRODUCT, plan_name)
		frappe.db.set_value(
			"QTT Product Subscription", self.subscription.name, "razorpay_subscription_id", "sub_integration_test"
		)

	def tearDown(self):
		frappe.delete_doc("QTT Tenant", self.tenant.name, force=1, ignore_permissions=True)
		super().tearDown()

	def test_webhook_event_id_is_rejected_by_a_real_db_constraint_on_redelivery(self):
		frappe.get_doc(
			{
				"doctype": "QTT Webhook Event",
				"gateway": "razorpay",
				"gateway_event_id": "evt_integration_1",
				"event_type": "subscription.activated",
				"gateway_subscription_id": "sub_integration_test",
				"received_at": frappe.utils.now_datetime(),
				"raw_payload": "{}",
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.exceptions.UniqueValidationError):
			frappe.get_doc(
				{
					"doctype": "QTT Webhook Event",
					"gateway": "razorpay",
					"gateway_event_id": "evt_integration_1",
					"event_type": "subscription.activated",
					"gateway_subscription_id": "sub_integration_test",
					"received_at": frappe.utils.now_datetime(),
					"raw_payload": "{}",
				}
			).insert(ignore_permissions=True)

	def test_full_webhook_dispatch_transitions_real_subscription_to_active(self):
		gateway = _fake_gateway()
		gateway.verify_webhook_signature.return_value = True
		from qtt_platform.billing.gateways.base import SubscriptionWebhookEvent

		gateway.parse_subscription_webhook_event.return_value = SubscriptionWebhookEvent(
			event_type="subscription.activated",
			gateway_subscription_id="sub_integration_test",
			status="active",
			customer_id="cust_integration_test",
			raw_payload={"event": "subscription.activated"},
		)

		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			result = billing_service.process_webhook(
				"razorpay",
				json.dumps({"event": "subscription.activated"}).encode(),
				"sig",
				gateway_event_id="evt_integration_2",
			)

		self.assertTrue(result["ok"])
		self.assertEqual(
			frappe.db.get_value("QTT Product Subscription", self.subscription.name, "status"), "active"
		)
		self.assertEqual(
			frappe.db.get_value("QTT Tenant", self.tenant.name, "razorpay_customer_id"), "cust_integration_test"
		)

		# Redelivery of the SAME event id must be a real no-op, not a
		# second status write.
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			second_result = billing_service.process_webhook(
				"razorpay",
				json.dumps({"event": "subscription.activated"}).encode(),
				"sig",
				gateway_event_id="evt_integration_2",
			)
		self.assertTrue(second_result.get("already_processed"))

	def test_reconcile_corrects_a_real_subscription_against_a_mocked_gateway_status(self):
		gateway = _fake_gateway()
		gateway.fetch_subscription_status.return_value = "halted"
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			corrections = billing_service.reconcile_subscriptions()

		matching = [c for c in corrections if c["subscription"] == self.subscription.name]
		self.assertEqual(len(matching), 1)
		self.assertEqual(
			frappe.db.get_value("QTT Product Subscription", self.subscription.name, "status"), "suspended"
		)
