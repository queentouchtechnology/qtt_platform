"""
Bench-independent tests for SaaS lifecycle Phase C — the Razorpay
Subscriptions adapter (billing/gateways/razorpay_gateway.py's new
SubscriptionCapableGateway methods) and the service-layer glue
(billing/service.py::ensure_razorpay_plan / create_razorpay_subscription
/ cancel_razorpay_subscription). No real network call, no bench, no
database — a fake `requests` module captures exactly what would have
been sent, matching Part 38's explicit instruction to mock the gateway
for automated tests rather than requiring live Razorpay credentials.

Run manually from the qtt_platform repo root:

    python -m unittest qtt_platform.tests.test_billing_subscriptions -v
"""

import json
import sys
import types
import unittest
from unittest import mock


def _install_fake_modules():
	class _ValidationError(Exception):
		pass

	class _PermissionError(Exception):
		pass

	class _UniqueValidationError(_ValidationError):
		pass

	class _DuplicateEntryError(_ValidationError):
		pass

	def _throw(msg, exc=None, **kwargs):
		raise (exc or _ValidationError)(msg)

	fake_frappe = types.ModuleType("frappe")
	fake_frappe.ValidationError = _ValidationError
	fake_frappe.PermissionError = _PermissionError
	fake_frappe.UniqueValidationError = _UniqueValidationError
	fake_frappe.DuplicateEntryError = _DuplicateEntryError
	fake_frappe.throw = _throw
	fake_frappe._ = lambda s: s
	fake_frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	fake_frappe.db = types.SimpleNamespace(
		get_value=mock.Mock(return_value=None),
		set_value=mock.Mock(),
		exists=mock.Mock(return_value=False),
		sql=mock.Mock(return_value=()),
		# frappe.db.sql() itself returns () for any UPDATE (see
		# credit_service.py::deduct_credits' own comment on why — no
		# result set to fetch) — the real affected-row count lives on
		# the underlying DB-API cursor's .rowcount, faked here so tests
		# can set it per-case rather than relying on db.sql()'s return.
		_cursor=types.SimpleNamespace(rowcount=0),
	)
	fake_frappe.get_doc = mock.Mock()
	fake_frappe.get_all = mock.Mock(return_value=[])
	fake_frappe.log_error = mock.Mock()
	fake_frappe.get_traceback = mock.Mock(return_value="")
	fake_frappe.generate_hash = mock.Mock(return_value="fake-invitation-token")
	fake_frappe.sendmail = mock.Mock()
	fake_frappe.session = types.SimpleNamespace(user="Administrator")
	fake_frappe.local = types.SimpleNamespace(request_ip=None)
	fake_frappe.get_hooks = mock.Mock(return_value={})
	fake_frappe.cache = mock.Mock(
		return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
	)
	fake_frappe.get_attr = mock.Mock()
	fake_frappe.parse_json = lambda s: __import__("json").loads(s)
	fake_frappe.get_roles = mock.Mock(return_value=["All"])

	fake_frappe_utils = types.ModuleType("frappe.utils")
	fake_frappe_utils.add_days = lambda d, n: d
	fake_frappe_utils.now_datetime = lambda: "2026-08-12 00:00:00"
	fake_frappe_utils.today = lambda: "2026-08-12"
	fake_frappe_utils.get_datetime = lambda v: v  # tests pass real datetime objects in directly
	fake_frappe.utils = fake_frappe_utils

	fake_frappe_utils_password = types.ModuleType("frappe.utils.password")
	fake_frappe_utils_password.get_decrypted_password = mock.Mock(return_value="test-secret")
	fake_frappe_utils_password.update_password = mock.Mock()
	fake_frappe_utils.password = fake_frappe_utils_password

	class _Document:
		"""Minimal stand-in for frappe.model.document.Document — just
		enough for a real doctype controller module (e.g.
		qtt_tenant_membership.py) to import and subclass successfully.
		Tests that need an instance build one via Document.__new__(...)
		and set only the attributes their method under test reads,
		rather than going through this class's own (absent) __init__."""

	fake_frappe_model = types.ModuleType("frappe.model")
	fake_frappe_model_document = types.ModuleType("frappe.model.document")
	fake_frappe_model_document.Document = _Document
	fake_frappe_model.document = fake_frappe_model_document
	fake_frappe.model = fake_frappe_model
	sys.modules["frappe.model"] = fake_frappe_model
	sys.modules["frappe.model.document"] = fake_frappe_model_document

	fake_requests = types.ModuleType("requests")
	fake_requests.post = mock.Mock()
	fake_requests.get = mock.Mock()
	fake_requests.patch = mock.Mock()
	sys.modules["requests"] = fake_requests

	sys.modules["frappe"] = fake_frappe
	sys.modules["frappe.utils"] = fake_frappe_utils
	sys.modules["frappe.utils.password"] = fake_frappe_utils_password
	return fake_frappe, fake_requests


def _make_get_doc(existing: dict):
	"""Mirrors frappe.get_doc's two real call shapes: get_doc(doctype,
	name) for a lookup (returns a pre-configured fake from `existing`,
	keyed by (doctype, name)), get_doc({...}) for constructing a new
	in-memory doc (e.g. what qtt_platform.audit.write_audit_event does
	internally) — a plain throwaway Mock is fine for that shape since no
	test here asserts on audit-log construction."""

	def _get_doc(*args, **kwargs):
		if len(args) == 2:
			key = (args[0], args[1])
			if key in existing:
				return existing[key]
			raise AssertionError(f"no fake doc configured for get_doc{key}")
		return mock.Mock()

	return _get_doc


def _make_get_doc_with_construction(existing: dict):
	"""Like _make_get_doc, but the get_doc({...}) construction branch
	returns a Mock whose ATTRIBUTES reflect the passed dict
	(mock.Mock(**the_dict)) instead of a blank Mock — needed wherever a
	test asserts on what change_plan()/etc. actually put on the newly
	constructed document (e.g. that razorpay_subscription_id was carried
	forward), not just that .insert() was called."""

	def _get_doc(*args, **kwargs):
		if len(args) == 2:
			key = (args[0], args[1])
			if key in existing:
				return existing[key]
			raise AssertionError(f"no fake doc configured for get_doc{key}")
		return mock.Mock(**args[0])

	return _get_doc


class _FrappeDict(dict):
	"""A minimal stand-in for real Frappe's frappe._dict — a dict that
	ALSO supports attribute access (t.name) — needed wherever production
	code uses both t.name and t.get(...) on the same frappe.get_all()
	row, which plain dict (no attribute access) or types.SimpleNamespace
	(no .get()) each only satisfy half of."""

	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError:
			return None


def _fake_response(json_body, status_code=200):
	resp = mock.Mock()
	resp.status_code = status_code
	resp.json.return_value = json_body
	resp.raise_for_status = mock.Mock()
	return resp


fake_frappe, fake_requests = _install_fake_modules()

from qtt_platform.ai import feature_registry  # noqa: E402
from qtt_platform.usage import registry as usage_registry  # noqa: E402
from qtt_platform.ai.services import credit_service  # noqa: E402
from qtt_platform.api import ai as api_ai  # noqa: E402
from qtt_platform.api import billing as api_billing  # noqa: E402
from qtt_platform.api import dashboard as api_dashboard  # noqa: E402
from qtt_platform.api import invitation as api_invitation  # noqa: E402
from qtt_platform.api import product as api_product  # noqa: E402
from qtt_platform.api import product_access as api_product_access  # noqa: E402
from qtt_platform.api import session as api_session  # noqa: E402
from qtt_platform.api import subscription as api_subscription  # noqa: E402
from qtt_platform.billing import service as billing_service  # noqa: E402
from qtt_platform.billing.gateways.base import SubscriptionCapableGateway, SubscriptionWebhookEvent  # noqa: E402
from qtt_platform.billing.gateways.razorpay_gateway import RazorpayGateway  # noqa: E402
from qtt_platform.entitlement import engine as entitlement_engine  # noqa: E402
from qtt_platform.errors import QttApiError  # noqa: E402
from qtt_platform.exceptions import FeatureNotConfigured  # noqa: E402
from qtt_platform.qtt_platform.doctype.qtt_tenant_membership.qtt_tenant_membership import (  # noqa: E402
	QTTTenantMembership,
)
from qtt_platform.subscription import service as subscription_service  # noqa: E402
from qtt_platform import user_provisioning  # noqa: E402
from qtt_platform.user_provisioning import create_user  # noqa: E402


def _fake_gateway(**method_returns):
	"""A mock spec'd against the REAL RazorpayGateway class (not just the
	SubscriptionCapableGateway ABC) — it's what get_gateway() actually
	returns in production, implementing BOTH PaymentGateway
	(verify_webhook_signature, parse_webhook_event, ...) and
	SubscriptionCapableGateway. mock.Mock(spec=...) sets __class__ to the
	spec'd class, so isinstance(gateway, SubscriptionCapableGateway) —
	billing.service's own capability check — passes exactly like the real
	thing would, without any real network access."""
	gateway = mock.Mock(spec=RazorpayGateway)
	for name, value in method_returns.items():
		getattr(gateway, name).return_value = value
	return gateway


class RazorpayCreatePlanTest(unittest.TestCase):
	def setUp(self):
		fake_requests.post.reset_mock()
		fake_requests.post.return_value = _fake_response({"id": "plan_ABC123"})
		self.gateway = RazorpayGateway()

	def test_creates_plan_with_amount_in_paise(self):
		plan_id = self.gateway.create_plan(name="QMP LMS Starter (QMP_LMS)", amount=99, currency="INR", period="monthly")
		self.assertEqual(plan_id, "plan_ABC123")

		url, kwargs = fake_requests.post.call_args
		self.assertTrue(url[0].endswith("/plans"))
		self.assertEqual(kwargs["json"]["period"], "monthly")
		self.assertEqual(kwargs["json"]["item"]["amount"], 9900)  # 99 rupees -> 9900 paise
		self.assertEqual(kwargs["json"]["item"]["currency"], "INR")

	def test_unsupported_period_rejected_before_any_network_call(self):
		with self.assertRaises(Exception):
			self.gateway.create_plan(name="x", amount=1, currency="INR", period="weekly")
		fake_requests.post.assert_not_called()


class RazorpayCreateSubscriptionTest(unittest.TestCase):
	def setUp(self):
		fake_requests.post.reset_mock()
		fake_requests.post.return_value = _fake_response({"id": "sub_XYZ789", "status": "created"})
		self.gateway = RazorpayGateway()

	def test_creates_subscription_with_trial_start_at(self):
		result = self.gateway.create_subscription(
			gateway_plan_id="plan_ABC123",
			total_count=120,
			start_at=1755561600,
			customer_notify=True,
			notes={"qtt_tenant": "tenant-1"},
		)
		self.assertEqual(result.gateway_subscription_id, "sub_XYZ789")
		self.assertEqual(result.status, "created")
		self.assertIn("subscription_id", result.client_payload)

		_, kwargs = fake_requests.post.call_args
		body = kwargs["json"]
		self.assertEqual(body["plan_id"], "plan_ABC123")
		self.assertEqual(body["total_count"], 120)
		self.assertEqual(body["start_at"], 1755561600)
		self.assertEqual(body["customer_notify"], 1)
		self.assertEqual(body["notes"], {"qtt_tenant": "tenant-1"})

	def test_no_customer_id_sent_ever(self):
		# Confirms the deliberate design fact this phase's own docs assert:
		# Razorpay's Create Subscription request never carries a
		# customer_id — verified against Razorpay's current API docs.
		self.gateway.create_subscription(gateway_plan_id="plan_ABC123", total_count=120)
		_, kwargs = fake_requests.post.call_args
		self.assertNotIn("customer_id", kwargs["json"])

	def test_start_at_omitted_when_no_trial(self):
		self.gateway.create_subscription(gateway_plan_id="plan_ABC123", total_count=120, start_at=None)
		_, kwargs = fake_requests.post.call_args
		self.assertNotIn("start_at", kwargs["json"])


class RazorpayCancelSubscriptionTest(unittest.TestCase):
	def setUp(self):
		fake_requests.post.reset_mock()
		fake_requests.post.return_value = _fake_response({"id": "sub_XYZ789", "status": "cancelled"})
		self.gateway = RazorpayGateway()

	def test_cancel_hits_the_correct_subscription_id_endpoint(self):
		self.gateway.cancel_subscription(gateway_subscription_id="sub_XYZ789", cancel_at_cycle_end=True)
		url, kwargs = fake_requests.post.call_args
		self.assertTrue(url[0].endswith("/subscriptions/sub_XYZ789/cancel"))
		self.assertEqual(kwargs["json"], {"cancel_at_cycle_end": True})


