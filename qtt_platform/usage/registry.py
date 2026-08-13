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
	# CONFIRMED live against a real site (2026-08-14) — frappe.get_hooks()
	# always returns a dict for a dict-shaped hook, but wraps EACH KEY'S
	# value in a list of every declaring app's own contribution for that
	# exact key (verified: frappe.get_hooks("usage_resolvers") returned
	# {"QMP_LMS::max_students": ["qmp_lms_bridge.usage.count_students"]},
	# not a bare string) — even though only qmp_lms_bridge ever declares
	# a real value here (qtt_platform's own usage_resolvers = {} never
	# contributes a competing entry for the same key). This replaces the
	# previous defensive "which shape is it" branching now that the real
	# shape is known — see this module's git history for the old code.
	# Exactly one app is ever expected to declare a given key in
	# practice; the last contribution wins, matching normal hook-override
	# precedence for every other kind of Frappe hook.
	raw = frappe.get_hooks("usage_resolvers") or {}
	return {key: (value[-1] if isinstance(value, list) else value) for key, value in raw.items()}


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
