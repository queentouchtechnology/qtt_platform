"""
Tenant-facing subscription management. Per the hardening review's
authorization matrix (section 5), changing a subscription is a financial
governance action — Tenant Owner only by default, not Tenant Admin, absent
an explicit tenant-level configuration to widen that (not built in Phase 4;
the default is deliberately the narrower, safer one). SaaS lifecycle Phase
E's own explicit instruction widens exactly ONE action (change_plan) to
Tenant Owner OR Tenant Admin — see _PLAN_CHANGE_ROLES below; every other
action in this file (subscribe/cancel/resume) stays Owner-only, unchanged.

Tenant resolution: subscribe/cancel/get_my_subscription (pre-Phase-E,
unchanged) all take `tenant` as an explicit parameter — safe because
require_tenant_role/require_tenant_membership re-validate real membership
for whatever tenant was passed, never trusting the value itself. Phase E's
own two new/changed endpoints (change_plan, resume) instead resolve
tenant from the caller's active tenant session
(qtt_platform.tenant.context.resolve_active_tenant), per that phase's
explicit instruction not to accept tenant as a request parameter at all.
Both patterns are safe; they are simply different, and this file now
contains both — flagged here rather than silently glossed over.
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.billing import service as billing_service
from qtt_platform.errors import QttApiError, fail, ok
from qtt_platform.exceptions import FeatureNotConfigured, UsageResolutionFailed
from qtt_platform.product.guards import require_product_access
from qtt_platform.subscription import service
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role
from qtt_platform.usage.registry import get_usage, get_usage_resolver

_SUBSCRIPTION_MANAGER_ROLES = ["Tenant Owner"]

#: SaaS lifecycle Phase E section 4's explicit widening for change_plan
#: only — a tenant billing action, gated by TENANT role, never by QMP_LMS
#: product role (Manager/Instructor/Staff/Student must never substitute
#: for this, per that section's own explicit instruction).
_PLAN_CHANGE_ROLES = ["Tenant Owner", "Tenant Admin"]


def _as_bool(value, default: bool) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() not in ("0", "false", "no", "")


@frappe.whitelist()
def subscribe(tenant: str, product: str, plan_code: str) -> dict:
	require_tenant_role(tenant, _SUBSCRIPTION_MANAGER_ROLES)

	plan_name = frappe.db.get_value("QTT Plan", {"product": product, "plan_code": plan_code}, "name")
	if not plan_name:
		frappe.throw(_("No plan '{0}' found for this product.").format(plan_code))

	existing = service.get_current_subscription(tenant, product)
	if existing and existing.status in OPEN_SUBSCRIPTION_STATUSES:
		frappe.throw(
			_("This tenant already has a subscription for this product — use change_plan instead."),
			frappe.ValidationError,
		)

	subscription = service.create_subscription(tenant, product, plan_name)
	return {"subscription": subscription.name, "plan": plan_name, "status": subscription.status}


@frappe.whitelist()
def get_my_subscription(tenant: str, product: str) -> dict | None:
	"""Read-only — any active tenant member may see the tenant's own
	subscription state, not only Tenant Owner/Admin. SaaS lifecycle
	Phase E extends the response (trial dates, pending plan change,
	cancellation state) rather than adding a second endpoint, per that
	phase's own instruction to extend an existing API where one already
	returns subscription information."""
	require_tenant_membership(tenant)

	current = service.get_current_subscription(tenant, product)
	if not current:
		return None

	scheduled_plan_code = None
	if current.scheduled_plan:
		scheduled_plan_code = frappe.db.get_value("QTT Plan", current.scheduled_plan, "plan_code")
	current_plan_code = frappe.db.get_value("QTT Plan", current.plan, "plan_code")

	return {
		"subscription": current.name,
		"plan": current.plan,
		"plan_code": current_plan_code,
		"status": current.status,
		"current_period_start": str(current.current_period_start),
		"current_period_end": str(current.current_period_end),
		"cancel_at_period_end": bool(current.cancel_at_period_end),
		"trial_start": str(current.trial_start) if current.trial_start else None,
		"trial_end": str(current.trial_end) if current.trial_end else None,
		"scheduled_plan": current.scheduled_plan,
		"scheduled_plan_code": scheduled_plan_code,
		"scheduled_plan_effective_date": (
			str(current.scheduled_plan_effective_date) if current.scheduled_plan_effective_date else None
		),
		"cancellation_requested_at": (
			str(current.cancellation_requested_at) if current.cancellation_requested_at else None
		),
		"cancel_reason": current.cancel_reason,
		"effective_end_date": str(current.effective_end_date) if current.effective_end_date else None,
		# The gateway's own subscription id, not a secret (key_secret/
		# webhook_secret never leave QTT Payment Gateway Config — see
		# that doctype's Password fields) — useful for support/debugging,
		# safe to expose to the tenant that owns it.
		"razorpay_subscription_id": current.razorpay_subscription_id,
	}


@frappe.whitelist()
def change_plan(product: str, new_plan: str) -> dict:
	"""SaaS lifecycle Phase E — upgrade (immediate) or downgrade
	(scheduled for the next billing cycle). `new_plan` is a plan_code
	(e.g. "PROFESSIONAL"), matching this phase's own wire shape — never
	a QTT Plan document name/hash. See the module docstring for why
	tenant is resolved from the session here rather than a parameter.
	"""
	try:
		tenant = resolve_active_tenant()
		if not tenant:
			raise QttApiError("TENANT_ACCESS_DENIED", "No active tenant.")

		try:
			require_tenant_role(tenant, _PLAN_CHANGE_ROLES)
		except frappe.PermissionError as exc:
			# Deliberately a distinct code from TENANT_ACCESS_DENIED — this
			# is "you're a real member but not a billing authority," not
			# "you have no relationship to this tenant at all." Section 4:
			# product role (Manager/Instructor/Staff/Student) must never
			# substitute for this check — require_tenant_role only ever
			# looks at QTT Tenant Membership.tenant_role, never
			# QTT Product Access.product_role, so that substitution is
			# structurally impossible here, not just policy.
			raise QttApiError("BILLING_ROLE_REQUIRED", str(exc)) from exc

		try:
			require_product_access(tenant, product)
		except frappe.PermissionError as exc:
			raise QttApiError("PRODUCT_ACCESS_DENIED", str(exc)) from exc

		product_status = frappe.db.get_value("QTT Product", product, "status")
		if product_status != "active":
			raise QttApiError("INVALID_PRODUCT", f"'{product}' is not an available product.")

		new_plan_doc = _resolve_plan_by_code(product, new_plan)

		current = service.get_current_subscription(tenant, product)
		if not current:
			raise QttApiError("SUBSCRIPTION_NOT_FOUND", "No subscription exists for this product.")
		if current.status == "cancelled":
			raise QttApiError("SUBSCRIPTION_CANCELLED", "This subscription has already been cancelled.")
		if current.cancel_at_period_end or current.cancellation_requested_at:
			raise QttApiError(
				"CANCELLATION_PENDING",
				"A cancellation is pending for this subscription. Call "
				"qtt_platform.api.subscription.resume to reactivate it before changing plans.",
			)
		if current.plan == new_plan_doc.name:
			raise QttApiError("PLAN_UNCHANGED", "The subscription is already on this plan.")
		if current.scheduled_plan and current.scheduled_plan != new_plan_doc.name:
			raise QttApiError(
				"PLAN_CHANGE_ALREADY_PENDING",
				f"A plan change to '{frappe.db.get_value('QTT Plan', current.scheduled_plan, 'plan_code')}' "
				"is already scheduled for this subscription.",
			)

		old_plan_doc = frappe.get_doc("QTT Plan", current.plan)
		# Plan comparison, per SaaS lifecycle Phase E section 6: no plan
		# NAME comparison anywhere (no `if new_plan == "ENTERPRISE"`).
		# QTT Plan has no explicit ordering field, and none was added —
		# base_price ascending is ALREADY the architecture's own treatment
		# of plan ordering (see qmp_lms_bridge/plans.py's own documented
		# decision from Phase B: "no plan_order field... the 1/2/3
		# ordering already falls out of base_price ascending"). Reused
		# here, not re-decided.
		is_upgrade = new_plan_doc.base_price > old_plan_doc.base_price

		write_audit_event(
			"plan_change_requested",
			tenant=tenant,
			product=product,
			target_doctype="QTT Product Subscription",
			target_name=current.name,
			metadata={
				"old_plan": old_plan_doc.plan_code,
				"new_plan": new_plan_doc.plan_code,
				"requested_by": frappe.session.user,
			},
		)

		if is_upgrade:
			return _apply_upgrade(tenant, product, current, new_plan_doc, old_plan_doc.plan_code)
		return _schedule_downgrade(tenant, product, current, new_plan_doc, old_plan_doc.plan_code)

	except QttApiError as exc:
		return fail(exc.code, str(exc))
	except frappe.PermissionError as exc:
		return fail("TENANT_ACCESS_DENIED", str(exc))
	except frappe.ValidationError as exc:
		return fail("VALIDATION_ERROR", str(exc))
	except Exception:
		frappe.log_error(title="qtt_platform.api.subscription.change_plan failed", message=frappe.get_traceback())
		return fail("INTERNAL_ERROR", "The plan change could not be completed. Please try again.")


@frappe.whitelist()
def resume(product: str) -> dict:
	"""SaaS lifecycle Phase E section 12 — the explicit "resume before
	changing plan" path change_plan()'s CANCELLATION_PENDING error
	points at. Owner-only, matching cancel()'s own authorization (the
	inverse of an Owner-gated action stays Owner-gated, not widened to
	Admin the way change_plan() was).

	Known limitation, stated plainly: this only clears LOCAL cancellation
	state (subscription/service.py::resume_subscription()). It does not
	make any Razorpay API call — no confirmed Razorpay "un-cancel a
	scheduled cancellation" endpoint was found this session, and this
	project does not implement unconfirmed APIs. If the subscription was
	ever cancelled via cancel_razorpay_subscription() (Phase D) with
	cancel_at_cycle_end=True, Razorpay's own side may still believe a
	cancellation is scheduled; reconcile_subscriptions() (Phase D) is the
	stated safety net for this specific local/external divergence.
	"""
	try:
		tenant = resolve_active_tenant()
		if not tenant:
			raise QttApiError("TENANT_ACCESS_DENIED", "No active tenant.")

		try:
			require_tenant_role(tenant, _SUBSCRIPTION_MANAGER_ROLES)
		except frappe.PermissionError as exc:
			raise QttApiError("BILLING_ROLE_REQUIRED", str(exc)) from exc

		current = service.resume_subscription(tenant, product)
		return ok({"subscription": current.name, "status": current.status, "cancel_at_period_end": False})

	except QttApiError as exc:
		return fail(exc.code, str(exc))
	except frappe.PermissionError as exc:
		return fail("TENANT_ACCESS_DENIED", str(exc))
	except frappe.ValidationError as exc:
		return fail("VALIDATION_ERROR", str(exc))
	except Exception:
		frappe.log_error(title="qtt_platform.api.subscription.resume failed", message=frappe.get_traceback())
		return fail("INTERNAL_ERROR", "Could not resume this subscription. Please try again.")


@frappe.whitelist()
def cancel(tenant: str, product: str, at_period_end=True, reason: str | None = None) -> dict:
	require_tenant_role(tenant, _SUBSCRIPTION_MANAGER_ROLES)

	at_period_end = _as_bool(at_period_end, True)
	current = service.cancel_subscription(tenant, product, at_period_end=at_period_end, reason=reason)

	# SaaS lifecycle Phase D: also cancel the EXTERNAL Razorpay
	# subscription if this one was ever linked to Razorpay (Phase C) — a
	# safe no-op via cancel_razorpay_subscription()'s own guard if it
	# wasn't (e.g. a Phase A-era trial that never converted). Local
	# cancellation above already succeeded and is not rolled back if this
	# external call fails; the failure is logged, not swallowed silently,
	# and reconcile_subscriptions() (Phase I) is the safety net for a
	# local/external mismatch this leaves behind.
	try:
		billing_service.cancel_razorpay_subscription(current.name, cancel_at_cycle_end=at_period_end)
	except Exception:
		frappe.log_error(
			title=f"cancel(): Razorpay-side cancellation failed for {current.name}",
			message=frappe.get_traceback(),
		)

	return {
		"subscription": current.name,
		"status": current.status,
		"cancel_at_period_end": bool(current.cancel_at_period_end),
		"effective_end_date": str(current.effective_end_date) if current.effective_end_date else None,
	}


def _resolve_plan_by_code(product: str, plan_code: str):
	plan_name = frappe.db.get_value("QTT Plan", {"product": product, "plan_code": plan_code}, "name")
	if not plan_name:
		raise QttApiError("INVALID_PLAN", f"'{plan_code}' is not a plan for product '{product}'.")
	plan_doc = frappe.get_doc("QTT Plan", plan_name)
	if not plan_doc.is_public:
		raise QttApiError("INVALID_PLAN", f"'{plan_code}' is not currently available.")
	return plan_doc


def _apply_upgrade(tenant: str, product: str, current, new_plan_doc, old_plan_code: str) -> dict:
	"""Upgrade = immediate (SaaS lifecycle Phase E section 2's default
	policy). Razorpay is synced BEFORE any local write — section 14's
	explicit ordering: "if Razorpay change fails: DO NOT mark QTT
	subscription as upgraded." """
	try:
		billing_service.sync_razorpay_plan_change(current.name, new_plan_doc.name, immediate=True)
	except Exception as exc:
		write_audit_event(
			"plan_change_failed",
			tenant=tenant,
			product=product,
			target_doctype="QTT Product Subscription",
			target_name=current.name,
			metadata={"old_plan": old_plan_code, "new_plan": new_plan_doc.plan_code, "change_type": "upgrade"},
		)
		frappe.log_error(
			title=f"change_plan(): Razorpay upgrade sync failed for {current.name}", message=frappe.get_traceback()
		)
		raise QttApiError(
			"PLAN_CHANGE_FAILED", "Could not update billing for this upgrade. Please try again."
		) from exc

	new_subscription = service.change_plan(tenant, product, new_plan_doc.name)

	write_audit_event(
		"plan_upgrade",
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Subscription",
		target_name=new_subscription.name,
		metadata={
			"old_plan": old_plan_code,
			"new_plan": new_plan_doc.plan_code,
			"requested_by": frappe.session.user,
		},
	)

	return ok(
		{
			"subscription": new_subscription.name,
			"old_plan": old_plan_code,
			"new_plan": new_plan_doc.plan_code,
			"change_type": "upgrade",
			"effective": "immediate",
		}
	)