class RazorpaySubscriptionWebhookParsingTest(unittest.TestCase):
	def setUp(self):
		self.gateway = RazorpayGateway()

	def test_parses_activated_event_with_customer_id(self):
		payload = json.dumps(
			{
				"event": "subscription.activated",
				"payload": {"subscription": {"entity": {"id": "sub_XYZ789", "status": "active", "customer_id": "cust_1"}}}},
		).encode()
		event = self.gateway.parse_subscription_webhook_event(payload)
		self.assertEqual(event.event_type, "subscription.activated")
		self.assertEqual(event.gateway_subscription_id, "sub_XYZ789")
		self.assertEqual(event.status, "active")
		self.assertEqual(event.customer_id, "cust_1")

	def test_parses_created_event_with_no_customer_id_yet(self):
		payload = json.dumps(
			{"event": "subscription.pending", "payload": {"subscription": {"entity": {"id": "sub_XYZ789", "status": "pending"}}}}
		).encode()
		event = self.gateway.parse_subscription_webhook_event(payload)
		self.assertIsNone(event.customer_id)


class EnsureRazorpayPlanTest(unittest.TestCase):
	def test_reuses_existing_plan_id_without_any_gateway_call(self):
		fake_plan = mock.Mock(razorpay_plan_id="plan_already_set")
		fake_frappe.get_doc = _make_get_doc({("QTT Plan", "plan-1"): fake_plan})
		with mock.patch.object(billing_service, "get_gateway") as get_gateway_mock:
			result = billing_service.ensure_razorpay_plan("plan-1")
		self.assertEqual(result, "plan_already_set")
		get_gateway_mock.assert_not_called()

	def test_creates_and_stores_when_not_set(self):
		fake_plan = mock.Mock(
			razorpay_plan_id=None, display_name="Starter", product="QMP_LMS", base_price=99, billing_period="monthly"
		)
		fake_plan.name = "plan-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Plan", "plan-1"): fake_plan})
		fake_frappe.db.set_value = mock.Mock()

		fake_gateway = _fake_gateway(create_plan="plan_new_123")
		with mock.patch.object(billing_service, "get_gateway", return_value=fake_gateway):
			result = billing_service.ensure_razorpay_plan("plan-1")

		fake_gateway.create_plan.assert_called_once_with(name="Starter (QMP_LMS)", amount=99, currency="INR", period="monthly")
		self.assertEqual(result, "plan_new_123")
		fake_frappe.db.set_value.assert_called_once_with("QTT Plan", "plan-1", "razorpay_plan_id", "plan_new_123")


class CreateRazorpaySubscriptionTest(unittest.TestCase):
	def test_refuses_to_double_link(self):
		fake_sub = mock.Mock(razorpay_subscription_id="sub_already_linked")
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): fake_sub})
		with self.assertRaises(Exception):
			billing_service.create_razorpay_subscription("sub-1")


class CancelRazorpaySubscriptionTest(unittest.TestCase):
	def test_noop_when_never_linked_to_razorpay(self):
		fake_sub = mock.Mock(razorpay_subscription_id=None)
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): fake_sub})
		with mock.patch.object(billing_service, "get_gateway") as get_gateway_mock:
			result = billing_service.cancel_razorpay_subscription("sub-1")
		self.assertFalse(result)
		get_gateway_mock.assert_not_called()

	def test_cancels_when_linked(self):
		fake_sub = mock.Mock(razorpay_subscription_id="sub_XYZ789", tenant="tenant-1", product="QMP_LMS")
		fake_sub.name = "sub-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): fake_sub})
		fake_gateway = _fake_gateway()
		with mock.patch.object(billing_service, "get_gateway", return_value=fake_gateway):
			result = billing_service.cancel_razorpay_subscription("sub-1", cancel_at_cycle_end=False)
		self.assertTrue(result)
		fake_gateway.cancel_subscription.assert_called_once_with(
			gateway_subscription_id="sub_XYZ789", cancel_at_cycle_end=False
		)


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase D — webhook dispatch, the subscription state
# machine, and reconciliation.
# ---------------------------------------------------------------------------


def _subscription_event(event_type, gateway_subscription_id="sub_XYZ789", status="active", customer_id=None, raw_payload=None):
	return SubscriptionWebhookEvent(
		event_type=event_type,
		gateway_subscription_id=gateway_subscription_id,
		status=status,
		customer_id=customer_id,
		raw_payload=raw_payload or {"event": event_type},
	)


class ProcessWebhookRoutingTest(unittest.TestCase):
	"""process_webhook() must route by event-name prefix, and the
	ORDER path must stay byte-for-byte the same as before Phase D."""

	def test_subscription_event_routes_to_subscription_handler(self):
		gateway = _fake_gateway()
		gateway.verify_webhook_signature.return_value = True
		gateway.parse_subscription_webhook_event.return_value = _subscription_event("subscription.updated")
		fake_frappe.get_doc = mock.Mock()  # webhook-event ledger insert succeeds
		fake_frappe.db.get_value = mock.Mock(return_value=None)  # no matching local subscription

		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			result = billing_service.process_webhook(
				"razorpay", json.dumps({"event": "subscription.updated"}).encode(), "sig", gateway_event_id="evt_1"
			)

		gateway.parse_subscription_webhook_event.assert_called_once()
		gateway.parse_webhook_event.assert_not_called()
		self.assertTrue(result["ok"])

	def test_payment_event_routes_to_existing_order_handler_unchanged(self):
		gateway = _fake_gateway()
		gateway.verify_webhook_signature.return_value = True
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			with mock.patch.object(billing_service, "_process_order_webhook", return_value={"ok": True}) as order_handler:
				result = billing_service.process_webhook(
					"razorpay", json.dumps({"event": "payment.captured"}).encode(), "sig"
				)
		order_handler.assert_called_once()
		gateway.parse_subscription_webhook_event.assert_not_called()
		self.assertTrue(result["ok"])

	def test_invalid_signature_rejected_before_any_dispatch(self):
		gateway = _fake_gateway()
		gateway.verify_webhook_signature.return_value = False
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			with self.assertRaises(Exception):
				billing_service.process_webhook("razorpay", b'{"event": "subscription.updated"}', "bad-sig")
		gateway.parse_subscription_webhook_event.assert_not_called()


class RecordWebhookEventOnceTest(unittest.TestCase):
	def test_first_delivery_is_recorded_and_returns_true(self):
		fake_frappe.get_doc = mock.Mock()
		event = _subscription_event("subscription.activated")
		result = billing_service._record_webhook_event_once("razorpay", "evt_unique_1", event)
		self.assertTrue(result)
		fake_frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	def test_redelivery_hits_the_unique_constraint_and_returns_false(self):
		doc = mock.Mock()
		doc.insert.side_effect = fake_frappe.UniqueValidationError("duplicate")
		fake_frappe.get_doc = mock.Mock(return_value=doc)
		event = _subscription_event("subscription.activated")
		result = billing_service._record_webhook_event_once("razorpay", "evt_duplicate", event)
		self.assertFalse(result)

	def test_missing_event_id_is_rejected_before_recording_anything(self):
		gateway = _fake_gateway()
		gateway.verify_webhook_signature.return_value = True
		gateway.parse_subscription_webhook_event.return_value = _subscription_event("subscription.activated")
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			with self.assertRaises(Exception):
				billing_service.process_webhook(
					"razorpay", b'{"event": "subscription.activated"}', "sig", gateway_event_id=None
				)


class ApplySubscriptionStatusTransitionTest(unittest.TestCase):
	def test_changes_status_and_audits(self):
		sub = mock.Mock(status="trialing", tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		billing_service._apply_subscription_status_transition(sub, "active", source="subscription.activated", gateway_status="active")
		self.assertEqual(sub.status, "active")
		sub.save.assert_called_once_with(ignore_permissions=True)

	def test_noop_when_status_unchanged(self):
		sub = mock.Mock(status="active", tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		billing_service._apply_subscription_status_transition(sub, "active", source="subscription.charged", gateway_status="active")
		sub.save.assert_not_called()

	def test_cancelled_sets_cancelled_at_and_effective_end_date(self):
		sub = mock.Mock(status="active", tenant="tenant-1", product="QMP_LMS", cancelled_at=None, effective_end_date=None)
		sub.name = "sub-1"
		billing_service._apply_subscription_status_transition(sub, "cancelled", source="subscription.cancelled", gateway_status="cancelled")
		self.assertIsNotNone(sub.cancelled_at)
		self.assertIsNotNone(sub.effective_end_date)


class ProcessSubscriptionWebhookEndToEndTest(unittest.TestCase):
	def setUp(self):
		self.gateway = _fake_gateway()
		self.gateway.verify_webhook_signature.return_value = True
		self.sub = mock.Mock(status="trialing", tenant="tenant-1", product="QMP_LMS", razorpay_subscription_id="sub_XYZ789")
		self.sub.name = "sub-1"

	def test_activated_event_transitions_to_active_and_backfills_customer_id(self):
		self.gateway.parse_subscription_webhook_event.return_value = _subscription_event(
			"subscription.activated", customer_id="cust_1"
		)
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): self.sub})
		fake_frappe.db.get_value = mock.Mock(side_effect=["sub-1", None])  # subscription lookup, then customer_id lookup
		fake_frappe.db.set_value = mock.Mock()

		with mock.patch.object(billing_service, "get_gateway", return_value=self.gateway):
			result = billing_service.process_webhook(
				"razorpay", b'{"event": "subscription.activated"}', "sig", gateway_event_id="evt_2"
			)

		self.assertTrue(result["ok"])
		self.assertEqual(self.sub.status, "active")
		fake_frappe.db.set_value.assert_any_call("QTT Tenant", "tenant-1", "razorpay_customer_id", "cust_1")

	def test_halted_event_transitions_to_suspended(self):
		self.sub.status = "past_due"
		self.gateway.parse_subscription_webhook_event.return_value = _subscription_event(
			"subscription.halted", status="halted"
		)
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): self.sub})
		fake_frappe.db.get_value = mock.Mock(return_value="sub-1")

		with mock.patch.object(billing_service, "get_gateway", return_value=self.gateway):
			billing_service.process_webhook("razorpay", b'{"event": "subscription.halted"}', "sig", gateway_event_id="evt_3")

		self.assertEqual(self.sub.status, "suspended")

	def test_payment_failure_pending_event_transitions_to_past_due(self):
		# Razorpay's own mid-retry-grace-period state (SaaS lifecycle
		# Phase D's own documented mapping) — "payment failure" from the
		# customer's perspective.
		self.sub.status = "active"
		self.gateway.parse_subscription_webhook_event.return_value = _subscription_event(
			"subscription.pending", status="pending"
		)
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): self.sub})
		fake_frappe.db.get_value = mock.Mock(return_value="sub-1")

		with mock.patch.object(billing_service, "get_gateway", return_value=self.gateway):
			billing_service.process_webhook("razorpay", b'{"event": "subscription.pending"}', "sig", gateway_event_id="evt_pending_1")

		self.assertEqual(self.sub.status, "past_due")

	def test_subscription_recovery_from_past_due_to_active(self):
		# A retried charge succeeding — "subscription recovery" — is the
		# SAME subscription.charged event that also records the payment
		# (RecordSubscriptionChargeTest, tested separately); this test's
		# only job is confirming the STATUS half of recovery.
		self.sub.status = "past_due"
		self.gateway.parse_subscription_webhook_event.return_value = _subscription_event(
			"subscription.charged", status="active", raw_payload={"payload": {}}
		)
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): self.sub})
		fake_frappe.db.get_value = mock.Mock(return_value="sub-1")
		fake_frappe.db.exists = mock.Mock(return_value=False)

		with mock.patch.object(billing_service, "get_gateway", return_value=self.gateway):
			with mock.patch.object(subscription_service, "apply_scheduled_plan_change"):
				billing_service.process_webhook(
					"razorpay", b'{"event": "subscription.charged"}', "sig", gateway_event_id="evt_recovery_1"
				)

		self.assertEqual(self.sub.status, "active")

	def test_unknown_subscription_id_is_a_safe_no_op(self):
		self.gateway.parse_subscription_webhook_event.return_value = _subscription_event("subscription.activated")
		fake_frappe.get_doc = mock.Mock()  # webhook-event ledger insert
		fake_frappe.db.get_value = mock.Mock(return_value=None)  # no local subscription matches

		with mock.patch.object(billing_service, "get_gateway", return_value=self.gateway):
			result = billing_service.process_webhook(
				"razorpay", b'{"event": "subscription.activated"}', "sig", gateway_event_id="evt_4"
			)
		self.assertTrue(result.get("unrecognized_subscription"))

	def test_redelivered_event_id_is_a_no_op_second_time(self):
		self.gateway.parse_subscription_webhook_event.return_value = _subscription_event("subscription.activated")
		ledger_doc = mock.Mock()
		ledger_doc.insert.side_effect = fake_frappe.UniqueValidationError("duplicate")
		fake_frappe.get_doc = mock.Mock(return_value=ledger_doc)

		with mock.patch.object(billing_service, "get_gateway", return_value=self.gateway):
			result = billing_service.process_webhook(
				"razorpay", b'{"event": "subscription.activated"}', "sig", gateway_event_id="evt_5"
			)
		self.assertTrue(result.get("already_processed"))


