"""Shared exception types used across the entitlement/usage engine. Kept in
one small module rather than scattered per-file, since both
qtt_platform.usage.registry and qtt_platform.entitlement.engine need to
raise/catch the same types."""


class FeatureNotConfigured(Exception):
	"""No usage resolver is registered for a (product, feature_key) pair
	being asked about as if it were a countable/numeric feature. Distinct
	from a feature simply being absent from a tenant's entitlements — this
	means the *product* never registered a resolver for it at all, which
	is a deploy-time configuration gap, not a normal runtime condition."""


class UsageResolutionFailed(Exception):
	"""A registered usage resolver raised while computing usage. Callers
	must treat this as fail-closed (deny the gated action) — see the
	hardening review section 2's "what happens if it throws" answer."""
