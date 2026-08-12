"""
Invoice/payment lifecycle — the only code path that creates or transitions
a QTT Invoice/QTT Payment/QTT Payment Transaction. Every write uses
ignore_permissions=True, matching the same billing-immutability pattern as
subscription/service.py: no tenant-facing role holds DocPerm on any of
these doctypes.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime, today

from qtt_platform.audit import write_audit_event
from qtt_platform.billing.gateways.base import SubscriptionCapableGateway
from qtt_platform.billing.gateways.registry import get_gateway
from qtt_platform.subscription import service as subscription_service

#: Razorpay requires either total_count or end_at to bound a subscription
#: (confirmed against their current API docs) — there is no "recurring
#: forever" option. QTT plans are indefinite-until-cancelled, so this is
#: a deliberate, stated stand-in for "effectively unbounded": 10 years of
#: monthly billing. Not a guessed magic number — cancellation is always
#: driven by cancel_razorpay_subscription() below, never by this count
#: running out in practice.
_UNBOUNDED_TOTAL_COUNT = 120


def create_invoice(tenant: str, items: list[dict], *, due_in_days: int = 7) -> "frappe.model.document.Document":
	"""items: [{"subscription": <name>, "description": <str>, "amount": <float>}, ...]
	Created in `draft` status — call issue_invoice() to move it to `open`
	before a payment can be collected against it."""
	total = sum(item["amount"] for item in items)
	invoice = frappe.get_doc(
		{
			"doctype": "QTT Invoice",
			"tenant": tenant,
			"amount": total,
			"status": "draft",
			"due_date": add_days(today(), due_in_days),
			"items": items,
		}
	)
	invoice.insert(ignore_permissions=True)
	return invoice


def issue_invoice(invoice_name: str) -> None:
	frappe.db.set_value("QTT Invoice", invoice_name, "status", "open")


def create_payment_order(invoice_name: str, *, gateway_key: str = "razorpay") -> dict:
	"""Reads amount/currency from the QTT Invoice itself — never from a
	request parameter. This is the concrete fix for the hardening review
	section 10's "no client-controlled amount" requirement: there is no
	code path anywhere in this module that accepts an amount from a
	caller for a real charge."""
	invoice = frappe.get_doc("QTT Invoice", invoice_name)
	if invoice.status not in ("open",):
		frappe.throw(_("Cannot create a payment order for an invoice that isn't open."))

	gateway = get_gateway(gateway_key)
	if not gateway.is_configured():
		frappe.throw(_("Payment gateway '{0}' is not configured.").format(gateway_key))

	order = gateway.create_order(invoice_name=invoice_name, amount=invoice.amount, currency=invoice.currency)

	frappe.get_doc(
		{
			"doctype": "QTT Payment Transaction",
			"invoice": invoice_name,
			"gateway": gateway_key,
			"gateway_reference": order.gateway_order_id,
			"status": "created",
		}
	).insert(ignore_permissions=True)

	return order.client_payload


def process_webhook(
	gateway_key: str, payload_body: bytes, signature: str, *, gateway_event_id: str | None = None
) -> dict:
	"""The one entry point for inbound gateway webhooks. Verifies the
	signature BEFORE reading a single field of the payload (hardening
	review section 10) — an invalid signature is rejected outright, no
	processing, no state change, no exception detail leaked back to the
	caller beyond a generic rejection.

	SaaS lifecycle Phase D: Razorpay delivers BOTH one-time-payment events
	(payment.captured, ...) and subscription lifecycle events
	(subscription.*) to the same configured webhook URL — this function
	now dispatches by event-name prefix, after the one shared signature
	check above. `gateway_event_id` (Razorpay: the X-Razorpay-Event-Id
	header — confirmed unique-per-delivery against Razorpay's own webhook
	docs, not guessed) is only required for the subscription path; the
	existing order/payment path's idempotency (QTT Payment Transaction.
	gateway_reference, unique) is unchanged and doesn't need it.
	"""
	gateway = get_gateway(gateway_key)

	if not gateway.verify_webhook_signature(payload_body, signature):
		_audit_webhook_rejected(gateway_key)
		frappe.throw(_("Invalid webhook signature."), frappe.PermissionError)

	try:
		raw_event_name = json.loads(payload_body).get("event", "")
	except (ValueError, TypeError):
		frappe.throw(_("Malformed webhook payload."), frappe.ValidationError)

	if raw_event_name.startswith("subscription."):
		return _process_subscription_webhook(gateway, gateway_key, payload_body, gateway_event_id)

	return _process_order_webhook(gateway, payload_body)


def _process_order_webhook(gateway, payload_body: bytes) -> dict:
	"""The pre-Phase-D webhook body, unchanged — one-time Orders/payment
	events only. Extracted into its own function so process_webhook()
	could gain the subscription-event branch above without touching a
	single line of this existing, already-reviewed logic."""
	event = gateway.parse_webhook_event(payload_body)

	# Idempotency: a redelivered webhook for a transaction we've already
	# recorded as succeeded is a safe no-op — checked before any write.
	existing_transaction = frappe.db.get_value(
		"QTT Payment Transaction", {"gateway_reference": event.gateway_reference}, ["name", "status"], as_dict=True
	)

	if existing_transaction and existing_transaction.status == "succeeded":
		return {"ok": True, "already_processed": True}

	if not existing_transaction:
		# A webhook arriving for a reference we never created an order for
		# is unusual (not necessarily malicious — could be a manual test
		# payment) but must still resolve to a real invoice via the
		# gateway's own reference, never trust a tenant/invoice id if the
		# payload happened to include one.
		frappe.throw(_("No matching payment transaction for this webhook."), frappe.ValidationError)

	transaction = frappe.get_doc("QTT Payment Transaction", existing_transaction.name)
	transaction.status = "succeeded"
	transaction.raw_payload = json.dumps(event.raw_payload)
	transaction.save(ignore_permissions=True)

	payment = frappe.get_doc(
		{
			"doctype": "QTT Payment",
			"invoice": transaction.invoice,
			"amount": event.amount,
			"currency": event.currency,
			"status": "succeeded",
			"paid_at": now_datetime(),
		}
	)
	payment.insert(ignore_permissions=True)

	transaction.payment = payment.name
	transaction.save(ignore_permissions=True)

	_mark_invoice_paid_and_activate_subscriptions(transaction.invoice)

	return {"ok": True}


def _mark_invoice_paid_and_activate_subscriptions(invoice_name: str) -> None:
	invoice = frappe.get_doc("QTT Invoice", invoice_name)
	# State-transition validation (hardening review section 10) — a stale
	# or duplicate webhook cannot un-void or re-pay an invoice that isn't
	# currently open.
	if invoice.status != "open":
		return
	invoice.status = "paid"
	invoice.save(ignore_permissions=True)
	write_audit_event(
		"payment_received", tenant=invoice.tenant, target_doctype="QTT Invoice", target_name=invoice.name
	)
	# Activating/renewing the subscription(s) this invoice covers is
	# deliberately left to whatever created the invoice in the first place
	# (api/subscription.py's subscribe()/change_plan() already activate a
	# subscription at creation time, independent of payment) — this
	# function's job ends at "the invoice is paid," matching the narrow
	# scope of what a webhook should decide.


def refund_payment(payment_name: str, amount: float, *, reference: str | None = None) -> "frappe.model.document.Document":
	"""Creates a NEW QTT Payment row — the original is never mutated, per
	the hardening review section 11's append-only classification.
	Idempotent per original payment: a payment can only be refunded once
	in this simple model (no partial-refund tracking) — a second call
	against an already-refunded payment returns the existing refund
	rather than creating a duplicate."""
	original = frappe.get_doc("QTT Payment", payment_name)
	if original.status != "succeeded":
		frappe.throw(_("Can only refund a succeeded payment."))

	existing_refund_name = frappe.db.exists("QTT Payment", {"refund_of": original.name})
	if existing_refund_name:
		return frappe.get_doc("QTT Payment", existing_refund_name)

	refund = frappe.get_doc(
		{
			"doctype": "QTT Payment",
			"invoice": original.invoice,
			"amount": amount,
			"currency": original.currency,
			"status": "refunded",
			"paid_at": now_datetime(),
			"refund_of": original.name,
		}
	)
	refund.insert(ignore_permissions=True)

	tenant = frappe.db.get_value("QTT Invoice", original.invoice, "tenant")
	write_audit_event(
		"payment_refunded",
		tenant=tenant,
		target_doctype="QTT Payment",
		target_name=refund.name,
		metadata={"original_payment": original.name, "amount": amount, "reference": reference},
	)
	return refund


def reconcile_payments() -> list[dict]:
	"""The recoverable-state mechanism from the hardening review section
	24: scans for QTT Payment(status=succeeded) whose invoice is not
	marked paid (the rare case where the payment write succeeded but the
	invoice-status write that should accompany it didn't — normally
	impossible given both happen in one Frappe request transaction, but
	this is the safety net for whatever edge case defeats that). Not
	registered as a scheduled job yet — same open scheduler_events
	convention gap noted in Phase 8's reconcile_wallet()."""
	corrections = []
	succeeded_payments = frappe.get_all(
		"QTT Payment", filters={"status": "succeeded"}, fields=["name", "invoice"]
	)
	for row in succeeded_payments:
		invoice_status = frappe.db.get_value("QTT Invoice", row.invoice, "status")
		if invoice_status not in ("paid",):
			frappe.db.set_value("QTT Invoice", row.invoice, "status", "paid")
			corrections.append({"invoice": row.invoice, "payment": row.name, "corrected_to": "paid"})
	return corrections


