"""Ported from qzmaster-ai-gateway's src/ai/core/ai-provider.ts and
ai-capabilities.ts — the one interface every vendor integration
implements. The gateway, business services, and API routes depend only on
this — never on a concrete DeepSeekProvider/OpenAiProvider/etc. class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from qtt_platform.ai.core.request import AiRequest
from qtt_platform.ai.core.response import AiResponse


@dataclass(frozen=True)
class AiCapabilities:
	structured_output: bool = False
	max_context_tokens: int | None = None


class AiProvider(ABC):
	name: str
	capabilities: AiCapabilities

	@abstractmethod
	def is_configured(self) -> bool:
		"""True once credentials are present and the provider is enabled.
		The gateway checks this before routing so a missing key surfaces
		as ProviderNotConfigured, never a crash mid-request."""
		...

	@abstractmethod
	def generate(self, request: AiRequest) -> AiResponse: ...
