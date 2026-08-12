"""
Razorpay adapter — the first PaymentGateway implementation, matching
`razorpay_flutter` already being an (unused) pubspec dependency in the
Flutter app.

Built from Razorpay's well-established, publicly documented Orders API
and webhook conventions (Basic Auth on key_id:key_secret, amounts in the
smallest currency unit, HMAC-SHA256 webhook signatures over the raw
request body) — the same general-API-knowledge basis this project used
for the OpenAI-compatible chat completions client. Signature verification
itself (hmac.compare_digest over a standard HMAC-SHA256) is well-
established, correct cryptographic practice, not guessed. What HAS NOT
been done: an actual call against a real Razorpay sandbox account — no
such account/credentials were available this session. Verify the exact
webhook payload field nesting against Razorpay's current documentation
before relying on parse_webhook_event() in production; the shape below
matches their long-documented event structure but is not
execution-verified here.

SaaS lifecycle Phase C additionally implements SubscriptionCapableGateway
on this same class (Subscriptions API: /v1/plans, /v1/subscriptions,
/v1/subscriptions/:id/cancel) — fetched fresh from Razorpay's own current
API documentation while building this phase (razorpay.com/docs/api/...),
not from memory, given how consequential a wrong field name would be
here. Everything above this comment (the Orders implementation) is
unchanged.
"""

import hashlib
import hmac
import json

import frappe
import requests
from frappe.utils.password import get_decrypted_password

from qtt_platform.billing.gateways.base import (
	OrderResult,
	PaymentGateway,
	SubscriptionCapableGateway,
	SubscriptionResult,
	SubscriptionWebhookEvent,
	WebhookEvent,
)

GATEWAY_KEY = "razorpay"
API_BASE = "https://api.razorpay.com/v1"

#: Razorpay's billing_period vocabulary ("monthly"/"yearly", already used
#: by QTT Plan.billing_period, unchanged) maps directly onto Razorpay's
#: own `period` values for Create Plan — confirmed against their current
#: API docs, not guessed: Razorpay's period is itself literally
#: "monthly"/"yearly" (among others this app doesn't use, like "weekly").
_BILLING_PERIOD_TO_RAZORPAY_PERIOD = {
	"monthly": "monthly",
	"yearly": "yearly",
}


