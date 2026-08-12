"""
Subscription lifecycle service — the only code path that creates or
transitions a QTT Product Subscription. Every write here uses
ignore_permissions=True, since no tenant-facing role holds DocPerm on any
of these doctypes (hardening review section 11's billing-immutability
pattern); the whitelisted API in api/subscription.py is what actually
gates who may call these functions and with what tenant-role.
"""

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime, today

from qtt_platform.audit import write_audit_event

#: Subscription statuses under which a subscription is considered "open" —
#: governs access via the entitlement engine (Phase 5) and blocks a second
#: `subscribe()` call for the same (tenant, product) in api/subscription.py.
#: Exported here rather than duplicated, since both call sites need the
#: identical definition of "currently subscribed."
OPEN_SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due")


def create_subscription(tenant: str, product: str, plan: str, *, period_days: int = 30):
	"""Creates a new QTT Product Subscription, atomically activates it as
	the (tenant, product)'s current subscription (see activate_pointer),
	and records a 'created' QTT Subscription Event. Trial length comes
	from the plan's own trial_days if set; otherwise the subscription
	starts 'active' for `period_days`."""
	plan_doc = frappe.get_doc("QTT Plan", plan)
	if plan_doc.product != product:
		frappe.throw(_("Plan {0} does not belong to product {1}.").format(plan, product))

	start = today()
	if plan_doc.trial_days:
		status = "trialing"
		end = add_days(start, plan_doc.trial_days)
	else:
		status = "active"
		end = add_days(start, period_days)

	subscription = frappe.get_doc(
		{
			"doctype": "QTT Product Subscription",
			"tenant": tenant,
			"product": product,
			"plan": plan,
			"status": status,
			"current_period_start": start,
			"current_period_end": end,
			# trial_start/trial_end (SaaS lifecycle Phase C) — fixed once at
			# creation, independent of current_period_start/end which keep
			# moving forward on every renewal (see that field's own
			# description). Left blank for a subscription that started
			# 'active' with no trial at all.
			"trial_start": start if status == "trialing" else None,
			"trial_end": end if status == "trialing" else None,
		}
	)
	subscription.insert(ignore_permissions=True)

	activate_pointer(tenant, product, subscription.name)
	_write_subscription_event(subscription.name, "created", to_plan=plan)

	return subscription


def get_current_subscription(tenant: str, product: str):
	"""Reads the current subscription via the pointer table — never by
	querying QTT Product Subscription directly for 'the active one',
	since multiple historical rows may share status='active' after a
	plan change (see change_plan below). Returns None if the tenant has
	never subscribed to this product."""
	pointer = frappe.db.get_value(
		"QTT Tenant Product Subscription Pointer",
		{"tenant": tenant, "product": product},
		"current_subscription",
	)
	if not pointer:
		return None
	return frappe.get_doc("QTT Product Subscription", pointer)


def change_plan(tenant: str, product: str, new_plan: str):
	"""Applies a plan change RIGHT NOW: creates a NEW QTT Product
	Subscription row (the old one is never mutated — it becomes
	historical purely by virtue of the pointer no longer referencing it,
	not by a status change) and atomically repoints the tenant's
	(tenant, product) pointer at it. Used directly for an immediate
	upgrade (api/subscription.py::change_plan()); also the function
	apply_scheduled_plan_change() below calls once a scheduled
	downgrade's effective date has arrived — "applying a plan change" is
	always this same operation, whether it happens immediately or late.

	SaaS lifecycle Phase E: the new row now CARRIES FORWARD
	razorpay_subscription_id/trial_start/trial_end/status from the row it
	supersedes, rather than leaving razorpay_subscription_id blank and
	hardcoding status='active'. Both were real gaps this phase found: a
	plan change previously orphaned the Razorpay linkage entirely (the
	new "current" row had no razorpay_subscription_id, breaking every
	later cancel/reconcile/plan-change call for that lineage), and
	hardcoding 'active' would have silently ended a trial early the
	moment a customer changed plans while still trialing (Part 11's
	explicit "do not restart the trial" only half-covers this — the
	original code didn't restart it, but WOULD have ended it prematurely
	by converting 'trialing' straight to 'active')."""
	current = get_current_subscription(tenant, product)
	if not current:
		frappe.throw(_("No active subscription to change for this product."))

	new_plan_doc = frappe.get_doc("QTT Plan", new_plan)
	if new_plan_doc.product != product:
		frappe.throw(_("Plan {0} does not belong to product {1}.").format(new_plan, product))

	old_plan_price = frappe.db.get_value("QTT Plan", current.plan, "base_price") or 0
	event_type = "upgraded" if new_plan_doc.base_price > old_plan_price else "downgraded"

	new_subscription = frappe.get_doc(
		{
			"doctype": "QTT Product Subscription",
			"tenant": tenant,
			"product": product,
			"plan": new_plan,
			"status": current.status,
			"current_period_start": current.current_period_start,
			"current_period_end": current.current_period_end,
			"razorpay_subscription_id": current.razorpay_subscription_id,
			"trial_start": current.trial_start,
			"trial_end": current.trial_end,
		}
	)
	new_subscription.insert(ignore_permissions=True)

	activate_pointer(tenant, product, new_subscription.name)
	_write_subscription_event(new_subscription.name, event_type, from_plan=current.plan, to_plan=new_plan)

	return new_subscription