def _audit_webhook_rejected(gateway_key: str) -> None:
	write_audit_event("security_violation", metadata={"reason": "invalid_webhook_signature", "gateway": gateway_key})
	frappe.log_error(
		title=f"Rejected webhook: invalid signature ({gateway_key})",
		message="A webhook with an invalid signature was rejected.",
	)


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase C — Razorpay Subscriptions integration. Everything
# above this point (Orders/Invoice/Payment) is unchanged. These functions
# are the ONLY code path that creates/cancels an external Razorpay
# subscription; they never fake success — every one either returns a real
# gateway response or raises. Webhook event PROCESSING / the
# trial->active->past_due->suspended state machine is Phase D, directly
# below this block.
# ---------------------------------------------------------------------------


def _require_subscription_capable_gateway(gateway_key: str) -> SubscriptionCapableGateway:
	gateway = get_gateway(gateway_key)
	if not isinstance(gateway, SubscriptionCapableGateway):
		frappe.throw(_("Payment gateway '{0}' does not support recurring subscriptions.").format(gateway_key))
	return gateway


def ensure_razorpay_plan(plan_name: str, *, gateway_key: str = "razorpay") -> str:
	"""Reuse-first (Part 12 — 'create/reuse Razorpay Plans rather than
	creating a new Razorpay plan on every signup'): returns QTT Plan's
	existing razorpay_plan_id if already set; otherwise creates the
	Razorpay Plan exactly once and stores the id. Safe to call on every
	subscription creation for the same QTT Plan — a second call is a
	no-op DB read, never a second Razorpay API call."""
	plan = frappe.get_doc("QTT Plan", plan_name)
	if plan.razorpay_plan_id:
		return plan.razorpay_plan_id

	gateway = _require_subscription_capable_gateway(gateway_key)
	razorpay_plan_id = gateway.create_plan(
		name=f"{plan.display_name} ({plan.product})",
		amount=plan.base_price,
		currency="INR",
		period=plan.billing_period,
	)
	frappe.db.set_value("QTT Plan", plan.name, "razorpay_plan_id", razorpay_plan_id)
	write_audit_event(
		"razorpay_plan_created",
		product=plan.product,
		target_doctype="QTT Plan",
		target_name=plan.name,
		metadata={"razorpay_plan_id": razorpay_plan_id},
	)
	return razorpay_plan_id


