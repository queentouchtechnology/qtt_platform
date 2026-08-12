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
"""

import hashlib
import hmac

import frappe
import requests
from frappe.utils.password import get_decrypted_password

from qtt_platform.billing.gateways.base import OrderResult, PaymentGateway, WebhookEvent

GATEWAY_KEY = "razorpay"
API_BASE = "https://api.razorpay.com/v1"


class RazorpayGateway(PaymentGateway):
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
		import json

		data = json.loads(payload_body)
		payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {})
		return WebhookEvent(
			event_type=data.get("event", "unknown"),
			gateway_reference=payment_entity.get("order_id") or payment_entity.get("id"),
			amount=(payment_entity.get("amount") or 0) / 100,  # back to rupees
			currency=payment_entity.get("currency", "INR"),
			raw_payload=data,
		)
