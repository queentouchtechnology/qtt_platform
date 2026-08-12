"""
Ported from qzmaster-ai-gateway's src/ai/core/ai-request.ts — the
vendor-neutral request shape every AI business service builds, regardless
of which provider ends up handling it. Do not add provider-specific
fields here — if a capability can't be expressed generically, it belongs
in `metadata` (advisory) or the provider implementation reads it from its
own QTT AI Provider/Model config, not from the request.
"""

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AiMessage:
	role: str  # "system" | "user" | "assistant"
	content: str


@dataclass(frozen=True)
class AiRequest:
	#: Logical task name, e.g. "quiz_generation" — used for task-based
	#: model routing (routing.py) and usage/credit accounting.
	task: str
	messages: list[AiMessage]
	#: Explicit provider/model override. Omit to route by task (routing.py).
	provider: str | None = None
	model: str | None = None
	temperature: float | None = None
	max_output_tokens: int | None = None
	#: Ask the provider to return valid JSON matching the caller's schema
	#: (the schema itself lives in the prompt, built by the calling
	#: product's own business service — not this layer). The provider
	#: implementation decides *how* (JSON mode, tool calling, prompt-only).
	structured_output: bool = False
	metadata: dict | None = None

	def with_model(self, model: str) -> "AiRequest":
		return dataclasses.replace(self, model=model)

	def with_provider_and_model(self, provider: str, model: str) -> "AiRequest":
		return dataclasses.replace(self, provider=provider, model=model)