def create_razorpay_subscription(subscription_name: str, *, gateway_key: str = "razorpay") -> dict:
	"""Creates the EXTERNAL Razorpay subscription for an already-created
	LOCAL QTT Product Subscription (qtt_platform.subscription.service.
	create_subscription() — unmodified) and links the two via
	razorpay_subscription_id. If the local subscription is currently
	trialing, its trial_end (Phase C field) becomes Razorpay's start_at —
	the customer authorizes now, the first real charge happens at
	trial_end. Idempotent guard: refuses to double-link an already-linked
	subscription rather than silently creating a second external
	subscription for it."""
	subscription = frappe.get_doc("QTT Product Subscription", subscription_name)
	if subscription.razorpay_subscription_id:
		frappe.throw(_("This subscription is already linked to a Razorpay subscription."))

	razorpay_plan_id = ensure_razorpay_plan(subscription.plan, gateway_key=gateway_key)
	gateway = _require_subscription_capable_gateway(gateway_key)

	start_at = None
	if subscription.status == "trialing" and subscription.trial_end:
		start_at = int(get_datetime(subscription.trial_end).timestamp())

	result = gateway.create_subscription(
		gateway_plan_id=razorpay_plan_id,
		total_count=_UNBOUNDED_TOTAL_COUNT,
		start_at=start_at,
		customer_notify=True,
		notes={"qtt_tenant": subscription.tenant, "qtt_subscription": subscription.name},
	)

	frappe.db.set_value(
		"QTT Product Subscription", subscription.name, "razorpay_subscription_id", result.gateway_subscription_id
	)
	write_audit_event(
		"razorpay_subscription_created",
		tenant=subscription.tenant,
		product=subscription.product,
		target_doctype="QTT Product Subscription",
		target_name=subscription.name,
		metadata={"razorpay_subscription_id": result.gateway_subscription_id, "start_at": start_at},
	)

	return {"razorpay_subscription_id": result.gateway_subscription_id, "checkout": result.client_payload}


