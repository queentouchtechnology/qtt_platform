"""
Pay-by-link for QTT invoices: the app opens `<site>/pay?invoice=…&t=…` in
the browser, where Razorpay Checkout collects the payment. The link is
signed per invoice with the site's own secret, so it can't be used for any
other invoice, and the amount always comes from the invoice on the server
(billing.service.create_payment_order). The Razorpay webhook marks the
invoice paid; whoever created the invoice reacts to that (doc_events on
QTT Invoice).
"""

import hashlib
import hmac
from urllib.parse import urlencode

import frappe
from frappe.utils import get_url

from qtt_platform.billing import service as billing_service


def _secret() -> bytes:
	key = frappe.local.conf.get("encryption_key") or frappe.local.conf.get("secret_key") or ""
	if not key:
		frappe.throw("Site has no encryption_key; can't sign payment links.")
	return f"qtt-pay:{key}".encode()


def sign(invoice: str) -> str:
	return hmac.new(_secret(), invoice.encode(), hashlib.sha256).hexdigest()[:40]


def verify(invoice: str, token: str) -> bool:
	return bool(invoice and token) and hmac.compare_digest(sign(invoice), token)


def payment_url(invoice: str) -> str:
	return f"{get_url().rstrip('/')}/pay?{urlencode({'invoice': invoice, 't': sign(invoice)})}"


def online_payments_on() -> bool:
	from qtt_platform.billing.gateways.registry import get_gateway

	try:
		return get_gateway("razorpay").is_configured()
	except Exception:
		return False


def checkout_payload(invoice: str) -> dict:
	"""Order for Razorpay Checkout (amount from the invoice, never from the request)."""
	return billing_service.create_payment_order(invoice)