class RazorpayGateway(PaymentGateway, SubscriptionCapableGateway):
	gateway_key = GATEWAY_KEY

	def is_configured(self) -> bool:
		row = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, ["enabled", "key_id"], as_dict=True)
		return bool(row and row.enabled and row.key_id)

	def create_order(self, *, invoice_name: str, amount: float, currency: str) -> OrderResult:
		key_id = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, "key_id")
		key_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "key_secret")

		response = requests.post(
			f"{API_BASE}/orders",
			auth=(key_id, key_secret),
			json={
				# Razorpay amounts are in the smallest currency unit
				# (paise for INR) — hence *100.
				"amount": int(round(amount * 100)),
				"currency": currency,
				"receipt": invoice_name,
			},
			timeout=30,
		)
		response.raise_for_status()
		data = response.json()

		return OrderResult(
			gateway_order_id=data["id"],
			client_payload={
				"order_id": data["id"],
				"amount": data["amount"],
				"currency": data["currency"],
				"key_id": key_id,
			},
		)

	def verify_webhook_signature(self, payload_body: bytes, signature: str) -> bool:
		webhook_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "webhook_secret")
		expected = hmac.new(webhook_secret.encode(), payload_body, hashlib.sha256).hexdigest()
		# constant-time comparison — never a plain == on secret-derived values
		return hmac.compare_digest(expected, signature)

	def parse_webhook_event(self, payload_body: bytes) -> WebhookEvent:
		data = json.loads(payload_body)
		payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {})
		return WebhookEvent(
			event_type=data.get("event", "unknown"),
			gateway_reference=payment_entity.get("order_id") or payment_entity.get("id"),
			amount=(payment_entity.get("amount") or 0) / 100,  # back to rupees
			currency=payment_entity.get("currency", "INR"),
			raw_payload=data,
		)

	# -----------------------------------------------------------------
	# SubscriptionCapableGateway (SaaS lifecycle Phase C) — Subscriptions
	# API. Field names below verified against Razorpay's current API
	# documentation while building this phase, not from memory:
	#   POST /v1/plans                          -> create_plan
	#   POST /v1/subscriptions                  -> create_subscription
	#   POST /v1/subscriptions/:id/cancel        -> cancel_subscription
	#   webhook event names (subscription.*)     -> parse_subscription_webhook_event
	# -----------------------------------------------------------------

	def create_plan(self, *, name: str, amount: float, currency: str, period: str, interval: int = 1) -> str:
		razorpay_period = _BILLING_PERIOD_TO_RAZORPAY_PERIOD.get(period)
		if not razorpay_period:
			frappe.throw(f"Unsupported billing period for Razorpay: '{period}'.")

		key_id = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, "key_id")
		key_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "key_secret")

		response = requests.post(
			f"{API_BASE}/plans",
			auth=(key_id, key_secret),
			json={
				"period": razorpay_period,
				"interval": interval,
				"item": {
					# Razorpay amounts are in the smallest currency unit
					# (paise for INR) — same *100 convention as create_order().
					"name": name,
					"amount": int(round(amount * 100)),
					"currency": currency,
				},
			},
			timeout=30,
		)
		response.raise_for_status()
		return response.json()["id"]

	def create_subscription(
		self,
		*,
		gateway_plan_id: str,
		total_count: int,
		start_at: int | None = None,
		customer_notify: bool = True,
		notes: dict | None = None,
	) -> SubscriptionResult:
		key_id = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, "key_id")
		key_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "key_secret")

		body = {
			"plan_id": gateway_plan_id,
			"total_count": total_count,
			"customer_notify": 1 if customer_notify else 0,
		}
		if start_at is not None:
			body["start_at"] = start_at
		if notes:
			body["notes"] = notes

		response = requests.post(f"{API_BASE}/subscriptions", auth=(key_id, key_secret), json=body, timeout=30)
		response.raise_for_status()
		data = response.json()

		return SubscriptionResult(
			gateway_subscription_id=data["id"],
			status=data.get("status", "created"),
			client_payload={
				"subscription_id": data["id"],
				"key_id": key_id,
				"short_url": data.get("short_url"),
			},
		)

	def cancel_subscription(self, *, gateway_subscription_id: str, cancel_at_cycle_end: bool) -> None:
		key_id = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, "key_id")
		key_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "key_secret")

		response = requests.post(
			f"{API_BASE}/subscriptions/{gateway_subscription_id}/cancel",
			auth=(key_id, key_secret),
			json={"cancel_at_cycle_end": cancel_at_cycle_end},
			timeout=30,
		)
		response.raise_for_status()

	def parse_subscription_webhook_event(self, payload_body: bytes) -> SubscriptionWebhookEvent:
		data = json.loads(payload_body)
		subscription_entity = data.get("payload", {}).get("subscription", {}).get("entity", {})
		return SubscriptionWebhookEvent(
			event_type=data.get("event", "unknown"),
			gateway_subscription_id=subscription_entity.get("id"),
			status=subscription_entity.get("status", "unknown"),
			customer_id=subscription_entity.get("customer_id") or None,
			raw_payload=data,
		)

	def fetch_subscription_status(self, *, gateway_subscription_id: str) -> str:
		# GET /v1/subscriptions/:id — response includes a `status` field
		# with the same vocabulary as the webhook entity's status
		# (confirmed against Razorpay's current API docs while building
		# Phase D: created/authenticated/active/pending/halted/cancelled/
		# completed/expired).
		key_id = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, "key_id")
		key_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "key_secret")

		response = requests.get(
			f"{API_BASE}/subscriptions/{gateway_subscription_id}", auth=(key_id, key_secret), timeout=30
		)
		response.raise_for_status()
		return response.json().get("status", "unknown")

	def update_subscription_plan(
		self, *, gateway_subscription_id: str, gateway_plan_id: str, schedule_change_at: str
	) -> dict:
		# PATCH /v1/subscriptions/:id — confirmed against Razorpay's
		# current API docs while building Phase E: plan_id +
		# schedule_change_at ("now" | "cycle_end") natively supports both
		# the immediate-upgrade and deferred-downgrade policies via ONE
		# subscription id, with no separate subscription ever created.
		key_id = frappe.db.get_value("QTT Payment Gateway Config", GATEWAY_KEY, "key_id")
		key_secret = get_decrypted_password("QTT Payment Gateway Config", GATEWAY_KEY, "key_secret")

		response = requests.patch(
			f"{API_BASE}/subscriptions/{gateway_subscription_id}",
			auth=(key_id, key_secret),
			json={
				"plan_id": gateway_plan_id,
				"schedule_change_at": schedule_change_at,
				"customer_notify": True,
			},
			timeout=30,
		)
		response.raise_for_status()
		return response.json()