def cancel_razorpay_subscription(
	subscription_name: str, *, cancel_at_cycle_end: bool = True, gateway_key: str = "razorpay"
) -> bool:
	"""Cancels the EXTERNAL Razorpay subscription linked to a local QTT
	Product Subscription. Returns False (a safe no-op, not an error) if
	the local subscription was never linked to Razorpay at all — e.g. a
	Phase A-era trial that never converted. Does NOT touch the local
	QTT Product Subscription.status/cancel_at_period_end/cancelled_at
	fields itself — deciding local state transitions from a cancellation
	is Phase D's job (qtt_platform.subscription.service.cancel_subscription
	already owns the local half of this, unmodified)."""
	subscription = frappe.get_doc("QTT Product Subscription", subscription_name)
	if not subscription.razorpay_subscription_id:
		return False

	gateway = _require_subscription_capable_gateway(gateway_key)
	gateway.cancel_subscription(
		gateway_subscription_id=subscription.razorpay_subscription_id, cancel_at_cycle_end=cancel_at_cycle_end
	)
	write_audit_event(
		"razorpay_subscription_cancel_requested",
		tenant=subscription.tenant,
		product=subscription.product,
		target_doctype="QTT Product Subscription",
		target_name=subscription.name,
		metadata={"cancel_at_cycle_end": cancel_at_cycle_end},
	)
	return True


def sync_razorpay_plan_change(subscription_name: str, new_plan_name: str, *, immediate: bool, gateway_key: str = "razorpay") -> dict | None:
	"""SaaS lifecycle Phase E — the ONLY place that PATCHes Razorpay's
	plan on an existing subscription (billing/gateways/razorpay_gateway.py's
	update_subscription_plan(), PATCH /v1/subscriptions/:id). Reuses
	ensure_razorpay_plan() (Phase C, unmodified) so the target plan's
	Razorpay-side id is created/reused exactly once, same as at initial
	subscription creation. `immediate=True` -> schedule_change_at="now"
	(the upgrade policy); `immediate=False` -> "cycle_end" (the downgrade
	policy) — this app's own upgrade/downgrade classification is decided
	by the caller (api/subscription.py), never re-derived here.

	Returns None (a safe no-op, not an error) if the local subscription
	was never linked to Razorpay at all — mirrors
	cancel_razorpay_subscription()'s identical reasoning, and matters for
	plan changes tested/used in a purely local (no Razorpay) environment.
	Never fakes success: raises on any real gateway failure, letting the
	caller decide what "the local state must not diverge from this" means
	for its own case (api/subscription.py's change_plan() is the one
	that enforces Part 14's ordering — call this BEFORE any local write).
	"""
	subscription = frappe.get_doc("QTT Product Subscription", subscription_name)
	if not subscription.razorpay_subscription_id:
		return None

	razorpay_plan_id = ensure_razorpay_plan(new_plan_name, gateway_key=gateway_key)
	gateway = _require_subscription_capable_gateway(gateway_key)

	result = gateway.update_subscription_plan(
		gateway_subscription_id=subscription.razorpay_subscription_id,
		gateway_plan_id=razorpay_plan_id,
		schedule_change_at="now" if immediate else "cycle_end",
	)
	write_audit_event(
		"razorpay_subscription_plan_change_synced",
		tenant=subscription.tenant,
		product=subscription.product,
		target_doctype="QTT Product Subscription",
		target_name=subscription.name,
		metadata={"new_plan": new_plan_name, "immediate": immediate, "razorpay_plan_id": razorpay_plan_id},
	)
	return result


