"""
The AI Service layer of the architecture diagrams — the one door a
product's own business service calls (e.g. a future LMS QuizAiService).
Sits one level above AiGateway (core/gateway.py), which knows nothing
about credits, cost, or usage recording; this module knows nothing about
what a "quiz" or a "job description" is. Mirrors the original Node
gateway's own strict separation between AiGateway and the business
services built on it.

Callers are expected to have already run their own tenant/product/role
checks and entitlement check (is this feature even enabled) — this
function's job starts at credit reservation, matching the AI request
flow's stage ordering from the architecture documents (auth -> tenant ->
membership -> role -> feature entitlement all happen before this is ever
called).
"""

import time
import uuid

import frappe

from qtt_platform.ai.bootstrap import build_registry
from qtt_platform.ai.core.exceptions import AiProviderException
from qtt_platform.ai.core.gateway import AiGateway
from qtt_platform.ai.core.request import AiRequest
from qtt_platform.ai.core.response import AiResponse, AiUsage
from qtt_platform.ai.services import credit_service, usage_service
from qtt_platform.ai.services.cost_service import cost_for


def generate_and_track(
	*, tenant: str, product: str, user: str, feature: str, request: AiRequest, credit_cost: float
) -> AiResponse:
	"""Reserves `credit_cost` credits BEFORE calling the provider (not
	charge-on-success-only) — a crash or failure after reservation is
	merely a needless refund; charging only on success risks the worse
	failure mode of a provider succeeding and the process crashing before
	that's recorded, which either double-charges on client retry or
	silently under-charges forever. See the hardening review section 8.

	Raises frappe.ValidationError (insufficient credits, credits never
	touched) or re-raises AiProviderException (credits refunded first).
	"""
	reference = str(uuid.uuid4())

	reservation = credit_service.deduct_credits(tenant, product, credit_cost, reference=reference)
	if not reservation.get("ok"):
		frappe.throw("Insufficient AI credits.", frappe.ValidationError)

	gateway = AiGateway(build_registry())
	start = time.monotonic()

	try:
		response = gateway.generate(request)
	except AiProviderException:
		credit_service.refund_credits(tenant, product, credit_cost, reference=reference)
		usage_service.record_usage(
			tenant=tenant,
			product=product,
			user=user,
			feature=feature,
			provider=request.provider or "unknown",
			model=request.model or "unknown",
			usage=AiUsage(),
			credits_used=0,
			provider_cost=0,
			status="error",
			duration_ms=int((time.monotonic() - start) * 1000),
		)
		raise

	provider_cost = cost_for(response.provider, response.model, response.usage)
	usage_service.record_usage(
		tenant=tenant,
		product=product,
		user=user,
		feature=feature,
		provider=response.provider,
		model=response.model,
		usage=response.usage,
		credits_used=credit_cost,
		provider_cost=provider_cost,
		status="success",
		duration_ms=response.duration_ms,
	)
	return response