class RecordSubscriptionChargeTest(unittest.TestCase):
	def test_creates_invoice_payment_and_transaction(self):
		sub = mock.Mock(tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		fake_frappe.db.exists = mock.Mock(return_value=False)
		invoice_doc = mock.Mock()
		invoice_doc.name = "inv-1"
		fake_frappe.get_doc = mock.Mock(return_value=invoice_doc)
		fake_frappe.db.set_value = mock.Mock()

		raw_payload = {"payload": {"payment": {"entity": {"id": "pay_1", "amount": 9900, "currency": "INR"}}}}
		billing_service._record_subscription_charge(sub, raw_payload)

		fake_frappe.db.set_value.assert_any_call("QTT Invoice", "inv-1", "status", "paid")

	def test_idempotent_on_gateway_payment_id(self):
		sub = mock.Mock(tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		fake_frappe.db.exists = mock.Mock(return_value=True)  # already recorded
		fake_frappe.get_doc = mock.Mock()

		raw_payload = {"payload": {"payment": {"entity": {"id": "pay_1", "amount": 9900, "currency": "INR"}}}}
		billing_service._record_subscription_charge(sub, raw_payload)

		fake_frappe.get_doc.assert_not_called()

	def test_missing_payment_entity_is_a_safe_noop(self):
		sub = mock.Mock(tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		fake_frappe.get_doc = mock.Mock()
		billing_service._record_subscription_charge(sub, {"payload": {}})
		fake_frappe.get_doc.assert_not_called()


class ReconcileSubscriptionsTest(unittest.TestCase):
	def test_corrects_drifted_status(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[
				types.SimpleNamespace(name="sub-1", razorpay_subscription_id="sub_XYZ789", status="active")
			]
		)
		sub = mock.Mock(status="active", tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})

		gateway = _fake_gateway()
		gateway.fetch_subscription_status.return_value = "halted"
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			corrections = billing_service.reconcile_subscriptions()

		self.assertEqual(len(corrections), 1)
		self.assertEqual(sub.status, "suspended")

	def test_no_correction_when_in_sync(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[
				types.SimpleNamespace(name="sub-1", razorpay_subscription_id="sub_XYZ789", status="active")
			]
		)
		gateway = _fake_gateway()
		gateway.fetch_subscription_status.return_value = "active"
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			corrections = billing_service.reconcile_subscriptions()
		self.assertEqual(corrections, [])

	def test_fetch_failure_is_logged_and_skipped_not_raised(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[
				types.SimpleNamespace(name="sub-1", razorpay_subscription_id="sub_XYZ789", status="active")
			]
		)
		gateway = _fake_gateway()
		gateway.fetch_subscription_status.side_effect = Exception("network error")
		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			corrections = billing_service.reconcile_subscriptions()  # must not raise
		self.assertEqual(corrections, [])


class CancelSubscriptionFieldsTest(unittest.TestCase):
	"""subscription/service.py::cancel_subscription()'s Phase D field
	population — the local half of cancellation."""

	def _fake_current_subscription(self, **overrides):
		sub = mock.Mock(plan="plan-1", current_period_end="2026-09-01", **overrides)
		sub.name = "sub-1"
		return sub

	def test_cancel_at_period_end_sets_requested_at_and_effective_end_date_but_not_cancelled_at(self):
		current = self._fake_current_subscription(cancelled_at=None)
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(subscription_service, "_write_subscription_event"):
				result = subscription_service.cancel_subscription(
					"tenant-1", "QMP_LMS", at_period_end=True, reason="too expensive"
				)

		self.assertEqual(result.cancel_reason, "too expensive")
		self.assertIsNotNone(result.cancellation_requested_at)
		self.assertEqual(result.effective_end_date, "2026-09-01")
		self.assertIsNone(result.cancelled_at)

	def test_immediate_cancel_sets_cancelled_at_and_status(self):
		current = self._fake_current_subscription(cancelled_at=None)
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(subscription_service, "_write_subscription_event"):
				result = subscription_service.cancel_subscription("tenant-1", "QMP_LMS", at_period_end=False)

		self.assertEqual(result.status, "cancelled")
		self.assertIsNotNone(result.cancelled_at)
		self.assertIsNotNone(result.effective_end_date)


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase E — plan upgrade/downgrade.
# ---------------------------------------------------------------------------


def _fake_plan(name, plan_code, base_price, *, is_public=1, product="QMP_LMS", features=None):
	plan = mock.Mock(product=product, plan_code=plan_code, base_price=base_price, is_public=is_public)
	plan.name = name
	plan.features = features or []
	return plan


def _fake_feature(feature_key, limit_value):
	return mock.Mock(feature_key=feature_key, limit_value=limit_value)


def _fake_current_subscription(**overrides):
	defaults = dict(
		name="sub-1",
		tenant="tenant-1",
		product="QMP_LMS",
		plan="plan-starter",
		status="active",
		current_period_start="2026-08-01",
		current_period_end="2026-08-31",
		cancel_at_period_end=0,
		cancellation_requested_at=None,
		cancel_reason=None,
		scheduled_plan=None,
		scheduled_plan_effective_date=None,
		razorpay_subscription_id="sub_razorpay_1",
		trial_start=None,
		trial_end=None,
	)
	defaults.update(overrides)
	sub = mock.Mock(**{k: v for k, v in defaults.items() if k != "name"})
	sub.name = defaults["name"]
	return sub


class SubscriptionServiceChangePlanCarryForwardTest(unittest.TestCase):
	"""subscription_service.change_plan() directly — the Phase E fix that
	carries razorpay_subscription_id/trial dates/status forward onto the
	new row instead of leaving them blank / hardcoding 'active'."""

	def setUp(self):
		self.current = _fake_current_subscription(status="trialing", trial_start="2026-08-01", trial_end="2026-08-08")
		self.new_plan_doc = _fake_plan("plan-professional", "PROFESSIONAL", 299)
		fake_frappe.get_doc = _make_get_doc_with_construction(
			{("QTT Plan", "plan-professional"): self.new_plan_doc}
		)
		fake_frappe.db.get_value = mock.Mock(return_value=99)  # old plan base_price

	def test_carries_forward_razorpay_subscription_id(self):
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			with mock.patch.object(subscription_service, "activate_pointer"):
				with mock.patch.object(subscription_service, "_write_subscription_event"):
					new_sub = subscription_service.change_plan("tenant-1", "QMP_LMS", "plan-professional")
		self.assertEqual(new_sub.razorpay_subscription_id, "sub_razorpay_1")

	def test_carries_forward_trial_dates_and_does_not_restart_trial(self):
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			with mock.patch.object(subscription_service, "activate_pointer"):
				with mock.patch.object(subscription_service, "_write_subscription_event"):
					new_sub = subscription_service.change_plan("tenant-1", "QMP_LMS", "plan-professional")
		self.assertEqual(new_sub.trial_start, "2026-08-01")
		self.assertEqual(new_sub.trial_end, "2026-08-08")

	def test_carries_forward_trialing_status_instead_of_hardcoding_active(self):
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			with mock.patch.object(subscription_service, "activate_pointer"):
				with mock.patch.object(subscription_service, "_write_subscription_event"):
					new_sub = subscription_service.change_plan("tenant-1", "QMP_LMS", "plan-professional")
		self.assertEqual(new_sub.status, "trialing")

	def test_active_status_stays_active(self):
		self.current.status = "active"
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			with mock.patch.object(subscription_service, "activate_pointer"):
				with mock.patch.object(subscription_service, "_write_subscription_event"):
					new_sub = subscription_service.change_plan("tenant-1", "QMP_LMS", "plan-professional")
		self.assertEqual(new_sub.status, "active")


class ScheduleAndApplyDowngradeTest(unittest.TestCase):
	def setUp(self):
		self.current = _fake_current_subscription(plan="plan-professional")
		self.new_plan_doc = _fake_plan("plan-starter", "STARTER", 99)
		fake_frappe.get_doc = _make_get_doc({("QTT Plan", "plan-starter"): self.new_plan_doc})

	def test_schedule_plan_change_sets_fields(self):
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			result = subscription_service.schedule_plan_change("tenant-1", "QMP_LMS", "plan-starter", "2026-08-31")
		self.assertEqual(result.scheduled_plan, "plan-starter")
		self.assertEqual(result.scheduled_plan_effective_date, "2026-08-31")
		self.current.save.assert_called_once_with(ignore_permissions=True)

	def test_apply_noop_when_nothing_scheduled(self):
		sub = _fake_current_subscription(scheduled_plan=None)
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})
		result = subscription_service.apply_scheduled_plan_change("sub-1")
		self.assertIsNone(result)

	def test_apply_noop_when_not_yet_due(self):
		sub = _fake_current_subscription(scheduled_plan="plan-starter", scheduled_plan_effective_date="2099-01-01")
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})
		result = subscription_service.apply_scheduled_plan_change("sub-1")
		self.assertIsNone(result)

	def test_apply_runs_change_plan_when_due(self):
		sub = _fake_current_subscription(scheduled_plan="plan-starter", scheduled_plan_effective_date="2020-01-01")
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})
		new_sub = mock.Mock()
		new_sub.name = "sub-2"
		with mock.patch.object(subscription_service, "change_plan", return_value=new_sub) as change_plan_mock:
			result = subscription_service.apply_scheduled_plan_change("sub-1")
		change_plan_mock.assert_called_once_with("tenant-1", "QMP_LMS", "plan-starter")
		self.assertIs(result, new_sub)


class ResumeSubscriptionTest(unittest.TestCase):
	def test_clears_cancellation_fields(self):
		current = _fake_current_subscription(
			status="active", cancel_at_period_end=1, cancellation_requested_at="2026-08-15 00:00:00", cancel_reason="too pricey"
		)
		# write_audit_event() inside resume_subscription() calls
		# frappe.get_doc({...}) to build the QTT Audit Log row — reset to
		# a clean generic mock rather than inheriting whatever an earlier
		# test in this module left fake_frappe.get_doc configured as.
		fake_frappe.get_doc = mock.Mock()
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			result = subscription_service.resume_subscription("tenant-1", "QMP_LMS")
		self.assertEqual(result.cancel_at_period_end, 0)
		self.assertIsNone(result.cancellation_requested_at)
		self.assertIsNone(result.cancel_reason)

	def test_rejects_already_cancelled(self):
		current = _fake_current_subscription(status="cancelled")
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with self.assertRaises(Exception):
				subscription_service.resume_subscription("tenant-1", "QMP_LMS")


class ChangePlanAuthorizationTest(unittest.TestCase):
	"""Exercises the REAL require_tenant_role chain (not mocked) — the
	actual thing enforcing SaaS lifecycle Phase E section 4's "Tenant
	Owner OR Tenant Admin, never Member, never a QMP_LMS product role.\""""

	def _run_with_role(self, tenant_role, membership_status="active"):
		membership = mock.Mock(status=membership_status, tenant_role=tenant_role)
		fake_frappe.get_doc = _make_get_doc({("QTT Tenant Membership", "membership-1"): membership})
		fake_frappe.db.get_value = mock.Mock(side_effect=["active", "membership-1"])
		with mock.patch.object(api_subscription, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_subscription, "require_product_access", return_value=None):
				with mock.patch.object(api_subscription, "service") as service_mock:
					service_mock.get_current_subscription.return_value = None  # short-circuits after the role gate
					return api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")

	def test_owner_can_change_plan(self):
		result = self._run_with_role("Tenant Owner")
		# Passed the role gate — the failure (if any) is deeper in the
		# flow (SUBSCRIPTION_NOT_FOUND from the short-circuited mock
		# above), never BILLING_ROLE_REQUIRED.
		self.assertNotEqual(result.get("error", {}).get("code"), "BILLING_ROLE_REQUIRED")

	def test_admin_can_change_plan(self):
		result = self._run_with_role("Tenant Admin")
		self.assertNotEqual(result.get("error", {}).get("code"), "BILLING_ROLE_REQUIRED")

	def test_member_cannot_change_plan(self):
		result = self._run_with_role("Member")
		self.assertEqual(result["error"]["code"], "BILLING_ROLE_REQUIRED")

	def test_student_product_role_does_not_substitute_for_tenant_role(self):
		# require_tenant_role never reads QTT Product Access.product_role
		# at all — a "Student" product role literally cannot appear in
		# this code path, which is the structural guarantee section 4
		# asks for. Modelled here as a Member (the only tenant_role a
		# QMP_LMS Student would plausibly hold) to prove it's still
		# blocked purely on tenant_role.
		result = self._run_with_role("Member")
		self.assertEqual(result["error"]["code"], "BILLING_ROLE_REQUIRED")

	def test_instructor_product_role_does_not_substitute_for_tenant_role(self):
		result = self._run_with_role("Member")
		self.assertEqual(result["error"]["code"], "BILLING_ROLE_REQUIRED")

	def test_no_active_tenant_rejected(self):
		with mock.patch.object(api_subscription, "resolve_active_tenant", return_value=None):
			result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")
		self.assertEqual(result["error"]["code"], "TENANT_ACCESS_DENIED")