# ---------------------------------------------------------------------------
# SaaS lifecycle Phase D — subscription webhook processing, the
# trial/active/past_due/suspended/cancelled state machine, and
# reconciliation. Everything above this point (Orders, Phase C's
# create/cancel-subscription functions) is unchanged.
# ---------------------------------------------------------------------------

#: Razorpay's subscription EVENT NAMES (webhook `event` field, confirmed
#: against Razorpay's current webhook documentation) -> this app's own
#: QTT Product Subscription.status vocabulary. A deliberate, documented
#: design decision this project made — Razorpay does not publish a
#: canonical "map our events to your states" table:
#:   - subscription.authenticated: customer completed checkout
#:     authorization; not itself a status change (still whatever the
#:     local trial/active state already was) — only triggers the
#:     razorpay_customer_id backfill below.
#:   - subscription.activated / subscription.charged / subscription.resumed:
#:     a real, currently-billing subscription -> "active" — also the
#:     RECOVERY path out of "past_due"/"suspended".
#:   - subscription.pending: Razorpay is mid-retry after a failed charge,
#:     inside ITS OWN grace period -> "past_due".
#:   - subscription.halted: Razorpay's own retry/grace period is
#:     exhausted -> "suspended" (Part 25's "if grace period expires").
#:   - subscription.paused: -> "suspended" — this app's own state
#:     diagram has no separate "paused" state; "suspended" is the
#:     closest existing local value.
#:   - subscription.cancelled / subscription.completed: -> "cancelled".
#:   - subscription.updated: informational only (e.g. quantity/notes
#:     changed on Razorpay's side) — no local status change.
_SUBSCRIPTION_EVENT_TO_LOCAL_STATUS: dict[str, str | None] = {
	"subscription.authenticated": None,
	"subscription.activated": "active",
	"subscription.charged": "active",
	"subscription.resumed": "active",
	"subscription.pending": "past_due",
	"subscription.halted": "suspended",
	"subscription.paused": "suspended",
	"subscription.cancelled": "cancelled",
	"subscription.completed": "cancelled",
	"subscription.updated": None,
}

#: Razorpay's raw subscription `status` values (from GET
#: /v1/subscriptions/:id, confirmed against Razorpay's current API docs)
#: -> this app's local status. Used by reconcile_subscriptions() only —
#: the webhook handler uses the event-name table above, since an event
#: name carries slightly more intent than a bare status snapshot (this
#: app doesn't need the distinction for its own state machine, but keeps
#: the two tables separate rather than conflating "what Razorpay told us
#: happened" with "what Razorpay says is true right now").
_RAZORPAY_STATUS_TO_LOCAL: dict[str, str | None] = {
	"created": None,
	"authenticated": None,
	"active": "active",
	"pending": "past_due",
	"halted": "suspended",
	"cancelled": "cancelled",
	"completed": "cancelled",
	"expired": "cancelled",
}


