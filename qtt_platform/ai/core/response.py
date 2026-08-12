"""Ported from qzmaster-ai-gateway's src/ai/core/ai-usage.ts and
ai-response.ts — the single response shape every AI business service
consumes. Business code reads content/usage/provider/model/request_id and
never needs to know how the underlying vendor formatted its HTTP
response."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AiUsage:
	input_tokens: int | None = None
	output_tokens: int | None = None
	total_tokens: int | None = None


@dataclass(frozen=True)
class AiResponse:
	content: str
	usage: AiUsage
	provider: str
	model: str
	request_id: str
	duration_ms: int
	#: Raw provider payload, kept only for debugging/audit — business
	#: logic must never branch on this.
	raw_metadata: dict | None = None