def _schedule_downgrade(tenant: str, product: str, current, new_plan_doc, old_plan_code: str) -> dict:
	"""Downgrade = scheduled for current_period_end (SaaS lifecycle
	Phase E section 2/8's default policy) — old-plan entitlements remain
	in effect until then (qtt_platform.entitlement.engine reads
	`plan`, unchanged by scheduling; only apply_scheduled_plan_change()
	later flips it). Razorpay is synced (schedule_change_at="cycle_end")
	BEFORE the local scheduled_plan fields are set — section 14: "if
	external scheduling fails: do not record it as successfully
	scheduled." """
	try:
		billing_service.sync_razorpay_plan_change(current.name, new_plan_doc.name, immediate=False)
	except Exception as exc:
		write_audit_event(
			"plan_change_failed",
			tenant=tenant,
			product=product,
			target_doctype="QTT Product Subscription",
			target_name=current.name,
			metadata={"old_plan": old_plan_code, "new_plan": new_plan_doc.plan_code, "change_type": "downgrade"},
		)
		frappe.log_error(
			title=f"change_plan(): Razorpay downgrade scheduling failed for {current.name}",
			message=frappe.get_traceback(),
		)
		raise QttApiError(
			"PLAN_CHANGE_FAILED", "Could not schedule this downgrade with the billing provider. Please try again."
		) from exc

	effective_date = current.current_period_end
	service.schedule_plan_change(tenant, product, new_plan_doc.name, effective_date)

	# Section 10 — detect-and-inform only, never destructive. Checked
	# against the TARGET plan's own limits (not the tenant's current
	# entitlements, which still reflect the OLD plan right now) so the
	# customer sees an accurate preview of what happens at effective_date.
	over_limit = _preview_over_limit_features(tenant, product, new_plan_doc)
	if over_limit:
		write_audit_event(
			"plan_change_usage_exceeded",
			tenant=tenant,
			product=product,
			target_doctype="QTT Product Subscription",
			target_name=current.name,
			metadata={"new_plan": new_plan_doc.plan_code, "over_limit": over_limit},
		)

	return ok(
		{
			"subscription": current.name,
			"old_plan": old_plan_code,
			"new_plan": new_plan_doc.plan_code,
			"change_type": "downgrade",
			"effective": "next_billing_cycle",
			"effective_date": str(effective_date),
			"usage_warning": over_limit or None,
		}
	)


