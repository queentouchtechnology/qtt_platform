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
	merged: dict = {}
	raw = frappe.get_hooks("ai_feature_handlers") or {}
	# Same open question about frappe.get_hooks()'s exact merge shape for
	# a custom dict-valued hook already flagged in usage/registry.py and
	# document_security.py — handled defensively here for the same reason.
	if isinstance(raw, dict):
		merged.update(raw)
	else:
		for app_value in raw:
			if isinstance(app_value, dict):
				merged.update(app_value)
	return merged


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
