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
	"""Upgrade or downgrade: creates a NEW QTT Product Subscription row
	(the old one is never mutated — it becomes historical purely by virtue
	of the pointer no longer referencing it, not by a status change) and
	atomically repoints the tenant's (tenant, product) pointer at it."""
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
			"status": "active",
			"current_period_start": current.current_period_start,
			"current_period_end": current.current_period_end,
		}
	)
	new_subscription.insert(ignore_permissions=True)

	activate_pointer(tenant, product, new_subscription.name)
	_write_subscription_event(new_subscription.name, event_type, from_plan=current.plan, to_plan=new_plan)

	return new_subscription


def cancel_subscription(tenant: str, product: str, *, at_period_end: bool = True):
	"""`at_period_end=True` (the default) marks the subscription to lapse
	at current_period_end without an immediate access change — the
	entitlement engine (Phase 5) is what actually enforces the period
	boundary. `at_period_end=False` cancels immediately."""
	current = get_current_subscription(tenant, product)
	if not current:
		frappe.throw(_("No active subscription to cancel for this product."))

	if at_period_end:
		current.cancel_at_period_end = 1
	else:
		current.status = "cancelled"
		current.cancel_at_period_end = 0
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
