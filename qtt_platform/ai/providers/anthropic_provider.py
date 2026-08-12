"""
Registered stub — same reason as gemini.py: Anthropic's Messages API has
a different shape from the OpenAI-compatible chat completions format
(system prompt is a top-level field, usage is input_tokens/output_tokens
at the top level, not nested under a single "usage" key the same way).

Named anthropic_provider.py to avoid import ambiguity with the real
`anthropic` Python package.
"""

from qtt_platform.ai.core.exceptions import ProviderNotConfigured
from qtt_platform.ai.core.provider import AiCapabilities, AiProvider
from qtt_platform.ai.core.request import AiRequest
from qtt_platform.ai.core.response import AiResponse

PROVIDER_KEY = "anthropic"


class AnthropicProvider(AiProvider):
	name = PROVIDER_KEY
	capabilities = AiCapabilities()

	def is_configured(self) -> bool:
		return False

	def generate(self, request: AiRequest) -> AiResponse:
		raise ProviderNotConfigured(PROVIDER_KEY)
