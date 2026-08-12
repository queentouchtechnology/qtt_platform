"""
The entitlement engine — the single place that knows "does tenant X get
feature Y," called by both server-side enforcement (inside a mutating
whitelisted method, after the tenant/product/role checks already ran) and
the read-only `can_i` endpoint Flutter uses to grey out UI affordances.

No caching here, deliberately: entitlements must reflect a plan
change/cancellation on the very next call, the same "never cache an access
decision" discipline already applied to tenant/product access checks.

These functions do not authenticate or authorize anything themselves — by
the time a whitelisted method calls check_limit()/is_feature_enabled(), it
has already run require_tenant_role/require_product_role. Calling these
functions is not itself a security boundary.
"""

import frappe
from frappe import _

from qtt_platform.exceptions import FeatureNotConfigured, UsageResolutionFailed
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES, get_current_subscription
from qtt_platform.usage.registry import get_usage, get_usage_resolver


def get_entitlements(tenant: str, product: str) -> dict:
	"""Merges the tenant's current plan features, active add-ons, and any
	tenant-specific overrides into one flat map. Returns {} (nothing
	entitled) if there is no open subscription for this (tenant, product)
	— fail closed, not "everything allowed by default."
	"""
	subscription = get_current_subscription(tenant, product)
	if not subscription or subscription.status not in OPEN_SUBSCRIPTION_STATUSES:
		return {}

	plan = frappe.get_doc("QTT Plan", subscription.plan)

	entitlements: dict = {}
	for feature in plan.features:
		entitlements[feature.feature_key] = _coerce(feature.limit_value)

	# Add-ons ADD to a numeric limit they're linked to via feature_key —
	# never touch a non-numeric (flag-shaped) entitlement.
	for item in subscription.items:
		if item.feature_key and isinstance(entitlements.get(item.feature_key), int):
			entitlements[item.feature_key] += item.quantity

	# Overrides REPLACE the plan/add-on-derived value outright, never
	# merge with it — that's the whole point of an override. Uses
	# frappe.get_all deliberately: this is internal platform logic
	# computing a result, not exposing QTT Tenant Feature Override's raw
	# rows to a caller — the same reasoning as every other internal
	# get_all use in this app (see product/registry.py).
	overrides = frappe.get_all(
		"QTT Tenant Feature Override",
		filters={"tenant": tenant, "product": product},
		fields=["feature_key", "override_value", "expires_on"],
	)
	today_str = frappe.utils.today()
	for override in overrides:
		if override.expires_on and str(override.expires_on) < today_str:
			continue  # expired — ignored, never deleted (see the doctype's own description)
		entitlements[override.feature_key] = _coerce(override.override_value)

	return entitlements


def is_feature_enabled(tenant: str, product: str, feature_key: str) -> bool:
	"""For flag-shaped features (no usage resolver registered for them) —
	e.g. 'live_classes_enabled'. Returns False (fail closed) if the
	feature isn't in the tenant's entitlements at all."""
	entitlements = get_entitlements(tenant, product)
	if feature_key not in entitlements:
		return False
	return _truthy(entitlements[feature_key])


def check_limit(tenant: str, product: str, feature_key: str, requested_increment: int = 1) -> bool:
	"""The real enforcement gate for a countable/numeric feature — call
	this again, independently, inside the actual mutating whitelisted
	method; never trust a prior can_i() call as sufficient (hardening
	review section 11's entitlement engine design). Fails closed on every
	error path: missing entitlement, non-numeric limit, no registered
	usage resolver, or the resolver itself raising.
	"""
	entitlements = get_entitlements(tenant, product)
	if feature_key not in entitlements:
		return False

	limit = _as_int(entitlements[feature_key])
	if limit is None:
		frappe.throw(
			_("'{0}' is not a numeric/limited feature — use is_feature_enabled() for a flag.").format(
				feature_key
			)
		)

	try:
		used = get_usage(tenant, product, feature_key)
	except (FeatureNotConfigured, UsageResolutionFailed):
		return False

	return (used + requested_increment) <= limit


