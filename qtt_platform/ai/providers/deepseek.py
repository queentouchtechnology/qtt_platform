"""Real implementation — matches qzmaster-ai-gateway's own "what's
actually implemented" status for DeepSeek (OpenAI-compatible chat
completions)."""

from qtt_platform.ai.providers.openai_compatible_provider import OpenAiCompatibleProvider


class DeepSeekProvider(OpenAiCompatibleProvider):
	provider_key = "deepseek"
	default_base_url = "https://api.deepseek.com/v1"