class ChangePlanOrchestrationTest(unittest.TestCase):
	"""api_subscription.change_plan() end-to-end with authorization
	mocked out (covered separately above) — BASIC / UPGRADE / DOWNGRADE /
	TRIAL / CANCELLATION / RAZORPAY-FAILURE / AUDIT behaviour."""

	def setUp(self):
		self.starter = _fake_plan("plan-starter", "STARTER", 99)
		self.professional = _fake_plan(
			"plan-professional", "PROFESSIONAL", 299, features=[_fake_feature("max_students", "100")]
		)
		self.current = _fake_current_subscription(plan="plan-starter")

		self._patches = [
			mock.patch.object(api_subscription, "resolve_active_tenant", return_value="tenant-1"),
			mock.patch.object(api_subscription, "require_tenant_role", return_value=None),
			mock.patch.object(api_subscription, "require_product_access", return_value=None),
			mock.patch.object(api_subscription, "write_audit_event"),
		]
		for p in self._patches:
			p.start()
			self.addCleanup(p.stop)

		fake_frappe.get_doc = _make_get_doc(
			{("QTT Plan", "plan-professional"): self.professional, ("QTT Plan", "plan-starter"): self.starter}
		)
		fake_frappe.db.get_value = mock.Mock(
			side_effect=lambda doctype, *a, **k: {
				"QTT Product": "active",
				"QTT Plan": "plan-professional" if not a or a[0] != {"product": "QMP_LMS", "plan_code": "STARTER"} else "plan-starter",
			}.get(doctype)
		)

	def _get_value_for_plan_code(self, plan_code):
		def _dispatch(doctype, *a, **k):
			if doctype == "QTT Product":
				return "active"
			if doctype == "QTT Plan":
				filters = a[0] if a else k.get("filters")
				if isinstance(filters, dict) and filters.get("plan_code") == plan_code:
					return "plan-professional" if plan_code == "PROFESSIONAL" else "plan-starter"
				return "plan-starter"  # scheduled_plan -> plan_code lookup fallback
			return None
		return _dispatch

	def test_change_to_same_plan_rejected(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("STARTER"))
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			result = api_subscription.change_plan("QMP_LMS", "STARTER")
		self.assertEqual(result["error"]["code"], "PLAN_UNCHANGED")

	def test_invalid_plan_rejected(self):
		# Product resolves fine; the PLAN lookup is what fails.
		fake_frappe.db.get_value = mock.Mock(
			side_effect=lambda doctype, *a, **k: "active" if doctype == "QTT Product" else None
		)
		result = api_subscription.change_plan("QMP_LMS", "NOT_A_REAL_PLAN")
		self.assertEqual(result["error"]["code"], "INVALID_PLAN")

	def test_invalid_product_rejected(self):
		fake_frappe.db.get_value = mock.Mock(return_value=None)
		result = api_subscription.change_plan("QTT_NOT_A_PRODUCT", "PROFESSIONAL")
		self.assertIn(result["error"]["code"], ("INVALID_PLAN", "INVALID_PRODUCT"))

	def test_missing_subscription_rejected(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("PROFESSIONAL"))
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=None):
			result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")
		self.assertEqual(result["error"]["code"], "SUBSCRIPTION_NOT_FOUND")

	def test_upgrade_is_immediate_and_syncs_gateway_with_now(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("PROFESSIONAL"))
		new_sub = mock.Mock(name="sub-2")
		new_sub.name = "sub-2"
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			with mock.patch.object(billing_service, "sync_razorpay_plan_change") as sync_mock:
				with mock.patch.object(subscription_service, "change_plan", return_value=new_sub) as change_plan_mock:
					result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")

		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["change_type"], "upgrade")
		self.assertEqual(result["data"]["effective"], "immediate")
		sync_mock.assert_called_once_with("sub-1", "plan-professional", immediate=True)
		change_plan_mock.assert_called_once()

	def test_downgrade_is_scheduled_and_syncs_gateway_with_cycle_end(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("STARTER"))
		current = _fake_current_subscription(plan="plan-professional")
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(billing_service, "sync_razorpay_plan_change") as sync_mock:
				with mock.patch.object(subscription_service, "schedule_plan_change") as schedule_mock:
					with mock.patch.object(subscription_service, "change_plan") as change_plan_mock:
						result = api_subscription.change_plan("QMP_LMS", "STARTER")

		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["change_type"], "downgrade")
		self.assertEqual(result["data"]["effective"], "next_billing_cycle")
		sync_mock.assert_called_once_with("sub-1", "plan-starter", immediate=False)
		schedule_mock.assert_called_once()
		# The KEY downgrade guarantee: current plan is NEVER flipped
		# immediately — change_plan() (which would create the new
		# current row) must not be called at all for a downgrade.
		change_plan_mock.assert_not_called()

	def test_plan_change_blocked_when_cancellation_pending(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("PROFESSIONAL"))
		current = _fake_current_subscription(plan="plan-starter", cancel_at_period_end=1)
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")
		self.assertEqual(result["error"]["code"], "CANCELLATION_PENDING")

	def test_resume_then_plan_change_succeeds(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("PROFESSIONAL"))
		current = _fake_current_subscription(plan="plan-starter", cancel_at_period_end=0, cancellation_requested_at=None)
		new_sub = mock.Mock()
		new_sub.name = "sub-2"
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(billing_service, "sync_razorpay_plan_change"):
				with mock.patch.object(subscription_service, "change_plan", return_value=new_sub):
					result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")
		self.assertTrue(result["success"])

	def test_plan_change_already_pending_rejected(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("PROFESSIONAL"))
		current = _fake_current_subscription(plan="plan-starter", scheduled_plan="plan-enterprise")
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")
		self.assertEqual(result["error"]["code"], "PLAN_CHANGE_ALREADY_PENDING")

	def test_razorpay_failure_blocks_upgrade_local_write(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("PROFESSIONAL"))
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=self.current):
			with mock.patch.object(billing_service, "sync_razorpay_plan_change", side_effect=Exception("gateway down")):
				with mock.patch.object(subscription_service, "change_plan") as change_plan_mock:
					result = api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")

		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "PLAN_CHANGE_FAILED")
		change_plan_mock.assert_not_called()

	def test_razorpay_failure_blocks_downgrade_scheduling(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("STARTER"))
		current = _fake_current_subscription(plan="plan-professional")
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(billing_service, "sync_razorpay_plan_change", side_effect=Exception("gateway down")):
				with mock.patch.object(subscription_service, "schedule_plan_change") as schedule_mock:
					result = api_subscription.change_plan("QMP_LMS", "STARTER")

		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "PLAN_CHANGE_FAILED")
		schedule_mock.assert_not_called()

	def test_downgrade_includes_usage_warning_when_over_limit(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=self._get_value_for_plan_code("STARTER"))
		starter_with_limit = _fake_plan("plan-starter", "STARTER", 99, features=[_fake_feature("max_students", "25")])
		fake_frappe.get_doc = _make_get_doc(
			{("QTT Plan", "plan-professional"): self.professional, ("QTT Plan", "plan-starter"): starter_with_limit}
		)
		current = _fake_current_subscription(plan="plan-professional")
		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(billing_service, "sync_razorpay_plan_change"):
				with mock.patch.object(subscription_service, "schedule_plan_change"):
					with mock.patch.object(
						api_subscription, "get_usage_resolver", side_effect=_resolver_only_for("max_students")
					):
						with mock.patch.object(api_subscription, "get_usage", return_value=95):
							result = api_subscription.change_plan("QMP_LMS", "STARTER")

		self.assertTrue(result["success"])
		self.assertEqual(len(result["data"]["usage_warning"]), 1)
		self.assertEqual(result["data"]["usage_warning"][0]["feature_key"], "max_students")


class WebhookAppliesScheduledDowngradeTest(unittest.TestCase):
	def test_subscription_charged_triggers_apply_scheduled_plan_change(self):
		gateway = _fake_gateway()
		gateway.verify_webhook_signature.return_value = True
		gateway.parse_subscription_webhook_event.return_value = _subscription_event(
			"subscription.charged",
			raw_payload={"payload": {"payment": {"entity": {"id": "pay_1", "amount": 9900, "currency": "INR"}}}},
		)
		sub = _fake_current_subscription()
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})
		fake_frappe.db.get_value = mock.Mock(return_value="sub-1")
		fake_frappe.db.exists = mock.Mock(return_value=True)  # payment already recorded — skip that branch

		with mock.patch.object(billing_service, "get_gateway", return_value=gateway):
			with mock.patch.object(subscription_service, "apply_scheduled_plan_change") as apply_mock:
				billing_service.process_webhook(
					"razorpay", b'{"event": "subscription.charged"}', "sig", gateway_event_id="evt_charged_1"
				)

		apply_mock.assert_called_once_with("sub-1")


def _resolver_only_for(*feature_keys):
	"""A get_usage_resolver() stand-in that only 'exists' for the given
	feature_keys — mirrors real usage.registry behaviour: a flag-shaped
	feature (e.g. live_classes_enabled) has NO registered resolver."""

	def _resolver(product, feature_key):
		if feature_key in feature_keys:
			return mock.Mock()
		from qtt_platform.exceptions import FeatureNotConfigured

		raise FeatureNotConfigured(feature_key)

	return _resolver