def schedule_plan_change(tenant: str, product: str, new_plan: str, effective_date) -> "frappe.model.document.Document":
	"""SaaS lifecycle Phase E — the downgrade path: records the pending
	change directly on the CURRENT subscription row (scheduled_plan/
	scheduled_plan_effective_date, Phase E fields) rather than creating a
	new row prematurely. No new QTT Product Subscription row exists until
	apply_scheduled_plan_change() actually applies it, at or after
	effective_date. A single row can hold at most one scheduled change by
	construction (scheduled_plan is a single field, not a list) — a
	second schedule_plan_change() call before the first is applied simply
	overwrites it (last-write-wins on a single-row UPDATE, the same
	low-severity race class already accepted by activate_pointer()'s own
	documented reasoning); api/subscription.py's own validation is what
	decides whether that overwrite should even be allowed to happen."""
	current = get_current_subscription(tenant, product)
	if not current:
		frappe.throw(_("No active subscription to change for this product."))

	new_plan_doc = frappe.get_doc("QTT Plan", new_plan)
	if new_plan_doc.product != product:
		frappe.throw(_("Plan {0} does not belong to product {1}.").format(new_plan, product))

	current.scheduled_plan = new_plan
	current.scheduled_plan_effective_date = effective_date
	current.save(ignore_permissions=True)

	# QTT Subscription Event's event_type enum (created/renewed/upgraded/
	# downgraded/cancelled) has no "scheduled" concept — a schedule
	# request doesn't change the plan yet, so recording it there would
	# misrepresent what actually happened to the subscription at this
	# timestamp. QTT Audit Log's free-text event_type is the right fit,
	# and matches the exact event name this phase's own spec asks for.
	write_audit_event(
		"plan_downgrade_scheduled",
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Subscription",
		target_name=current.name,
		metadata={"from_plan": current.plan, "to_plan": new_plan, "effective_date": str(effective_date)},
	)
	return current


def clear_scheduled_plan_change(tenant: str, product: str) -> None:
	"""Clears a pending scheduled downgrade without applying it — used
	when a plan change resolves differently before its effective date
	(e.g. the tenant upgrades instead, or apply_scheduled_plan_change()
	has just consumed it)."""
	current = get_current_subscription(tenant, product)
	if not current or not current.scheduled_plan:
		return
	current.scheduled_plan = None
	current.scheduled_plan_effective_date = None
	current.save(ignore_permissions=True)


def apply_scheduled_plan_change(subscription_name: str) -> "frappe.model.document.Document | None":
	"""Applies a pending scheduled downgrade if its effective date has
	arrived — called from the subscription.charged webhook handler
	(billing/service.py, Phase D extension) once Razorpay confirms a new
	billing cycle has actually started, per SaaS lifecycle Phase E
	section 15 ("webhook processing must reconcile ... scheduled plan").
	Returns the new current subscription if a change was applied, else
	None (nothing scheduled, or not due yet — checked defensively even
	though the webhook-driven caller should only invoke this on/after the
	right cycle boundary)."""
	subscription = frappe.get_doc("QTT Product Subscription", subscription_name)
	if not subscription.scheduled_plan:
		return None
	if subscription.scheduled_plan_effective_date and str(subscription.scheduled_plan_effective_date) > today():
		return None

	scheduled_plan = subscription.scheduled_plan
	old_plan = subscription.plan
	# change_plan() itself already writes the real "downgraded"
	# QTT Subscription Event (existing, valid enum value) — no separate
	# event needed there. This audit entry is the distinct "the scheduled
	# change was actually applied now" record (section 17's own vocabulary).
	new_subscription = change_plan(subscription.tenant, subscription.product, scheduled_plan)
	write_audit_event(
		"plan_downgrade_applied",
		tenant=subscription.tenant,
		product=subscription.product,
		target_doctype="QTT Product Subscription",
		target_name=new_subscription.name,
		metadata={"from_plan": old_plan, "to_plan": scheduled_plan},
	)
	return new_subscription