def can_i(tenant: str, product: str, feature_key: str) -> dict:
	"""The informational answer to 'can this tenant perform X' — whether a
	feature is numeric or a flag is determined by whether a usage
	resolver is registered for it, never guessed from the value's shape.
	Not authenticated/authorized itself — see api/entitlements.py for the
	whitelisted wrapper that requires Product Access before calling this.
	"""
	entitlements = get_entitlements(tenant, product)
	if feature_key not in entitlements:
		return {"allowed": False, "limit": None, "used": None, "remaining": None}

	raw_value = entitlements[feature_key]

	try:
		get_usage_resolver(product, feature_key)
		has_resolver = True
	except FeatureNotConfigured:
		has_resolver = False

	if not has_resolver:
		return {"allowed": _truthy(raw_value), "limit": None, "used": None, "remaining": None}

	limit = _as_int(raw_value)
	if limit is None:
		return {"allowed": False, "limit": None, "used": None, "remaining": None}

	try:
		used = get_usage(tenant, product, feature_key)
	except UsageResolutionFailed:
		return {"allowed": False, "limit": limit, "used": None, "remaining": None}

	return {"allowed": used < limit, "limit": limit, "used": used, "remaining": max(limit - used, 0)}


def get_entitlements_with_usage(tenant: str, product: str) -> list[dict]:
	"""One row per entitlement — {feature_key, allowed, limit, used,
	remaining} — SaaS lifecycle Phase H: the dashboard's "usage" and
	"entitlements" sections are the same underlying data (a numeric
	feature's limit/used/remaining IS its usage), so this single function
	serves both rather than two near-duplicate ones. Pure composition of
	get_entitlements()/can_i(), both unchanged — no new limit-comparison
	logic, same discipline as get_over_limit_features()."""
	entitlements = get_entitlements(tenant, product)
	return [{"feature_key": feature_key, **can_i(tenant, product, feature_key)} for feature_key in entitlements]


def get_over_limit_features(tenant: str, product: str) -> list[dict]:
	"""Numeric entitlements where CURRENT usage already exceeds the
	CURRENT limit — SaaS lifecycle Phase E, section 10: a downgrade must
	never delete data or auto-suspend records, only detect-and-report
	the condition (new creation is already blocked for free by
	check_limit() the moment the lower limit is in effect — nothing new
	needed for that half). Pure composition of get_entitlements()/
	get_usage(), already reviewed — no new limit-comparison logic. Returns
	[] if nothing is over limit, including when there's no open
	subscription at all (get_entitlements() returns {} in that case, so
	the loop below simply has nothing to iterate)."""
	entitlements = get_entitlements(tenant, product)
	over_limit = []
	for feature_key, raw_value in entitlements.items():
		# Same distinction can_i() already makes, reused here rather than
		# re-derived: numeric-vs-flag is decided by whether a usage
		# resolver is REGISTERED for this feature_key, never by whether
		# the stored value happens to parse as an int — a flag stored as
		# "1" must never be treated as "a limit of 1."
		try:
			get_usage_resolver(product, feature_key)
		except FeatureNotConfigured:
			continue

		limit = _as_int(raw_value)
		if limit is None:
			continue
		try:
			used = get_usage(tenant, product, feature_key)
		except (FeatureNotConfigured, UsageResolutionFailed):
			continue
		if used > limit:
			over_limit.append({"feature_key": feature_key, "used": used, "limit": limit})
	return over_limit


def _coerce(raw):
	"""limit_value/override_value are stored as strings. Numeric strings
	(including '0'/'1') become int; anything else is returned as-is.
	Boolean-flag semantics fall out of this naturally via _truthy() below
	— int(0) is falsy, any other int or non-empty string is truthy — so
	no separate 'is this a flag' declaration is needed on the doctype
	itself; see can_i()'s own comment for how the distinction is actually
	made (presence of a registered usage resolver, not the value's shape).
	"""
	if raw is None:
		return None
	try:
		return int(raw)
	except (TypeError, ValueError):
		return raw


def _as_int(value):
	if isinstance(value, bool):
		return None
	if isinstance(value, int):
		return value
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def _truthy(value) -> bool:
	if isinstance(value, int):
		return value != 0
	return str(value).strip().lower() in ("1", "true", "yes")