class GetOverLimitFeaturesTest(unittest.TestCase):
	def test_detects_over_limit_numeric_feature(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		with mock.patch.object(
			entitlement_engine, "get_entitlements", return_value={"max_students": 25, "live_classes_enabled": 1}
		):
			with mock.patch.object(entitlement_engine, "get_usage_resolver", side_effect=_resolver_only_for("max_students")):
				with mock.patch.object(entitlement_engine, "get_usage", return_value=30):
					over_limit = entitlement_engine.get_over_limit_features("tenant-1", "QMP_LMS")
		self.assertEqual(over_limit, [{"feature_key": "max_students", "used": 30, "limit": 25}])

	def test_within_limit_is_not_reported(self):
		with mock.patch.object(entitlement_engine, "get_entitlements", return_value={"max_students": 25}):
			with mock.patch.object(entitlement_engine, "get_usage_resolver", side_effect=_resolver_only_for("max_students")):
				with mock.patch.object(entitlement_engine, "get_usage", return_value=10):
					over_limit = entitlement_engine.get_over_limit_features("tenant-1", "QMP_LMS")
		self.assertEqual(over_limit, [])

	def test_no_open_subscription_returns_empty(self):
		with mock.patch.object(entitlement_engine, "get_entitlements", return_value={}):
			over_limit = entitlement_engine.get_over_limit_features("tenant-1", "QMP_LMS")
		self.assertEqual(over_limit, [])


class ConcurrentPlanChangeTest(unittest.TestCase):
	"""SaaS lifecycle Phase E section 16: change_plan() inherits
	activate_pointer()'s EXISTING, already-reviewed concurrency
	protection (a real DB unique constraint on
	QTT Tenant Product Subscription Pointer(tenant, product), patches/
	v0_3) rather than needing new locking — this test proves the
	inheritance, not the underlying primitive (already covered by this
	project's Phase 4 work)."""

	def test_change_plan_resolves_a_pointer_race_via_existing_retry_logic(self):
		current = _fake_current_subscription()
		new_plan_doc = _fake_plan("plan-professional", "PROFESSIONAL", 299)
		fake_frappe.get_doc = _make_get_doc({("QTT Plan", "plan-professional"): new_plan_doc})
		fake_frappe.db.get_value = mock.Mock(
			side_effect=[
				99,  # old plan base_price lookup inside change_plan()
				None,  # activate_pointer(): no existing pointer row found on first check
				"pointer-1",  # activate_pointer(): re-queried after UniqueValidationError, found by the "winner"
			]
		)
		# The NEW subscription row insert succeeds; the pointer INSERT
		# races and loses (simulating a concurrent second change_plan()
		# call that won), exactly the path activate_pointer() already
		# handles.
		new_sub_doc = mock.Mock()
		pointer_doc = mock.Mock()
		pointer_doc.insert.side_effect = fake_frappe.UniqueValidationError("duplicate pointer")
		call_count = {"n": 0}

		def _get_doc_dispatch(*args, **kwargs):
			if args and args[0] == "QTT Plan":
				return new_plan_doc
			call_count["n"] += 1
			if call_count["n"] == 1:
				return new_sub_doc  # the new QTT Product Subscription row
			return pointer_doc  # the QTT Tenant Product Subscription Pointer row

		fake_frappe.get_doc = mock.Mock(side_effect=_get_doc_dispatch)

		with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
			with mock.patch.object(subscription_service, "_write_subscription_event"):
				result = subscription_service.change_plan("tenant-1", "QMP_LMS", "plan-professional")

		self.assertIs(result, new_sub_doc)
		new_sub_doc.insert.assert_called_once_with(ignore_permissions=True)
		# The pointer's own concurrency-safe fallback (frappe.db.set_value
		# after catching UniqueValidationError) is what resolves the
		# race — confirmed it was reached at least once.
		self.assertTrue(fake_frappe.db.set_value.called)


class AuditEventsWrittenTest(unittest.TestCase):
	def test_upgrade_writes_plan_upgrade_event(self):
		with mock.patch.object(api_subscription, "write_audit_event") as audit_mock:
			with mock.patch.object(api_subscription, "resolve_active_tenant", return_value="tenant-1"):
				with mock.patch.object(api_subscription, "require_tenant_role"):
					with mock.patch.object(api_subscription, "require_product_access"):
						fake_frappe.db.get_value = mock.Mock(
							side_effect=lambda doctype, *a, **k: "active" if doctype == "QTT Product" else "plan-professional"
						)
						starter = _fake_plan("plan-starter", "STARTER", 99)
						professional = _fake_plan("plan-professional", "PROFESSIONAL", 299)
						fake_frappe.get_doc = _make_get_doc(
							{("QTT Plan", "plan-professional"): professional, ("QTT Plan", "plan-starter"): starter}
						)
						current = _fake_current_subscription(plan="plan-starter")
						new_sub = mock.Mock()
						new_sub.name = "sub-2"
						with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
							with mock.patch.object(billing_service, "sync_razorpay_plan_change"):
								with mock.patch.object(subscription_service, "change_plan", return_value=new_sub):
									api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")

		event_types = [call.args[0] for call in audit_mock.call_args_list]
		self.assertIn("plan_change_requested", event_types)
		self.assertIn("plan_upgrade", event_types)

	def test_failed_change_writes_plan_change_failed_event(self):
		with mock.patch.object(api_subscription, "write_audit_event") as audit_mock:
			with mock.patch.object(api_subscription, "resolve_active_tenant", return_value="tenant-1"):
				with mock.patch.object(api_subscription, "require_tenant_role"):
					with mock.patch.object(api_subscription, "require_product_access"):
						fake_frappe.db.get_value = mock.Mock(
							side_effect=lambda doctype, *a, **k: "active" if doctype == "QTT Product" else "plan-professional"
						)
						starter = _fake_plan("plan-starter", "STARTER", 99)
						professional = _fake_plan("plan-professional", "PROFESSIONAL", 299)
						fake_frappe.get_doc = _make_get_doc(
							{("QTT Plan", "plan-professional"): professional, ("QTT Plan", "plan-starter"): starter}
						)
						current = _fake_current_subscription(plan="plan-starter")
						with mock.patch.object(subscription_service, "get_current_subscription", return_value=current):
							with mock.patch.object(
								billing_service, "sync_razorpay_plan_change", side_effect=Exception("down")
							):
								api_subscription.change_plan("QMP_LMS", "PROFESSIONAL")

		event_types = [call.args[0] for call in audit_mock.call_args_list]
		self.assertIn("plan_change_failed", event_types)


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase F — tenant invitation + product access.
# ---------------------------------------------------------------------------


class UserProvisioningCreateUserTest(unittest.TestCase):
	"""qtt_platform.user_provisioning.create_user() — extracted from
	api.saas's own private _create_user() once api.invitation.
	accept_invitation() needed the identical logic. Tested HERE, not in
	test_saas_signup.py (its own more natural home) — see that file's
	module docstring for the reproduced cross-file fake-frappe binding
	issue this avoids."""

	def test_pre_existing_email_rejected_without_touching_get_doc(self):
		fake_frappe.db.exists = mock.Mock(return_value=True)
		fake_frappe.get_doc = mock.Mock()
		with self.assertRaises(QttApiError) as ctx:
			create_user("John Doe", "john@example.com", "StrongPassword123!")
		self.assertEqual(ctx.exception.code, "DUPLICATE_EMAIL")
		fake_frappe.get_doc.assert_not_called()

	def test_concurrent_duplicate_at_insert_time_is_mapped_cleanly(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_user = mock.Mock()
		fake_user.insert.side_effect = fake_frappe.DuplicateEntryError("already exists")
		fake_frappe.get_doc = mock.Mock(return_value=fake_user)
		with self.assertRaises(QttApiError) as ctx:
			create_user("John Doe", "john@example.com", "StrongPassword123!")
		self.assertEqual(ctx.exception.code, "DUPLICATE_EMAIL")

	def test_weak_password_rejected_by_frappes_own_policy_is_mapped(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_user = mock.Mock()
		fake_user.insert.side_effect = fake_frappe.ValidationError("Password not strong enough")
		fake_frappe.get_doc = mock.Mock(return_value=fake_user)
		with self.assertRaises(QttApiError) as ctx:
			create_user("John Doe", "john@example.com", "weak")
		self.assertEqual(ctx.exception.code, "WEAK_PASSWORD")

	def test_success_returns_inserted_user(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_user = mock.Mock()
		fake_frappe.get_doc = mock.Mock(return_value=fake_user)
		with mock.patch.object(user_provisioning, "_set_password"):
			result = create_user("John Doe", "john@example.com", "StrongPassword123!")
		self.assertIs(result, fake_user)
		fake_user.insert.assert_called_once_with(ignore_permissions=True)

	def test_password_is_set_explicitly_after_insert(self):
		# Regression test for a real bug caught via live testing (Part
		# C-J): on this Frappe version, User.on_update() runs validate()
		# a second time internally, which clears new_password to "" before
		# send_password_notification() ever reads it — so relying on
		# new_password's automatic on-insert side effect silently
		# produced accounts nobody could ever log into (confirmed: zero
		# rows in __Auth for a real signup-created user, traced against
		# 100% unmodified Frappe core). create_user() must now call
		# frappe.utils.password.update_password() itself, unconditionally,
		# right after insert.
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_user = mock.Mock()
		fake_frappe.get_doc = mock.Mock(return_value=fake_user)

		with mock.patch.object(user_provisioning, "_set_password") as set_password_mock:
			create_user("John Doe", "john@example.com", "StrongPassword123!")

		set_password_mock.assert_called_once_with("john@example.com", "StrongPassword123!")


class InviteUserTest(unittest.TestCase):
	def setUp(self):
		p = mock.patch.object(api_invitation, "require_tenant_role", return_value=None)
		p.start()
		self.addCleanup(p.stop)
		fake_frappe.sendmail = mock.Mock()
		fake_frappe.generate_hash = mock.Mock(return_value="tok-123")

	def test_rejects_already_active_member(self):
		fake_frappe.db.get_value = mock.Mock(side_effect=["membership-1", "active"])
		with self.assertRaises(Exception):
			api_invitation.invite_user("tenant-1", "existing@example.com")

	def test_creates_new_invitation_when_none_pending(self):
		fake_frappe.db.get_value = mock.Mock(
			side_effect=lambda doctype, *a, **k: {"QTT Tenant Membership": None, "QTT Tenant": "Acme Academy"}.get(
				doctype
			)
		)
		fake_frappe.db.exists = mock.Mock(return_value=False)
		new_invitation = mock.Mock(token="tok-123", expires_on="2026-08-19 00:00:00")
		new_invitation.name = "inv-1"

		def _get_doc(*args, **kwargs):
			if len(args) == 1 and isinstance(args[0], dict) and args[0]["doctype"] == "QTT Invitation":
				return new_invitation
			return mock.Mock()  # QTT Audit Log construction inside write_audit_event()

		fake_frappe.get_doc = mock.Mock(side_effect=_get_doc)

		result = api_invitation.invite_user(
			"tenant-1", "new@example.com", product="QMP_LMS", product_role="Manager"
		)

		self.assertEqual(result["invitation"], "inv-1")
		new_invitation.insert.assert_called_once_with(ignore_permissions=True)
		fake_frappe.sendmail.assert_called_once()

	def test_reuses_existing_pending_invitation_instead_of_duplicating(self):
		fake_frappe.db.get_value = mock.Mock(
			side_effect=lambda doctype, *a, **k: {"QTT Tenant Membership": None, "QTT Tenant": "Acme"}.get(doctype)
		)
		fake_frappe.db.exists = mock.Mock(return_value="inv-existing")
		existing_invitation = mock.Mock(token="tok-123", expires_on="2026-08-19 00:00:00")
		existing_invitation.name = "inv-existing"
		fake_frappe.get_doc = _make_get_doc({("QTT Invitation", "inv-existing"): existing_invitation})

		result = api_invitation.invite_user("tenant-1", "pending@example.com")

		self.assertEqual(result["invitation"], "inv-existing")
		existing_invitation.save.assert_called_once_with(ignore_permissions=True)
		existing_invitation.insert.assert_not_called()


class RevokeInvitationTest(unittest.TestCase):
	def setUp(self):
		p = mock.patch.object(api_invitation, "require_tenant_role", return_value=None)
		p.start()
		self.addCleanup(p.stop)

	def test_revoke_sets_status(self):
		fake_frappe.db.get_value = mock.Mock(return_value="tenant-1")
		fake_frappe.db.set_value = mock.Mock()
		result = api_invitation.revoke_invitation("tenant-1", "inv-1")
		self.assertEqual(result["status"], "revoked")
		fake_frappe.db.set_value.assert_called_once_with("QTT Invitation", "inv-1", "status", "revoked")

	def test_rejects_foreign_tenant_invitation(self):
		fake_frappe.db.get_value = mock.Mock(return_value="some-other-tenant")
		with self.assertRaises(Exception):
			api_invitation.revoke_invitation("tenant-1", "inv-1")


class AcceptInvitationTest(unittest.TestCase):
	def test_invalid_token_rejected(self):
		fake_frappe.db.exists = mock.Mock(return_value=None)
		result = api_invitation.accept_invitation("bad-token")
		self.assertEqual(result["error"]["code"], "INVALID_INVITATION")

	def test_expired_invitation_marks_expired_and_rejects(self):
		fake_frappe.db.exists = mock.Mock(return_value="inv-1")
		invitation = mock.Mock(expires_on="2000-01-01 00:00:00", email="new@example.com")
		invitation.name = "inv-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Invitation", "inv-1"): invitation})

		result = api_invitation.accept_invitation("tok-123")

		self.assertEqual(result["error"]["code"], "INVITATION_EXPIRED")
		self.assertEqual(invitation.status, "expired")
		invitation.save.assert_called_once_with(ignore_permissions=True)

	def test_existing_user_must_already_be_logged_in_as_that_user(self):
		fake_frappe.db.exists = mock.Mock(
			side_effect=lambda doctype, *a, **k: {"QTT Invitation": "inv-1", "User": "existing@example.com"}.get(
				doctype
			)
		)
		invitation = mock.Mock(expires_on="2099-01-01 00:00:00", email="existing@example.com")
		invitation.name = "inv-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Invitation", "inv-1"): invitation})

		with mock.patch.object(fake_frappe, "session", types.SimpleNamespace(user="Guest")):
			result = api_invitation.accept_invitation("tok-123")

		self.assertEqual(result["error"]["code"], "LOGIN_REQUIRED")

	def test_new_user_requires_name_and_password(self):
		fake_frappe.db.exists = mock.Mock(
			side_effect=lambda doctype, *a, **k: {"QTT Invitation": "inv-1", "User": None}.get(doctype)
		)
		invitation = mock.Mock(expires_on="2099-01-01 00:00:00", email="new@example.com")
		invitation.name = "inv-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Invitation", "inv-1"): invitation})

		result = api_invitation.accept_invitation("tok-123")

		self.assertEqual(result["error"]["code"], "ACCOUNT_DETAILS_REQUIRED")

	def test_success_creates_user_membership_and_product_access(self):
		fake_frappe.db.exists = mock.Mock(
			side_effect=lambda doctype, *a, **k: {
				"QTT Invitation": "inv-1",
				"User": None,
				"QTT Tenant Membership": None,
				"QTT Product Access": None,
			}.get(doctype)
		)
		invitation = mock.Mock(
			expires_on="2099-01-01 00:00:00",
			email="new@example.com",
			tenant="tenant-1",
			tenant_role="Member",
			product="QMP_LMS",
			product_role="Manager",
		)
		invitation.name = "inv-1"

		new_user = mock.Mock()
		new_user.name = "new@example.com"
		new_membership = mock.Mock(tenant_role="Member")
		new_membership.name = "membership-1"
		new_access = mock.Mock(product_role="Manager")

		def _get_doc(*args, **kwargs):
			if args == ("QTT Invitation", "inv-1"):
				return invitation
			if len(args) == 1 and isinstance(args[0], dict):
				doctype = args[0]["doctype"]
				return {"User": new_user, "QTT Tenant Membership": new_membership, "QTT Product Access": new_access}.get(
					doctype, mock.Mock()
				)
			raise AssertionError(f"unexpected get_doc call: {args!r}")

		fake_frappe.get_doc = mock.Mock(side_effect=_get_doc)

		result = api_invitation.accept_invitation("tok-123", full_name="New User", password="StrongPassword123!")

		self.assertTrue(result["success"], result)
		self.assertEqual(result["data"]["user"], "new@example.com")
		self.assertEqual(result["data"]["tenant"], "tenant-1")
		self.assertEqual(result["data"]["product_role"], "Manager")
		new_user.insert.assert_called_once_with(ignore_permissions=True)
		new_membership.insert.assert_called_once_with(ignore_permissions=True)
		new_access.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(invitation.status, "accepted")

	def test_no_product_on_invitation_means_no_product_access_created(self):
		fake_frappe.db.exists = mock.Mock(
			side_effect=lambda doctype, *a, **k: {
				"QTT Invitation": "inv-1",
				"User": None,
				"QTT Tenant Membership": None,
			}.get(doctype)
		)
		invitation = mock.Mock(
			expires_on="2099-01-01 00:00:00",
			email="new@example.com",
			tenant="tenant-1",
			tenant_role="Member",
			product=None,
			product_role=None,
		)
		invitation.name = "inv-1"

		new_user = mock.Mock()
		new_user.name = "new@example.com"
		new_membership = mock.Mock(tenant_role="Member")
		new_membership.name = "membership-1"

		def _get_doc(*args, **kwargs):
			if args == ("QTT Invitation", "inv-1"):
				return invitation
			if len(args) == 1 and isinstance(args[0], dict):
				doctype = args[0]["doctype"]
				return {"User": new_user, "QTT Tenant Membership": new_membership}.get(doctype, mock.Mock())
			raise AssertionError(f"unexpected get_doc call: {args!r}")

		fake_frappe.get_doc = mock.Mock(side_effect=_get_doc)

		result = api_invitation.accept_invitation("tok-123", full_name="New User", password="StrongPassword123!")

		self.assertTrue(result["success"], result)
		self.assertIsNone(result["data"]["product_role"])


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase H — dashboard APIs. Pure composition of already-
# tested functions; these tests confirm the composition wiring, not the
# underlying logic (each piece has its own tests elsewhere already).
# ---------------------------------------------------------------------------


