"""Wires every known provider class into a fresh AiProviderRegistry. One
function, called once per gateway construction (qtt_platform.ai.service) —
deliberately not a module-level singleton, since Frappe request workers
shouldn't share mutable state across requests."""

from qtt_platform.ai.core.registry import AiProviderRegistry
from qtt_platform.ai.providers.anthropic_provider import AnthropicProvider
from qtt_platform.ai.providers.deepseek import DeepSeekProvider
from qtt_platform.ai.providers.gemini import GeminiProvider
from qtt_platform.ai.providers.mock import MockProvider
from qtt_platform.ai.providers.openai_provider import OpenAiProvider
from qtt_platform.ai.providers.openrouter import OpenRouterProvider

_PROVIDER_CLASSES = (
	MockProvider,
	DeepSeekProvider,
	OpenAiProvider,
	OpenRouterProvider,
	GeminiProvider,
	AnthropicProvider,
)


def build_registry() -> AiProviderRegistry:
	registry = AiProviderRegistry()
	for provider_cls in _PROVIDER_CLASSES:
		registry.register(provider_cls())
	return registry
