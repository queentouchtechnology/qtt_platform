"""
AI feature handler registry — production-readiness audit. Mirrors
qtt_platform.usage.registry's exact pattern (a hooks.py-registered
dict of dotted-import-path strings, never a DocType field — same
arbitrary-code-execution reasoning already established there and in the
hardening review section 2) so a product can register its own AI
features without qtt_platform ever learning what they do.

api/ai.py's generate() endpoint is the only caller: it resolves tenant/
product access generically, looks up the registered handler for
"<product>::<feature>", and calls it — the handler owns everything
product-specific (role check, prompt, credit cost, parsing the result).
"""

import frappe

from qtt_platform.exceptions import FeatureNotConfigured

_REGISTRY_CACHE_KEY = "qtt_ai_feature_handler_registry"
_REGISTRY_CACHE_TTL = 60 * 60  # static per deploy — same reasoning as usage/registry.py


def _build_registry() -> dict:
	# CONFIRMED live against a real site (2026-08-14) — see
	# usage/registry.py::_build_registry()'s own comment for the full
	# explanation and empirical evidence. This was the exact reason
	# api.ai.generate() had never worked end-to-end despite the handler
	# itself (qmp_lms_bridge.ai_features.generate_quiz) working fine when
	# called directly — get_ai_feature_handler() was passing a
	# single-element LIST to frappe.get_attr(), not the dotted-path
	# string, on every real call.
	raw = frappe.get_hooks("ai_feature_handlers") or {}
	return {key: (value[-1] if isinstance(value, list) else value) for key, value in raw.items()}


def get_ai_feature_handler(product: str, feature: str):
	"""Returns the callable registered for "<product>::<feature>", or
	raises FeatureNotConfigured — the same exception type
	usage/registry.py raises for an unregistered usage resolver, reused
	deliberately: both mean "this product never configured this feature
	key," the same failure shape either way."""
	registry = frappe.cache().get_value(_REGISTRY_CACHE_KEY)
	if registry is None:
		registry = _build_registry()
		frappe.cache().set_value(_REGISTRY_CACHE_KEY, registry, expires_in_sec=_REGISTRY_CACHE_TTL)

	path = registry.get(f"{product}::{feature}")
	if not path:
		raise FeatureNotConfigured(f"No AI feature handler registered for {product}::{feature}")
	return frappe.get_attr(path)
