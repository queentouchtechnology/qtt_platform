"""
The usage engine — hardening review section 2's fix, implemented: usage
resolvers are registered in each product's own hooks.py
(`usage_resolvers = {"PRODUCT_KEY::feature_key": "dotted.python.path"}`),
never a DocType field. A database-editable dotted-import-path field would
let anyone with write access to that field make the platform call an
arbitrary Python function — see qtt_platform/hooks.py's own comment on
this and the QTT Plan Feature doctype's description.

No product registers a resolver yet — LMS integration is Phase 10 — so
this module is real, working infrastructure with nothing plugged into it,
exactly like the Product DocType registry was after Phase 2.
"""

import frappe

from qtt_platform.exceptions import FeatureNotConfigured, UsageResolutionFailed

_REGISTRY_CACHE_KEY = "qtt_usage_resolver_registry"
_REGISTRY_CACHE_TTL = 60 * 60  # static per deploy — see product/registry.py's identical reasoning


def _build_registry() -> dict:
	merged: dict = {}
	raw = frappe.get_hooks("usage_resolvers") or {}
	# NOTE: frappe.get_hooks() aggregates a dict-shaped hook by merging
	# every installed app's own declaration together — but this project
	# has not been able to confirm empirically (no live Frappe instance
	# available this session) whether that comes back as one already-
	# merged dict or a list of per-app dicts to merge here manually.
	# Handled defensively for both shapes rather than assuming one —
	# verify the actual shape on first real deploy (a `bench console`
	# check: `frappe.get_hooks("usage_resolvers")`) and simplify this
	# function once confirmed, rather than leaving the defensive branch
	# in place indefinitely.
	if isinstance(raw, dict):
		merged.update(raw)
	else:
		for app_resolvers in raw:
			if isinstance(app_resolvers, dict):
				merged.update(app_resolvers)
	return merged


def get_usage_resolver(product: str, feature_key: str):
	"""Returns the callable registered for (product, feature_key), or
	raises FeatureNotConfigured. The registry is static per deploy, so
	aggressively cached — this is exactly the kind of metadata the
	hardening review's section 23 performance review flags as safe to
	cache, unlike an access decision (never cached — see
	tenant/context.py)."""
	registry = frappe.cache().get_value(_REGISTRY_CACHE_KEY)
	if registry is None:
		registry = _build_registry()
		frappe.cache().set_value(_REGISTRY_CACHE_KEY, registry, expires_in_sec=_REGISTRY_CACHE_TTL)

	path = registry.get(f"{product}::{feature_key}")
	if not path:
		raise FeatureNotConfigured(f"No usage resolver registered for {product}::{feature_key}")
	return frappe.get_attr(path)


def get_usage(tenant: str, product: str, feature_key: str) -> int:
	"""Calls the registered resolver for (product, feature_key) with
	`tenant` as its only argument. Raises FeatureNotConfigured (no
	resolver registered — this feature isn't a countable one) or
	UsageResolutionFailed (the resolver itself raised) — callers
	(qtt_platform.entitlement.engine) are required to treat both as
	fail-closed, never as "usage is zero."""
	resolver = get_usage_resolver(product, feature_key)  # raises FeatureNotConfigured
	try:
		return resolver(tenant)
	except Exception as exc:
		frappe.log_error(
			title=f"Usage resolver failed: {product}::{feature_key}",
			message=frappe.get_traceback(),
		)
		raise UsageResolutionFailed(str(exc)) from exc
