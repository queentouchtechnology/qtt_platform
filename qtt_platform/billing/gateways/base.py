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


# ---------------------------------------------------------------------------
# Recurring-subscription capability (SaaS lifecycle Phase C) — deliberately
# a SEPARATE, optional interface, not added to PaymentGateway above. The
# existing Orders-based flow (create_order/parse_webhook_event) is untouched
# and still the whole contract for a gateway that only does one-time
# payments; a gateway implements SubscriptionCapableGateway in ADDITION to
# PaymentGateway only if it actually supports recurring subscriptions
# (Razorpay does — see razorpay_gateway.py). Nothing in the existing
# Orders-based billing/service.py functions depends on this interface.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionResult:
	#: The gateway's own subscription id — stored as
	#: QTT Product Subscription.razorpay_subscription_id.
	gateway_subscription_id: str
	#: The gateway's own raw status string at creation time (e.g.
	#: Razorpay's "created") — informational, never written directly into
	#: QTT Product Subscription.status, which stays governed by this
	#: app's own trial/active/past_due/cancelled vocabulary (unchanged).
	status: str
	#: Whatever the client SDK needs to complete checkout/authorization —
	#: for Razorpay, at minimum the subscription id and key_id.
	client_payload: dict


@dataclass(frozen=True)
class SubscriptionWebhookEvent:
	event_type: str  # gateway-specific string, e.g. "subscription.activated"
	gateway_subscription_id: str
	#: The gateway's own raw status for the subscription at the moment of
	#: this event (e.g. Razorpay's "active"/"halted"/"cancelled"). Mapping
	#: this to this app's own subscription state machine is Phase D's
	#: job, not this adapter's — this dataclass only reports what the
	#: gateway said.
	status: str
	#: Present only when the gateway has linked a customer to this
	#: subscription by this point (Razorpay populates this once the
	#: customer completes authorization, not before — see
	#: RazorpayGateway.create_subscription()'s own docstring). None if not
	#: yet available.
	customer_id: str | None
	raw_payload: dict


class SubscriptionCapableGateway(ABC):
	"""Optional capability a PaymentGateway subclass may additionally
	implement. See the module-level comment above this class for why it's
	kept separate from PaymentGateway itself."""

	@abstractmethod
	def create_plan(self, *, name: str, amount: float, currency: str, period: str, interval: int = 1) -> str:
		"""Creates a gateway-side recurring Plan and returns its id.
		Callers (qtt_platform.billing.service.ensure_razorpay_plan) are
		responsible for calling this AT MOST ONCE per QTT Plan and storing
		the result — this method itself has no reuse/dedup logic, it just
		performs one Create Plan call."""
		...

	@abstractmethod
	def create_subscription(
		self,
		*,
		gateway_plan_id: str,
		total_count: int,
		start_at: int | None = None,
		customer_notify: bool = True,
		notes: dict | None = None,
	) -> SubscriptionResult:
		"""Creates a gateway-side Subscription against an already-created
		Plan (gateway_plan_id). `start_at` (a Unix timestamp), when given,
		delays the first BILLING cycle to that moment — this is the trial
		mechanism (SaaS lifecycle Phase C / Part 11): the customer still
		completes checkout/authorization up front, but is not charged
		until `start_at`. No customer id is accepted here — Razorpay's own
		Create Subscription API does not take one; the customer is
		captured automatically once authorization completes (confirmed
		against Razorpay's current API documentation, not assumed)."""
		...

	@abstractmethod
	def cancel_subscription(self, *, gateway_subscription_id: str, cancel_at_cycle_end: bool) -> None: ...

	@abstractmethod
	def parse_subscription_webhook_event(self, payload_body: bytes) -> SubscriptionWebhookEvent:
		"""Called only after verify_webhook_signature() has already
		returned True — same ordering guarantee as parse_webhook_event()
		above, this method itself does not re-verify anything."""
		...

	@abstractmethod
	def fetch_subscription_status(self, *, gateway_subscription_id: str) -> str:
		"""Live GET of the gateway's own current status for this
		subscription (SaaS lifecycle Phase D — reconciliation). Returns
		just the raw status string; reconcile_subscriptions() applies the
		same status-mapping logic the webhook handler uses, so there is
		exactly one place that mapping lives."""
		...

	@abstractmethod
	def update_subscription_plan(
		self, *, gateway_subscription_id: str, gateway_plan_id: str, schedule_change_at: str
	) -> dict:
		"""Changes an EXISTING subscription's plan in place — SaaS
		lifecycle Phase E. Never creates a second gateway-side
		subscription; this always operates on the one subscription id a
		QTT Product Subscription lineage already has. `schedule_change_at`
		is gateway-vocabulary, not this app's own — Razorpay's real values
		are "now" (immediate — the upgrade policy) and "cycle_end"
		(deferred to the next billing cycle — the downgrade policy);
		other gateways implementing this interface later may use
		different literal values for the same two concepts, which is why
		this parameter is passed through verbatim rather than mapped
		through a shared enum. Returns the gateway's raw response dict —
		callers needing specific fields from it (e.g. confirmation the
		change was actually scheduled) read them from there, this
		interface doesn't invent a typed result for it."""
		...
