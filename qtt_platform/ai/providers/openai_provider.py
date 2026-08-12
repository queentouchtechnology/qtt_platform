"""Real implementation — matches qzmaster-ai-gateway's own status: built
specifically to prove the provider-switching story (the same business
service call working identically regardless of which provider is active),
not because two commercial providers were strictly required.

Named openai_provider.py, not openai.py, to avoid any import ambiguity
with the real third-party `openai` Python package."""

from qtt_platform.ai.providers.openai_compatible_provider import OpenAiCompatibleProvider


class OpenAiProvider(OpenAiCompatibleProvider):
	provider_key = "openai"
	default_base_url = "https://api.openai.com/v1"