def _process_subscription_webhook(
	gateway: SubscriptionCapableGateway, gateway_key: str, payload_body: bytes, gateway_event_id: str | None
) -> dict:
	event = gateway.parse_subscription_webhook_event(payload_body)

	if not gateway_event_id:
		# Razorpay's documented idempotency key (Part 17: "use the gateway
		# event ID as an idempotency key where available") is a header,
		# not a payload field — a delivery missing it can't be
		# deduplicated at all. Fail closed rather than silently risking
		# double-processing a redelivered event.
		frappe.throw(_("Missing webhook event id."), frappe.ValidationError)

	if not _record_webhook_event_once(gateway_key, gateway_event_id, event):
		return {"ok": True, "already_processed": True}

	subscription_name = frappe.db.get_value(
		"QTT Product Subscription", {"razorpay_subscription_id": event.gateway_subscription_id}, "name"
	)
	if not subscription_name:
		# A webhook for a subscription id this app has no local record of
		# — flag it, don't crash the whole delivery (Razorpay would just
		# keep retrying a 5xx indefinitely). Not necessarily malicious —
		# could be a stale/foreign test event — but worth an audit trail.
		write_audit_event(
			"security_violation",
			metadata={
				"reason": "webhook_for_unknown_subscription",
				"gateway_subscription_id": event.gateway_subscription_id,
			},
		)
		return {"ok": True, "unrecognized_subscription": True}

	subscription = frappe.get_doc("QTT Product Subscription", subscription_name)

	if event.customer_id:
		_backfill_tenant_razorpay_customer_id(subscription.tenant, event.customer_id)

	new_status = _SUBSCRIPTION_EVENT_TO_LOCAL_STATUS.get(event.event_type)
	if new_status:
		_apply_subscription_status_transition(
			subscription, new_status, source=event.event_type, gateway_status=event.status
		)

	if event.event_type == "subscription.charged":
		_record_subscription_charge(subscription, event.raw_payload)
		# SaaS lifecycle Phase E section 15: "webhook processing must
		# reconcile ... scheduled plan" — a subscription.charged event
		# means a new billing cycle genuinely started on Razorpay's side,
		# which is exactly when a pending scheduled downgrade (Phase E's
		# scheduled_plan/scheduled_plan_effective_date) should actually
		# apply. apply_scheduled_plan_change() itself is a safe no-op if
		# nothing is scheduled or the effective date hasn't arrived yet —
		# called unconditionally rather than pre-checked here so the one
		# "is this due" decision lives in exactly one place.
		subscription_service.apply_scheduled_plan_change(subscription.name)

	return {"ok": True}


def _record_webhook_event_once(gateway_key: str, gateway_event_id: str, event) -> bool:
	"""Returns True the first time this event id is seen (caller should
	process it), False for a redelivery (caller should no-op). Same
	insert-then-catch-UniqueValidationError pattern as
	qtt_platform.subscription.service.activate_pointer() — the
	database's own unique index on gateway_event_id (QTT Webhook Event's
	own DocType JSON) is the actual concurrency guarantee, not this
	function's own logic."""
	try:
		frappe.get_doc(
			{
				"doctype": "QTT Webhook Event",
				"gateway": gateway_key,
				"gateway_event_id": gateway_event_id,
				"event_type": event.event_type,
				"gateway_subscription_id": event.gateway_subscription_id,
				"received_at": now_datetime(),
				"raw_payload": json.dumps(event.raw_payload),
			}
		).insert(ignore_permissions=True)
		return True
	except frappe.UniqueValidationError:
		return False


def _apply_subscription_status_transition(subscription, new_status: str, *, source: str, gateway_status: str) -> None:
	"""`new_status` is already this app's own vocabulary — both callers
	(the webhook handler above, reconcile_subscriptions below) resolve
	their own gateway-specific value to a local status BEFORE calling
	this, so this function has exactly one job: apply it, and audit it,
	only if it's actually a change (no duplicate audit noise for a
	redundant confirmation of the state already recorded)."""
	if new_status == subscription.status:
		return

	previous_status = subscription.status
	subscription.status = new_status
	if new_status == "cancelled":
		subscription.cancelled_at = now_datetime()
		subscription.effective_end_date = today()
	subscription.save(ignore_permissions=True)

	write_audit_event(
		f"subscription_{new_status}",
		tenant=subscription.tenant,
		product=subscription.product,
		target_doctype="QTT Product Subscription",
		target_name=subscription.name,
		metadata={"from": previous_status, "to": new_status, "source": source, "gateway_status": gateway_status},
	)


def _backfill_tenant_razorpay_customer_id(tenant: str, customer_id: str) -> None:
	"""QTT Tenant.razorpay_customer_id (Phase C field) is deliberately
	NOT set at subscription-creation time — see create_razorpay_
	subscription()'s own docstring for why Razorpay's API gives no way to
	do that. This is where it actually gets set: the first webhook that
	reports one, and kept in sync thereafter."""
	current = frappe.db.get_value("QTT Tenant", tenant, "razorpay_customer_id")
	if current != customer_id:
		frappe.db.set_value("QTT Tenant", tenant, "razorpay_customer_id", customer_id)