def _preview_over_limit_features(tenant: str, product: str, plan_doc) -> list[dict]:
	"""Usage vs the TARGET plan's own limits, computed at REQUEST time
	for the customer-facing warning above — deliberately distinct from
	qtt_platform.entitlement.engine.get_over_limit_features(), which
	checks usage against the tenant's CURRENT entitlements and is what
	effectively governs access once apply_scheduled_plan_change()
	(subscription/service.py) actually applies the downgrade. Kept small
	and separate here rather than generalizing the engine function to
	take an arbitrary plan override for what is currently only two call
	sites with two different meanings of "the relevant plan.\""""
	over_limit = []
	for feature in plan_doc.features:
		# Same numeric-vs-flag distinction the entitlement engine itself
		# makes (get_over_limit_features()) — a registered usage resolver
		# is what makes a feature_key countable, never whether its stored
		# value happens to parse as an int (a flag stored as "1" must
		# never be treated as "a limit of 1").
		try:
			get_usage_resolver(product, feature.feature_key)
		except FeatureNotConfigured:
			continue

		try:
			limit = int(feature.limit_value)
		except (TypeError, ValueError):
			continue
		try:
			used = get_usage(tenant, product, feature.feature_key)
		except (FeatureNotConfigured, UsageResolutionFailed):
			continue
		if used > limit:
			over_limit.append({"feature_key": feature.feature_key, "used": used, "limit": limit})
	return over_limit