class GetEntitlementsWithUsageTest(unittest.TestCase):
	def test_composes_can_i_for_every_entitlement(self):
		with mock.patch.object(
			entitlement_engine, "get_entitlements", return_value={"max_students": 25, "live_classes_enabled": 1}
		):
			with mock.patch.object(
				entitlement_engine, "get_usage_resolver", side_effect=_resolver_only_for("max_students")
			):
				with mock.patch.object(entitlement_engine, "get_usage", return_value=10):
					rows = entitlement_engine.get_entitlements_with_usage("tenant-1", "QMP_LMS")

		by_key = {r["feature_key"]: r for r in rows}
		self.assertEqual(by_key["max_students"]["used"], 10)
		self.assertEqual(by_key["max_students"]["limit"], 25)
		self.assertTrue(by_key["live_classes_enabled"]["allowed"])
		self.assertIsNone(by_key["live_classes_enabled"]["limit"])

	def test_empty_when_no_entitlements(self):
		with mock.patch.object(entitlement_engine, "get_entitlements", return_value={}):
			rows = entitlement_engine.get_entitlements_with_usage("tenant-1", "QMP_LMS")
		self.assertEqual(rows, [])


class GetMyPaymentsTest(unittest.TestCase):
	def test_empty_when_no_invoices(self):
		with mock.patch.object(api_billing, "require_tenant_membership"):
			fake_frappe.get_all = mock.Mock(return_value=[])
			result = api_billing.get_my_payments("tenant-1")
		self.assertEqual(result, [])

	def test_joins_through_invoice_ids(self):
		with mock.patch.object(api_billing, "require_tenant_membership"):
			fake_frappe.get_all = mock.Mock(
				side_effect=[
					["inv-1", "inv-2"],
					[
						{
							"name": "pay-1",
							"invoice": "inv-1",
							"amount": 99,
							"currency": "INR",
							"status": "succeeded",
							"paid_at": "2026-08-01",
							"refund_of": None,
						}
					],
				]
			)
			result = api_billing.get_my_payments("tenant-1")
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["invoice"], "inv-1")


class GetTeamMembersTest(unittest.TestCase):
	def test_aggregates_membership_and_product_access(self):
		# frappe.get_all() rows are dot-accessible (frappe._dict) in real
		# use — types.SimpleNamespace mirrors that, unlike a plain dict.
		with mock.patch.object(api_product_access, "require_tenant_membership"):
			fake_frappe.get_all = mock.Mock(
				side_effect=[
					[types.SimpleNamespace(name="membership-1", user="a@example.com", tenant_role="Tenant Owner")],
					[types.SimpleNamespace(membership="membership-1", product="QMP_LMS", product_role="Manager")],
				]
			)
			result = api_product_access.get_team_members("tenant-1")

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["user"], "a@example.com")
		self.assertEqual(result[0]["tenant_role"], "Tenant Owner")
		self.assertEqual(result[0]["product_access"], [{"product": "QMP_LMS", "product_role": "Manager"}])

	def test_member_with_no_product_access_still_listed(self):
		with mock.patch.object(api_product_access, "require_tenant_membership"):
			fake_frappe.get_all = mock.Mock(
				side_effect=[
					[types.SimpleNamespace(name="membership-1", user="a@example.com", tenant_role="Member")],
					[],
				]
			)
			result = api_product_access.get_team_members("tenant-1")
		self.assertEqual(result[0]["product_access"], [])

	def test_empty_tenant_returns_empty_list(self):
		with mock.patch.object(api_product_access, "require_tenant_membership"):
			fake_frappe.get_all = mock.Mock(return_value=[])
			result = api_product_access.get_team_members("tenant-1")
		self.assertEqual(result, [])


class GetDashboardTest(unittest.TestCase):
	def test_no_active_tenant_rejected(self):
		with mock.patch.object(api_dashboard, "resolve_active_tenant", return_value=None):
			result = api_dashboard.get_dashboard("QMP_LMS")
		self.assertEqual(result["error"]["code"], "TENANT_ACCESS_DENIED")

	def test_full_composition_happy_path(self):
		membership = mock.Mock(tenant_role="Tenant Owner")
		tenant_doc = mock.Mock(tenant_name="Acme", status="active", owner_user="owner@example.com")
		access = mock.Mock(product_role="Manager", status="active")

		with mock.patch.object(api_dashboard, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_dashboard, "require_tenant_membership", return_value=membership):
				fake_frappe.db.get_value = mock.Mock(return_value=tenant_doc)
				with mock.patch.object(api_dashboard, "has_product_access", return_value=True):
					with mock.patch.object(api_dashboard, "require_product_access", return_value=access):
						with mock.patch.object(
							api_dashboard,
							"get_my_subscription",
							return_value={"plan_code": "STARTER", "current_period_end": "2026-08-31"},
						):
							with mock.patch.object(
								api_dashboard,
								"get_entitlements_with_usage",
								return_value=[{"feature_key": "max_students", "used": 5, "limit": 25}],
							):
								with mock.patch.object(api_dashboard, "get_my_invoices", return_value=[]):
									with mock.patch.object(api_dashboard, "get_my_payments", return_value=[]):
										with mock.patch.object(api_dashboard, "get_team_members", return_value=[]):
											result = api_dashboard.get_dashboard("QMP_LMS")

		self.assertTrue(result["success"], result)
		self.assertEqual(result["data"]["organization"]["tenant_name"], "Acme")
		self.assertEqual(result["data"]["product"]["product_role"], "Manager")
		self.assertEqual(result["data"]["next_billing_date"], "2026-08-31")
		self.assertEqual(len(result["data"]["entitlements"]), 1)

	def test_no_product_access_still_returns_other_sections(self):
		membership = mock.Mock(tenant_role="Member")
		tenant_doc = mock.Mock(tenant_name="Acme", status="active", owner_user="owner@example.com")

		with mock.patch.object(api_dashboard, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_dashboard, "require_tenant_membership", return_value=membership):
				fake_frappe.db.get_value = mock.Mock(return_value=tenant_doc)
				with mock.patch.object(api_dashboard, "has_product_access", return_value=False):
					with mock.patch.object(api_dashboard, "get_my_subscription", return_value=None):
						with mock.patch.object(api_dashboard, "get_my_invoices", return_value=[]):
							with mock.patch.object(api_dashboard, "get_my_payments", return_value=[]):
								with mock.patch.object(api_dashboard, "get_team_members", return_value=[]):
									result = api_dashboard.get_dashboard("QMP_LMS")

		self.assertTrue(result["success"], result)
		self.assertIsNone(result["data"]["product"])
		self.assertEqual(result["data"]["entitlements"], [])
		self.assertIsNone(result["data"]["next_billing_date"])


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase I — scheduled jobs. Each sweep is tested for: the
# happy path (a due row gets acted on), the not-due path (left alone),
# and per-row failure isolation (one bad row doesn't abort the sweep).
# ---------------------------------------------------------------------------


