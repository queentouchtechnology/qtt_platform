"""
Provider-agnostic payment gateway interface — QTT Invoice/QTT Payment
business logic never names a gateway. See the single-application
specification section 13: Razorpay is the first adapter; Stripe/others
are additional files implementing this same interface later, with zero
changes to billing/service.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderResult:
	#: The gateway's own order id — stored as QTT Payment Transaction.gateway_reference.
	gateway_order_id: str
	#: Whatever the client SDK needs to actually collect payment (a
	#: gateway-specific blob — Flutter's Razorpay SDK needs the order id,
	#: amount, currency, and key_id, for instance).
	client_payload: dict


@dataclass(frozen=True)
class WebhookEvent:
	event_type: str  # gateway-specific string, e.g. "payment.captured"
	gateway_reference: str  # order/payment id the event is about
	amount: float
	currency: str
	raw_payload: dict


class PaymentGateway(ABC):
	gateway_key: str

	@abstractmethod
	def is_configured(self) -> bool: ...

	@abstractmethod
	def create_order(self, *, invoice_name: str, amount: float, currency: str) -> OrderResult:
		"""Amount/currency are passed in explicitly by the caller — always
		read server-side from the QTT Invoice itself (billing/service.py),
		never accepted from a Flutter request parameter. See the hardening
		review section 10's explicit "no client-controlled amount" fix."""
		...

	@abstractmethod
	def verify_webhook_signature(self, payload_body: bytes, signature: str) -> bool: ...

	@abstractmethod
	def parse_webhook_event(self, payload_body: bytes) -> WebhookEvent:
		"""Called only after verify_webhook_signature() has already
		returned True — this method itself does not re-verify anything."""
		...
