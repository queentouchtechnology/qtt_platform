"""
A reasonable reconstruction of qzmaster-ai-gateway's AiProviderException
shape, inferred from how ai-gateway.ts actually uses it (error.is_transient
gates same-provider retry, error.is_fallback_eligible gates cross-provider
fallback) — not a byte-exact port, since this session read ai-gateway.ts
and ai-provider.ts but not ai-exceptions.ts itself. Verify against the
real file when porting further providers, rather than assuming this
matches it exactly in every field name.
"""


class AiProviderException(Exception):
	def __init__(
		self,
		kind: str,
		provider: str,
		message: str,
		cause: Exception | None = None,
		*,
		is_transient: bool = False,
		is_fallback_eligible: bool = True,
	):
		super().__init__(message)
		self.kind = kind
		self.provider = provider
		self.cause = cause
		self.is_transient = is_transient
		self.is_fallback_eligible = is_fallback_eligible


class ProviderNotConfigured(AiProviderException):
	"""Raised when a provider's is_configured() is False — a missing API
	key or a disabled QTT AI Provider row. Fallback-eligible (a different
	provider might be configured) but not transient (retrying the same
	unconfigured provider will never succeed)."""

	def __init__(self, provider: str):
		super().__init__(
			"ProviderNotConfigured",
			provider,
			f"{provider} is not configured",
			is_transient=False,
			is_fallback_eligible=True,
		)