class FinalizePendingCancellationsTest(unittest.TestCase):
	def test_finalizes_due_cancellations(self):
		fake_frappe.get_all = mock.Mock(return_value=[types.SimpleNamespace(name="sub-1")])
		sub = mock.Mock(status="active", plan="plan-1", tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})

		with mock.patch.object(subscription_service, "_write_subscription_event"):
			result = subscription_service.finalize_pending_cancellations()

		self.assertEqual(result, [{"subscription": "sub-1"}])
		self.assertEqual(sub.status, "cancelled")
		sub.save.assert_called_once_with(ignore_permissions=True)

	def test_empty_when_nothing_due(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		result = subscription_service.finalize_pending_cancellations()
		self.assertEqual(result, [])

	def test_one_bad_row_does_not_abort_the_sweep(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[types.SimpleNamespace(name="sub-bad"), types.SimpleNamespace(name="sub-good")]
		)
		good_sub = mock.Mock(status="active", plan="plan-1", tenant="tenant-1", product="QMP_LMS")
		good_sub.name = "sub-good"

		def _get_doc(*args, **kwargs):
			# Two call shapes hit this mock: the (doctype, name) lookup
			# below, AND write_audit_event()'s own frappe.get_doc({...})
			# construction call — the latter must not also raise, or
			# "sub-good"'s otherwise-successful processing would be
			# wrongly swallowed by the same try/except this test exists
			# to prove doesn't swallow the WRONG row.
			if len(args) == 2:
				if args[1] == "sub-bad":
					raise Exception("boom")
				return good_sub
			return mock.Mock()

		fake_frappe.get_doc = mock.Mock(side_effect=_get_doc)

		with mock.patch.object(subscription_service, "_write_subscription_event"):
			result = subscription_service.finalize_pending_cancellations()

		self.assertEqual(result, [{"subscription": "sub-good"}])
		fake_frappe.log_error.assert_called()


class ApplyDueScheduledDowngradesTest(unittest.TestCase):
	def test_applies_due_downgrade(self):
		fake_frappe.get_all = mock.Mock(return_value=[types.SimpleNamespace(name="sub-1")])
		new_sub = mock.Mock()
		new_sub.name = "sub-2"
		with mock.patch.object(subscription_service, "apply_scheduled_plan_change", return_value=new_sub) as apply_mock:
			result = subscription_service.apply_due_scheduled_downgrades()

		apply_mock.assert_called_once_with("sub-1")
		self.assertEqual(result, [{"subscription": "sub-1", "new_subscription": "sub-2"}])

	def test_noop_row_is_not_reported_as_applied(self):
		fake_frappe.get_all = mock.Mock(return_value=[types.SimpleNamespace(name="sub-1")])
		with mock.patch.object(subscription_service, "apply_scheduled_plan_change", return_value=None):
			result = subscription_service.apply_due_scheduled_downgrades()
		self.assertEqual(result, [])

	def test_one_bad_row_does_not_abort_the_sweep(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[types.SimpleNamespace(name="sub-bad"), types.SimpleNamespace(name="sub-good")]
		)
		new_sub = mock.Mock()
		new_sub.name = "sub-good-2"

		def _apply(name):
			if name == "sub-bad":
				raise Exception("boom")
			return new_sub

		with mock.patch.object(subscription_service, "apply_scheduled_plan_change", side_effect=_apply):
			result = subscription_service.apply_due_scheduled_downgrades()

		self.assertEqual(result, [{"subscription": "sub-good", "new_subscription": "sub-good-2"}])
		fake_frappe.log_error.assert_called()


class ExpireStaleTrialsTest(unittest.TestCase):
	def test_suspends_unlinked_stale_trial(self):
		fake_frappe.get_all = mock.Mock(return_value=[types.SimpleNamespace(name="sub-1")])
		sub = mock.Mock(status="trialing", tenant="tenant-1", product="QMP_LMS")
		sub.name = "sub-1"
		fake_frappe.get_doc = _make_get_doc({("QTT Product Subscription", "sub-1"): sub})

		result = billing_service.expire_stale_trials()

		self.assertEqual(result, [{"subscription": "sub-1"}])
		self.assertEqual(sub.status, "suspended")

	def test_only_queries_unlinked_trialing_subscriptions(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		billing_service.expire_stale_trials()
		_, kwargs = fake_frappe.get_all.call_args
		self.assertEqual(kwargs["filters"]["status"], "trialing")
		self.assertEqual(kwargs["filters"]["razorpay_subscription_id"], ["is", "not set"])

	def test_empty_when_nothing_stale(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		self.assertEqual(billing_service.expire_stale_trials(), [])


class ExpireStaleInvitationsTest(unittest.TestCase):
	def test_expires_stale_pending_invitations(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[types.SimpleNamespace(name="inv-1", tenant="tenant-1")]
		)
		fake_frappe.db.set_value = mock.Mock()

		result = api_invitation.expire_stale_invitations()

		self.assertEqual(result, [{"invitation": "inv-1"}])
		fake_frappe.db.set_value.assert_called_once_with("QTT Invitation", "inv-1", "status", "expired")

	def test_empty_when_nothing_stale(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		self.assertEqual(api_invitation.expire_stale_invitations(), [])

	def test_one_bad_row_does_not_abort_the_sweep(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[
				types.SimpleNamespace(name="inv-bad", tenant="tenant-1"),
				types.SimpleNamespace(name="inv-good", tenant="tenant-1"),
			]
		)

		def _set_value(doctype, name, field, value):
			if name == "inv-bad":
				raise Exception("boom")

		fake_frappe.db.set_value = mock.Mock(side_effect=_set_value)

		result = api_invitation.expire_stale_invitations()

		self.assertEqual(result, [{"invitation": "inv-good"}])
		fake_frappe.log_error.assert_called()


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase J — closing the remaining gaps in the master
# checklist (Membership, Product access) that no earlier phase's own
# testing wave happened to cover, since api/session.py and the
# governance half of api/product_access.py are pre-Phase-A code.
# ---------------------------------------------------------------------------


class CreateTenantApiTest(unittest.TestCase):
	def test_guest_rejected(self):
		with mock.patch.object(fake_frappe, "session", types.SimpleNamespace(user="Guest")):
			with self.assertRaises(Exception):
				api_session.create_tenant("Acme", "acme")

	def test_missing_tenant_name_rejected(self):
		with self.assertRaises(Exception):
			api_session.create_tenant("   ", "acme")

	def test_missing_slug_rejected(self):
		with self.assertRaises(Exception):
			api_session.create_tenant("Acme", "   ")

	def test_duplicate_slug_rejected(self):
		fake_frappe.db.exists = mock.Mock(return_value=True)
		with self.assertRaises(Exception):
			api_session.create_tenant("Acme", "acme")

	def test_success_creates_tenant_and_owner_membership_atomically(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		tenant_doc = mock.Mock()
		tenant_doc.name = "tenant-1"
		membership_doc = mock.Mock()
		membership_doc.name = "membership-1"

		captured_payloads = []

		def _get_doc(payload):
			# A third shape (QTT Audit Log, from write_audit_event()) also
			# hits this mock — must not be mistaken for the membership doc.
			captured_payloads.append(payload)
			if payload["doctype"] == "QTT Tenant":
				return tenant_doc
			if payload["doctype"] == "QTT Tenant Membership":
				return membership_doc
			return mock.Mock()

		fake_frappe.get_doc = mock.Mock(side_effect=_get_doc)

		with mock.patch.object(api_session, "_switch_tenant", return_value={"tenant_role": "Tenant Owner"}) as switch_mock:
			result = api_session.create_tenant("Acme Academy", "acme-academy")

		self.assertEqual(result["tenant"], "tenant-1")
		self.assertEqual(result["tenant_role"], "Tenant Owner")
		tenant_doc.insert.assert_called_once_with(ignore_permissions=True)
		membership_doc.insert.assert_called_once_with(ignore_permissions=True)
		membership_payload = next(p for p in captured_payloads if p["doctype"] == "QTT Tenant Membership")
		self.assertEqual(membership_payload["tenant_role"], "Tenant Owner")
		self.assertEqual(membership_payload["status"], "active")
		switch_mock.assert_called_once_with("tenant-1", user=fake_frappe.session.user)


class GetMyMembershipsApiTest(unittest.TestCase):
	def test_empty_when_no_memberships(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		self.assertEqual(api_session.get_my_memberships(), [])

	def test_returns_memberships_with_tenant_info_attached(self):
		fake_frappe.get_all = mock.Mock(
			side_effect=[
				[types.SimpleNamespace(tenant="tenant-1", tenant_role="Tenant Owner")],
				[_FrappeDict(name="tenant-1", tenant_name="Acme", status="active")],
			]
		)
		result = api_session.get_my_memberships()
		self.assertEqual(
			result,
			[{"tenant": "tenant-1", "tenant_name": "Acme", "tenant_status": "active", "tenant_role": "Tenant Owner"}],
		)


class GetActiveTenantApiTest(unittest.TestCase):
	def test_none_when_no_active_tenant(self):
		with mock.patch.object(api_session, "resolve_active_tenant", return_value=None):
			self.assertIsNone(api_session.get_active_tenant())

	def test_returns_tenant_info_when_active(self):
		with mock.patch.object(api_session, "resolve_active_tenant", return_value="tenant-1"):
			fake_frappe.db.get_value = mock.Mock(
				return_value=types.SimpleNamespace(tenant_name="Acme", status="active")
			)
			result = api_session.get_active_tenant()
		self.assertEqual(result, {"tenant": "tenant-1", "tenant_name": "Acme", "tenant_status": "active"})

	def test_none_when_active_tenant_pointer_is_stale(self):
		# Cache says a tenant is active, but the QTT Tenant row can't be
		# found (deleted, or the cache is simply stale) — fail closed to
		# None, never raise.
		with mock.patch.object(api_session, "resolve_active_tenant", return_value="tenant-deleted"):
			fake_frappe.db.get_value = mock.Mock(return_value=None)
			self.assertIsNone(api_session.get_active_tenant())


class GrantProductAccessTest(unittest.TestCase):
	def test_creates_new_access_when_none_exists(self):
		with mock.patch.object(api_product_access, "require_tenant_role"):
			fake_frappe.db.get_value = mock.Mock(return_value="membership-1")
			fake_frappe.db.exists = mock.Mock(return_value=False)
			new_access = mock.Mock(product_role="Manager", status="active")
			new_access.name = "access-1"

			def _get_doc(payload):
				return new_access if payload["doctype"] == "QTT Product Access" else mock.Mock()

			fake_frappe.get_doc = mock.Mock(side_effect=_get_doc)

			result = api_product_access.grant_product_access("tenant-1", "user@example.com", "QMP_LMS", "Manager")

		self.assertEqual(result["name"], "access-1")
		new_access.insert.assert_called_once_with(ignore_permissions=True)

	def test_reactivates_existing_access_instead_of_duplicating(self):
		with mock.patch.object(api_product_access, "require_tenant_role"):
			fake_frappe.db.get_value = mock.Mock(return_value="membership-1")
			fake_frappe.db.exists = mock.Mock(return_value="access-existing")
			existing_access = mock.Mock()
			existing_access.name = "access-existing"
			fake_frappe.get_doc = _make_get_doc({("QTT Product Access", "access-existing"): existing_access})

			api_product_access.grant_product_access("tenant-1", "user@example.com", "QMP_LMS", "Instructor")

		self.assertEqual(existing_access.product_role, "Instructor")
		self.assertEqual(existing_access.status, "active")
		existing_access.save.assert_called_once_with(ignore_permissions=True)
		existing_access.insert.assert_not_called()

	def test_target_user_not_an_active_member_is_rejected(self):
		with mock.patch.object(api_product_access, "require_tenant_role"):
			fake_frappe.db.get_value = mock.Mock(return_value=None)  # no active membership found
			with self.assertRaises(Exception):
				api_product_access.grant_product_access("tenant-1", "stranger@example.com", "QMP_LMS", "Manager")


class RevokeProductAccessTest(unittest.TestCase):
	def test_soft_revokes_without_deleting(self):
		with mock.patch.object(api_product_access, "require_tenant_role"):
			fake_frappe.db.get_value = mock.Mock(return_value="membership-1")
			fake_frappe.db.exists = mock.Mock(return_value="access-1")
			access = mock.Mock()
			access.name = "access-1"
			fake_frappe.get_doc = _make_get_doc({("QTT Product Access", "access-1"): access})

			result = api_product_access.revoke_product_access("tenant-1", "user@example.com", "QMP_LMS")

		self.assertEqual(access.status, "removed")
		access.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result["status"], "removed")

	def test_no_existing_access_record_is_rejected(self):
		with mock.patch.object(api_product_access, "require_tenant_role"):
			fake_frappe.db.get_value = mock.Mock(return_value="membership-1")
			fake_frappe.db.exists = mock.Mock(return_value=None)
			with self.assertRaises(Exception):
				api_product_access.revoke_product_access("tenant-1", "user@example.com", "QMP_LMS")


class ChangeProductRoleTest(unittest.TestCase):
	def test_changes_role_re_validated_by_the_doctype_itself(self):
		with mock.patch.object(api_product_access, "require_tenant_role"):
			fake_frappe.db.get_value = mock.Mock(return_value="membership-1")
			fake_frappe.db.exists = mock.Mock(return_value="access-1")
			access = mock.Mock(product_role="Instructor")
			access.name = "access-1"
			fake_frappe.get_doc = _make_get_doc({("QTT Product Access", "access-1"): access})

			result = api_product_access.change_product_role("tenant-1", "user@example.com", "QMP_LMS", "Manager")

		self.assertEqual(access.product_role, "Manager")
		access.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result["product_role"], "Manager")


class GetProductRoleOptionsTest(unittest.TestCase):
	"""Desk UI fix — qtt_product_access.js's dynamic product_role
	dropdown reads this endpoint. Pins the value/label reshaping: this is
	the one place role_key and role_name are allowed to differ, so the
	test uses a case where they do, rather than the current
	identical-by-coincidence QMP_LMS seed data."""

	def test_reshapes_role_key_and_role_name_into_value_label_pairs(self):
		fake_frappe.get_all = mock.Mock(
			return_value=[
				_FrappeDict(role_key="manager", role_name="Manager"),
				_FrappeDict(role_key="instructor", role_name="Instructor"),
			]
		)
		result = api_product.get_product_role_options("QMP_LMS")
		self.assertEqual(
			result,
			[{"value": "manager", "label": "Manager"}, {"value": "instructor", "label": "Instructor"}],
		)
		fake_frappe.get_all.assert_called_once_with(
			"QTT Product Role", filters={"parent": "QMP_LMS"}, fields=["role_key", "role_name"], order_by="idx asc"
		)

	def test_unknown_product_returns_empty_list_not_an_error(self):
		fake_frappe.get_all = mock.Mock(return_value=[])
		result = api_product.get_product_role_options("NOT_A_REAL_PRODUCT")
		self.assertEqual(result, [])


class TenantMembershipTitleTest(unittest.TestCase):
	"""Desk UI fix — QTT Tenant Membership.validate()'s new _set_title()."""

	def test_title_combines_user_and_tenant_name(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_frappe.db.get_value = mock.Mock(return_value="ABC School")

		membership = QTTTenantMembership.__new__(QTTTenantMembership)
		membership.user = "nitranjith2019@gmail.com"
		membership.tenant = "u7o73i0uao"
		membership.name = None
		membership.validate()

		self.assertEqual(membership.membership_title, "nitranjith2019@gmail.com — ABC School")

	def test_falls_back_to_tenant_id_if_tenant_name_missing(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_frappe.db.get_value = mock.Mock(return_value=None)

		membership = QTTTenantMembership.__new__(QTTTenantMembership)
		membership.user = "user@example.com"
		membership.tenant = "some-tenant-id"
		membership.name = None
		membership.validate()

		self.assertEqual(membership.membership_title, "user@example.com — some-tenant-id")


# ---------------------------------------------------------------------------
# Production-readiness audit, P0 — api/billing.py::start_subscription_checkout(),
# api/ai.py::generate(), ai/services/credit_service.py::grant_plan_credits().
# ---------------------------------------------------------------------------


class StartSubscriptionCheckoutTest(unittest.TestCase):
	def test_no_active_tenant_rejected(self):
		with mock.patch.object(api_billing, "resolve_active_tenant", return_value=None):
			result = api_billing.start_subscription_checkout("QMP_LMS")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "TENANT_ACCESS_DENIED")

	def test_non_owner_rejected(self):
		with mock.patch.object(api_billing, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(
				api_billing, "require_tenant_role", side_effect=fake_frappe.PermissionError("nope")
			):
				result = api_billing.start_subscription_checkout("QMP_LMS")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "BILLING_ROLE_REQUIRED")

	def test_no_subscription_rejected(self):
		with mock.patch.object(api_billing, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_billing, "require_tenant_role"):
				with mock.patch.object(subscription_service, "get_current_subscription", return_value=None):
					result = api_billing.start_subscription_checkout("QMP_LMS")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "SUBSCRIPTION_NOT_FOUND")

	def test_cancelled_subscription_rejected(self):
		sub = mock.Mock(status="cancelled")
		with mock.patch.object(api_billing, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_billing, "require_tenant_role"):
				with mock.patch.object(subscription_service, "get_current_subscription", return_value=sub):
					result = api_billing.start_subscription_checkout("QMP_LMS")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "SUBSCRIPTION_CANCELLED")

	def test_already_linked_reconstructs_checkout_without_relinking(self):
		sub = mock.Mock(status="active", razorpay_subscription_id="sub_rzp_123")
		sub.name = "sub-1"
		with mock.patch.object(api_billing, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_billing, "require_tenant_role"):
				with mock.patch.object(subscription_service, "get_current_subscription", return_value=sub):
					with mock.patch.object(billing_service, "get_gateway_public_key", return_value="rzp_key_id"):
						with mock.patch.object(billing_service, "create_razorpay_subscription") as create_mock:
							result = api_billing.start_subscription_checkout("QMP_LMS")

		create_mock.assert_not_called()
		self.assertTrue(result["success"], result)
		self.assertTrue(result["data"]["already_linked"])
		self.assertEqual(result["data"]["checkout"], {"subscription_id": "sub_rzp_123", "key_id": "rzp_key_id"})

	def test_not_yet_linked_calls_create_razorpay_subscription(self):
		sub = mock.Mock(status="active", razorpay_subscription_id=None)
		sub.name = "sub-1"
		with mock.patch.object(api_billing, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_billing, "require_tenant_role"):
				with mock.patch.object(subscription_service, "get_current_subscription", return_value=sub):
					with mock.patch.object(
						billing_service,
						"create_razorpay_subscription",
						return_value={"checkout": {"subscription_id": "sub_rzp_new", "key_id": "rzp_key_id"}},
					) as create_mock:
						result = api_billing.start_subscription_checkout("QMP_LMS")

		create_mock.assert_called_once_with("sub-1")
		self.assertTrue(result["success"], result)
		self.assertFalse(result["data"]["already_linked"])
		self.assertEqual(result["data"]["checkout"]["subscription_id"], "sub_rzp_new")

	def test_unexpected_error_mapped_to_payment_required(self):
		with mock.patch.object(api_billing, "resolve_active_tenant", side_effect=Exception("boom")):
			result = api_billing.start_subscription_checkout("QMP_LMS")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "PAYMENT_REQUIRED")


class GenerateAiFeatureTest(unittest.TestCase):
	def test_no_active_tenant_rejected(self):
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value=None):
			result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "TENANT_ACCESS_DENIED")

	def test_no_product_access_rejected(self):
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(
				api_ai, "require_product_access", side_effect=fake_frappe.PermissionError("nope")
			):
				result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "PRODUCT_ACCESS_DENIED")

	def test_feature_not_configured_rejected(self):
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(
					api_ai, "get_ai_feature_handler", side_effect=FeatureNotConfigured("no handler")
				):
					result = api_ai.generate("QMP_LMS", "unknown_feature")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "AI_FEATURE_NOT_CONFIGURED")

	def test_handler_permission_error_mapped_to_role_permission_denied(self):
		handler = mock.Mock(side_effect=fake_frappe.PermissionError("Student cannot do this"))
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(api_ai, "get_ai_feature_handler", return_value=handler):
					result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "ROLE_PERMISSION_DENIED")

	def test_insufficient_credits_mapped_from_plain_validation_error(self):
		handler = mock.Mock(side_effect=fake_frappe.ValidationError("Insufficient AI credits"))
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(api_ai, "get_ai_feature_handler", return_value=handler):
					result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "AI_CREDITS_EXHAUSTED")

	def test_other_validation_error_mapped_generically(self):
		handler = mock.Mock(side_effect=fake_frappe.ValidationError("topic is required"))
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(api_ai, "get_ai_feature_handler", return_value=handler):
					result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")

	def test_provider_failure_mapped_to_ai_provider_unavailable(self):
		from qtt_platform.ai.core.exceptions import AiProviderException

		handler = mock.Mock(side_effect=AiProviderException("timeout", "deepseek", "deepseek timed out"))
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(api_ai, "get_ai_feature_handler", return_value=handler):
					result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "AI_PROVIDER_UNAVAILABLE")

	def test_string_inputs_are_json_parsed_before_dispatch(self):
		handler = mock.Mock(return_value={"questions": []})
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(api_ai, "get_ai_feature_handler", return_value=handler):
					result = api_ai.generate("QMP_LMS", "quiz_generation", inputs='{"topic": "Algebra"}')

		handler.assert_called_once_with(tenant="tenant-1", user="Administrator", inputs={"topic": "Algebra"})
		self.assertTrue(result["success"], result)
		self.assertEqual(result["data"], {"questions": []})

	def test_success_path_returns_handler_result(self):
		handler = mock.Mock(return_value={"questions": [{"question_text": "2+2?"}]})
		with mock.patch.object(api_ai, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(api_ai, "require_product_access"):
				with mock.patch.object(api_ai, "get_ai_feature_handler", return_value=handler):
					result = api_ai.generate("QMP_LMS", "quiz_generation", inputs={"topic": "Algebra"})

		handler.assert_called_once_with(tenant="tenant-1", user="Administrator", inputs={"topic": "Algebra"})
		self.assertTrue(result["success"], result)
		self.assertEqual(len(result["data"]["questions"]), 1)

	def test_unexpected_error_mapped_to_internal_error(self):
		with mock.patch.object(api_ai, "resolve_active_tenant", side_effect=Exception("boom")):
			result = api_ai.generate("QMP_LMS", "quiz_generation")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "INTERNAL_ERROR")


