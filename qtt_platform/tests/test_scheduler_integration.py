"""
Real bench integration tests for SaaS lifecycle Phase I — requires an
actual Frappe site (frappe.tests.utils.FrappeTestCase). NOT executed
this pass (no bench access); see test_billing_subscriptions.py's Phase I
test classes (FinalizePendingCancellationsTest,
ApplyDueScheduledDowngradesTest, ExpireStaleTrialsTest,
ExpireStaleInvitationsTest) for the 12 bench-independent tests that WERE
actually executed while building this phase.

reconcile_subscriptions()/reconcile_payments() already have their own
integration coverage from Phases D/9's own test files (they were not
rewritten this phase, only scheduled) — not repeated here.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_scheduler_integration
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from qtt_platform.api.invitation import expire_stale_invitations
from qtt_platform.billing.service import expire_stale_trials
from qtt_platform.subscription.service import finalize_pending_cancellations

_PRODUCT = "QMP_LMS"
_PLAN_CODE = "PHASE_I_INTEGRATION_TEST"


class SchedulerIntegrationTest(FrappeTestCase):
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
					"display_name": "Phase I Integration Test Plan",
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
				"tenant_name": "Phase I Integration Tenant",
				"slug": "phase-i-integration-tenant",
				"owner_user": "Administrator",
				"status": "active",
			}
		)
		self.tenant.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("QTT Tenant", self.tenant.name, force=1, ignore_permissions=True)
		super().tearDown()

	def test_finalize_pending_cancellations_flips_status_when_due(self):
		from qtt_platform.subscription import service as subscription_service

		plan_name = frappe.db.get_value("QTT Plan", {"product": _PRODUCT, "plan_code": _PLAN_CODE}, "name")
		subscription = subscription_service.create_subscription(self.tenant.name, _PRODUCT, plan_name)
		frappe.db.set_value(
			"QTT Product Subscription",
			subscription.name,
			{"cancel_at_period_end": 1, "effective_end_date": add_days(today(), -1)},
		)

		results = finalize_pending_cancellations()

		matching = [r for r in results if r["subscription"] == subscription.name]
		self.assertEqual(len(matching), 1)
		self.assertEqual(frappe.db.get_value("QTT Product Subscription", subscription.name, "status"), "cancelled")

	def test_expire_stale_trials_suspends_unlinked_expired_trial(self):
		from qtt_platform.subscription import service as subscription_service

		plan_name = frappe.db.get_value("QTT Plan", {"product": _PRODUCT, "plan_code": _PLAN_CODE}, "name")
		subscription = subscription_service.create_subscription(self.tenant.name, _PRODUCT, plan_name)
		# Force it well past trial_end with no razorpay_subscription_id at all.
		frappe.db.set_value("QTT Product Subscription", subscription.name, "trial_end", add_days(today(), -10))

		results = expire_stale_trials()

		matching = [r for r in results if r["subscription"] == subscription.name]
		self.assertEqual(len(matching), 1)
		self.assertEqual(frappe.db.get_value("QTT Product Subscription", subscription.name, "status"), "suspended")

	def test_expire_stale_invitations_marks_expired(self):
		from qtt_platform.api.invitation import invite_user

		result = invite_user(self.tenant.name, "phase-i-invitee@example.com", tenant_role="Member")
		frappe.db.set_value("QTT Invitation", result["invitation"], "expires_on", add_days(now_datetime(), -1))

		results = expire_stale_invitations()

		matching = [r for r in results if r["invitation"] == result["invitation"]]
		self.assertEqual(len(matching), 1)
		self.assertEqual(frappe.db.get_value("QTT Invitation", result["invitation"], "status"), "expired")