def resume_subscription(tenant: str, product: str) -> "frappe.model.document.Document":
	"""Reverses a pending cancel_at_period_end request (SaaS lifecycle
	Phase E section 12) — only valid while the subscription hasn't
	actually lapsed yet (status is still open; a genuinely 'cancelled'
	subscription has no local state left to resume and needs a fresh
	subscribe() call instead, which api/subscription.py is responsible
	for rejecting before calling this). Clears exactly the fields
	cancel_subscription() sets, nothing else."""
	current = get_current_subscription(tenant, product)
	if not current:
		frappe.throw(_("No subscription to resume for this product."))
	if current.status == "cancelled":
		frappe.throw(_("This subscription has already been cancelled — subscribe again instead of resuming."))

	current.cancel_at_period_end = 0
	current.cancellation_requested_at = None
	current.cancel_reason = None
	current.effective_end_date = None
	current.save(ignore_permissions=True)

	# Same reasoning as schedule_plan_change() above — "resumed" isn't in
	# QTT Subscription Event's enum and doesn't belong there (the plan
	# itself never changed); QTT Audit Log is the right mechanism.
	write_audit_event(
		"subscription_resumed",
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Subscription",
		target_name=current.name,
	)
	return current


def cancel_subscription(tenant: str, product: str, *, at_period_end: bool = True, reason: str | None = None):
	"""`at_period_end=True` (the default) marks the subscription to lapse
	at current_period_end without an immediate access change — the
	entitlement engine (Phase 5) is what actually enforces the period
	boundary. `at_period_end=False` cancels immediately.

	SaaS lifecycle Phase D: also records cancellation_requested_at/
	cancel_reason/effective_end_date (Phase C fields). For
	at_period_end=True, cancelled_at is intentionally left unset here —
	the request has been made, but cancellation hasn't taken effect yet;
	a scheduled sweep (Phase I) is what flips status to 'cancelled' and
	sets cancelled_at once current_period_end actually passes. For an
	immediate cancellation, both happen together, now."""
	current = get_current_subscription(tenant, product)
	if not current:
		frappe.throw(_("No active subscription to cancel for this product."))

	current.cancellation_requested_at = now_datetime()
	current.cancel_reason = reason

	if at_period_end:
		current.cancel_at_period_end = 1
		current.effective_end_date = current.current_period_end
	else:
		current.status = "cancelled"
		current.cancel_at_period_end = 0
		current.cancelled_at = now_datetime()
		current.effective_end_date = today()
	current.save(ignore_permissions=True)

	_write_subscription_event(current.name, "cancelled", from_plan=current.plan)
	return current


def activate_pointer(tenant: str, product: str, subscription_name: str) -> None:
	"""The atomic operation the hardening review section 9 requires: at
	most one pointer row per (tenant, product), enforced by a real
	database unique constraint (patches/v0_3), not an application-level
	check alone.

	Refinement over the review's own raw-SQL pseudocode: the create path
	goes through frappe.get_doc(...).insert(), which runs the normal
	validate() pipeline. If two concurrent callers both race to create
	the FIRST pointer for a (tenant, product) that doesn't have one yet,
	the database's unique index lets exactly one INSERT succeed; the
	loser's insert() raises frappe.UniqueValidationError, which is caught
	here and treated as 'someone else just won the race' — retried as an
	update rather than propagated as an error. This achieves the identical
	guarantee as raw INSERT ... ON DUPLICATE KEY UPDATE while keeping the
	create path on the ORM's normal validated path.

	For an already-existing pointer, a plain UPDATE is safe: two
	concurrent plan-change calls for the same (tenant, product) racing
	here is a 'last write wins' outcome, not a security or financial
	defect (unlike the AI credit case) — see the hardening review section
	18's note on not over-applying the atomic-update pattern where the
	race is low-severity.
	"""
	existing_name = frappe.db.get_value(
		"QTT Tenant Product Subscription Pointer", {"tenant": tenant, "product": product}, "name"
	)
	if existing_name:
		frappe.db.set_value(
			"QTT Tenant Product Subscription Pointer",
			existing_name,
			"current_subscription",
			subscription_name,
		)
		return

	try:
		frappe.get_doc(
			{
				"doctype": "QTT Tenant Product Subscription Pointer",
				"tenant": tenant,
				"product": product,
				"current_subscription": subscription_name,
			}
		).insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		existing_name = frappe.db.get_value(
			"QTT Tenant Product Subscription Pointer", {"tenant": tenant, "product": product}, "name"
		)
		frappe.db.set_value(
			"QTT Tenant Product Subscription Pointer",
			existing_name,
			"current_subscription",
			subscription_name,
		)


def _write_subscription_event(
	subscription: str, event_type: str, *, from_plan: str | None = None, to_plan: str | None = None
):
	frappe.get_doc(
		{
			"doctype": "QTT Subscription Event",
			"subscription": subscription,
			"event_type": event_type,
			"from_plan": from_plan,
			"to_plan": to_plan,
			"occurred_at": now_datetime(),
		}
	).insert(ignore_permissions=True)
