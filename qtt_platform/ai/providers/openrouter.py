"""Real implementation — also OpenAI-compatible, matching
qzmaster-ai-gateway's status: inert until a QTT AI Provider row for
'openrouter' is configured with a real key, same as every other provider
here."""

from qtt_platform.ai.providers.openai_compatible_provider import OpenAiCompatibleProvider


class OpenRouterProvider(OpenAiCompatibleProvider):
	provider_key = "openrouter"
	default_base_url = "https://openrouter.ai/api/v1"
