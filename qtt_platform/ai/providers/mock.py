"""Ported from qzmaster-ai-gateway's MockAiProvider — deterministic,
network-free, always configured. Used for testing the gateway's own
routing/retry/fallback logic without spending money or needing a real key,
matching the Node gateway's own test suite, which uses this exclusively."""

import frappe

from qtt_platform.ai.core.provider import AiCapabilities, AiProvider
from qtt_platform.ai.core.request import AiRequest
from qtt_platform.ai.core.response import AiResponse, AiUsage

PROVIDER_KEY = "mock"


class MockProvider(AiProvider):
	name = PROVIDER_KEY
	capabilities = AiCapabilities(structured_output=True)

	def is_configured(self) -> bool:
		return True

	def generate(self, request: AiRequest) -> AiResponse:
		content = (
			f'{{"mock": true, "task": "{request.task}"}}'
			if request.structured_output
			else f"Mock response for task '{request.task}'"
		)
		return AiResponse(
			content=content,
			usage=AiUsage(input_tokens=10, output_tokens=10, total_tokens=20),
			provider=PROVIDER_KEY,
			model=request.model or "mock-model",
			request_id=frappe.generate_hash(length=12),
			duration_ms=1,
		)
