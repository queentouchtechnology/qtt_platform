"""
Registered stub — matches qzmaster-ai-gateway's own scope decision
("only implement providers actually needed now"). Gemini's wire format
differs from the OpenAI-compatible chat completions shape it shares with
DeepSeek/OpenAI/OpenRouter, so it needs its own HTTP client, not
openai_compatible.py.

To complete: implement generate() calling Gemini's own generateContent
API, following openai_compatible_provider.py's is_configured() pattern
for reading QTT AI Provider's api_key via get_decrypted_password().
"""

from qtt_platform.ai.core.exceptions import ProviderNotConfigured
from qtt_platform.ai.core.provider import AiCapabilities, AiProvider
from qtt_platform.ai.core.request import AiRequest
from qtt_platform.ai.core.response import AiResponse

PROVIDER_KEY = "gemini"


class GeminiProvider(AiProvider):
	name = PROVIDER_KEY
	capabilities = AiCapabilities()

	def is_configured(self) -> bool:
		return False

	def generate(self, request: AiRequest) -> AiResponse:
		raise ProviderNotConfigured(PROVIDER_KEY)