def _record_subscription_charge(subscription, raw_payload: dict) -> None:
	"""A successful recurring charge (Part 19/20) — reuses the existing
	QTT Invoice/QTT Payment/QTT Payment Transaction architecture exactly
	as the Orders flow does, just entered from the subscription side.
	Idempotent per gateway payment id (QTT Payment Transaction.
	gateway_reference is already unique) — belt-and-suspenders alongside
	_record_webhook_event_once's own event-id dedup above, in case the
	same underlying payment were ever reported under two different
	gateway_event_ids."""
	payment_entity = raw_payload.get("payload", {}).get("payment", {}).get("entity", {})
	gateway_payment_id = payment_entity.get("id")
	if not gateway_payment_id:
		return  # nothing to record without a real payment reference

	if frappe.db.exists("QTT Payment Transaction", {"gateway_reference": gateway_payment_id}):
		return

	amount = (payment_entity.get("amount") or 0) / 100  # paise -> rupees, same convention as the Orders flow
	currency = payment_entity.get("currency", "INR")

	invoice = create_invoice(
		subscription.tenant,
		[
			{
				"subscription": subscription.name,
				"description": f"{subscription.product} subscription renewal",
				"amount": amount,
			}
		],
	)
	frappe.db.set_value("QTT Invoice", invoice.name, "status", "paid")

	frappe.get_doc(
		{
			"doctype": "QTT Payment Transaction",
			"invoice": invoice.name,
			"gateway": "razorpay",
			"gateway_reference": gateway_payment_id,
			"status": "succeeded",
			"raw_payload": json.dumps(raw_payload),
		}
	).insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "QTT Payment",
			"invoice": invoice.name,
			"amount": amount,
			"currency": currency,
			"status": "succeeded",
			"paid_at": now_datetime(),
		}
	).insert(ignore_permissions=True)

	write_audit_event(
		"payment_received",
		tenant=subscription.tenant,
		product=subscription.product,
		target_doctype="QTT Invoice",
		target_name=invoice.name,
		metadata={"subscription": subscription.name, "gateway_payment_id": gateway_payment_id, "amount": amount},
	)


#: Locally "open" statuses reconcile_subscriptions() bothers checking —
#: a cancelled subscription has nothing left to reconcile.
_RECONCILABLE_LOCAL_STATUSES = ("trialing", "active", "past_due", "suspended")


def reconcile_subscriptions(*, gateway_key: str = "razorpay") -> list[dict]:
	"""The recoverable-state mechanism (Part 42): for every locally 'open'
	subscription linked to Razorpay, fetches Razorpay's own current
	status and repairs local state if it has drifted — the safety net
	for a webhook Razorpay never successfully delivered, or one this app
	somehow failed to record. Applies the exact same
	_apply_subscription_status_transition() the webhook handler uses, so
	there is exactly one place the status-mapping logic lives. Not
	registered as a scheduled job yet — that's Phase I, same open
	scheduler_events convention gap already noted for reconcile_payments()
	and Phase 8's reconcile_wallet()."""
	gateway = _require_subscription_capable_gateway(gateway_key)
	corrections = []

	open_subscriptions = frappe.get_all(
		"QTT Product Subscription",
		filters={
			"status": ["in", _RECONCILABLE_LOCAL_STATUSES],
			"razorpay_subscription_id": ["is", "set"],
		},
		fields=["name", "razorpay_subscription_id", "status"],
	)

	for row in open_subscriptions:
		try:
			razorpay_status = gateway.fetch_subscription_status(gateway_subscription_id=row.razorpay_subscription_id)
		except Exception:
			frappe.log_error(
				title=f"reconcile_subscriptions: fetch failed for {row.razorpay_subscription_id}",
				message=frappe.get_traceback(),
			)
			continue

		target_status = _RAZORPAY_STATUS_TO_LOCAL.get(razorpay_status)
		if not target_status or target_status == row.status:
			continue

		subscription = frappe.get_doc("QTT Product Subscription", row.name)
		_apply_subscription_status_transition(
			subscription, target_status, source="reconciliation", gateway_status=razorpay_status
		)
		corrections.append({"subscription": row.name, "from": row.status, "to": target_status})

	return corrections