class DeductCreditsTest(unittest.TestCase):
	"""Regression coverage for a real bug caught via live production
	verification (P6): frappe.db.sql() returns `()` for ANY UPDATE
	statement (no result set to fetch — see the fix's own comment in
	credit_service.py), so the original `if not affected:` check — where
	`affected` was db.sql()'s own return value — was always true
	regardless of whether the UPDATE actually matched a row. A real
	signup + real AI generation call against production reported
	"Insufficient AI credits" despite a real, positive wallet balance,
	which is what surfaced this. The fix reads `frappe.db._cursor.rowcount`
	instead — these tests pin that against both outcomes."""

	def setUp(self):
		fake_frappe.db.exists = mock.Mock(return_value=False)
		fake_frappe.db.get_value = mock.Mock(return_value="wallet-1")
		fake_frappe.db.sql = mock.Mock(return_value=())
		fake_frappe.get_doc = mock.Mock()

	def test_sufficient_balance_deducts_and_records_ledger_entry(self):
		fake_frappe.db._cursor = types.SimpleNamespace(rowcount=1)
		result = credit_service.deduct_credits("tenant-1", "QMP_LMS", 5.0, reference="ref-1")
		self.assertEqual(result, {"ok": True})
		fake_frappe.get_doc.assert_called_once()
		ledger_doc = fake_frappe.get_doc.call_args[0][0]
		self.assertEqual(ledger_doc["amount"], -5.0)
		self.assertEqual(ledger_doc["source"], "consumption")

	def test_insufficient_balance_reports_not_ok_without_writing_ledger(self):
		fake_frappe.db._cursor = types.SimpleNamespace(rowcount=0)
		result = credit_service.deduct_credits("tenant-1", "QMP_LMS", 5.0, reference="ref-2")
		self.assertEqual(result, {"ok": False, "reason": "insufficient_credits"})
		fake_frappe.get_doc.assert_not_called()

	def test_retried_reference_is_a_no_op(self):
		fake_frappe.db.exists = mock.Mock(return_value=True)
		fake_frappe.db._cursor = types.SimpleNamespace(rowcount=0)
		result = credit_service.deduct_credits("tenant-1", "QMP_LMS", 5.0, reference="ref-already-done")
		self.assertEqual(result, {"ok": True, "already_processed": True})
		fake_frappe.db.sql.assert_not_called()

	def test_does_not_rely_on_db_sql_return_value(self):
		# The specific regression: db.sql() returning its real-world `()`
		# for an UPDATE must NOT be mistaken for "no rows affected" when
		# rowcount says otherwise.
		fake_frappe.db.sql = mock.Mock(return_value=())
		fake_frappe.db._cursor = types.SimpleNamespace(rowcount=1)
		result = credit_service.deduct_credits("tenant-1", "QMP_LMS", 5.0, reference="ref-3")
		self.assertTrue(result["ok"])


class GrantPlanCreditsTest(unittest.TestCase):
	def test_grants_the_plans_numeric_feature_value(self):
		fake_frappe.db.get_value = mock.Mock(return_value="100")
		with mock.patch.object(credit_service, "grant_credits") as grant_mock:
			amount = credit_service.grant_plan_credits(
				"tenant-1", "QMP_LMS", "plan-professional", "ai_credits_grant",
				source="subscription_grant", reference="signup:sub-1",
			)
		self.assertEqual(amount, 100.0)
		grant_mock.assert_called_once_with(
			"tenant-1", "QMP_LMS", 100.0, "subscription_grant", reference="signup:sub-1"
		)

	def test_reads_the_correct_plan_feature_row(self):
		fake_frappe.db.get_value = mock.Mock(return_value="20")
		with mock.patch.object(credit_service, "grant_credits"):
			credit_service.grant_plan_credits(
				"tenant-1", "QMP_LMS", "plan-starter", "ai_credits_grant", source="subscription_grant"
			)
		fake_frappe.db.get_value.assert_called_once_with(
			"QTT Plan Feature", {"parent": "plan-starter", "feature_key": "ai_credits_grant"}, "limit_value"
		)

	def test_no_such_feature_on_plan_returns_zero_and_does_not_grant(self):
		fake_frappe.db.get_value = mock.Mock(return_value=None)
		with mock.patch.object(credit_service, "grant_credits") as grant_mock:
			amount = credit_service.grant_plan_credits(
				"tenant-1", "QMP_LMS", "plan-basic", "ai_credits_grant", source="subscription_grant"
			)
		self.assertEqual(amount, 0.0)
		grant_mock.assert_not_called()

	def test_zero_valued_feature_returns_zero_and_does_not_grant(self):
		fake_frappe.db.get_value = mock.Mock(return_value="0")
		with mock.patch.object(credit_service, "grant_credits") as grant_mock:
			amount = credit_service.grant_plan_credits(
				"tenant-1", "QMP_LMS", "plan-basic", "ai_credits_grant", source="subscription_grant"
			)
		self.assertEqual(amount, 0.0)
		grant_mock.assert_not_called()

	def test_non_numeric_feature_value_returns_zero_and_does_not_grant(self):
		fake_frappe.db.get_value = mock.Mock(return_value="not-a-number")
		with mock.patch.object(credit_service, "grant_credits") as grant_mock:
			amount = credit_service.grant_plan_credits(
				"tenant-1", "QMP_LMS", "plan-basic", "ai_credits_grant", source="subscription_grant"
			)
		self.assertEqual(amount, 0.0)
		grant_mock.assert_not_called()


class AiFeatureRegistryTest(unittest.TestCase):
	def test_raises_feature_not_configured_when_nothing_registered(self):
		fake_frappe.get_hooks = mock.Mock(return_value={})
		fake_frappe.cache = mock.Mock(
			return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
		)
		with self.assertRaises(FeatureNotConfigured):
			feature_registry.get_ai_feature_handler("QMP_LMS", "quiz_generation")

	def test_resolves_a_registered_handler_via_get_attr(self):
		fake_frappe.get_hooks = mock.Mock(
			return_value={"QMP_LMS::quiz_generation": "qmp_lms_bridge.ai_features.generate_quiz"}
		)
		fake_frappe.cache = mock.Mock(
			return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
		)
		sentinel_handler = mock.Mock()
		fake_frappe.get_attr = mock.Mock(return_value=sentinel_handler)

		handler = feature_registry.get_ai_feature_handler("QMP_LMS", "quiz_generation")

		self.assertIs(handler, sentinel_handler)
		fake_frappe.get_attr.assert_called_once_with("qmp_lms_bridge.ai_features.generate_quiz")

	def test_resolves_the_real_list_wrapped_hook_shape(self):
		# Regression coverage for the real bug caught via live production
		# testing (Part C-J): frappe.get_hooks() wraps every key's value
		# in a list of per-declaring-app contributions — confirmed live
		# against app.quizmasterplus.in — not a bare dotted-path string.
		# The pre-fix code passed that list straight to frappe.get_attr(),
		# which crashed with AttributeError: 'list' object has no
		# attribute 'split'. This is why api.ai.generate() had never
		# worked end-to-end even though the handler itself did when
		# called directly, bypassing this registry.
		fake_frappe.get_hooks = mock.Mock(
			return_value={"QMP_LMS::quiz_generation": ["qmp_lms_bridge.ai_features.generate_quiz"]}
		)
		fake_frappe.cache = mock.Mock(
			return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
		)
		sentinel_handler = mock.Mock()
		fake_frappe.get_attr = mock.Mock(return_value=sentinel_handler)

		handler = feature_registry.get_ai_feature_handler("QMP_LMS", "quiz_generation")

		self.assertIs(handler, sentinel_handler)
		fake_frappe.get_attr.assert_called_once_with("qmp_lms_bridge.ai_features.generate_quiz")


class UsageRegistryRealHookShapeTest(unittest.TestCase):
	"""Same regression as AiFeatureRegistryTest.test_resolves_the_real_list_wrapped_hook_shape,
	pinned for usage/registry.py — the first of the three registries this
	bug was found in."""

	def test_resolves_the_real_list_wrapped_hook_shape(self):
		fake_frappe.get_hooks = mock.Mock(
			return_value={"QMP_LMS::max_students": ["qmp_lms_bridge.usage.count_students"]}
		)
		fake_frappe.cache = mock.Mock(
			return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
		)
		sentinel = mock.Mock(return_value=25)
		fake_frappe.get_attr = mock.Mock(return_value=sentinel)

		resolver = usage_registry.get_usage_resolver("QMP_LMS", "max_students")

		self.assertIs(resolver, sentinel)
		fake_frappe.get_attr.assert_called_once_with("qmp_lms_bridge.usage.count_students")


if __name__ == "__main__":
	unittest.main()
