"""Writes one QTT AI Usage Record per AI request, success or failure —
called once by qtt_platform.ai.service, never by a provider implementation
itself (keeping providers free of any billing/audit concern, matching the
original Node gateway's own separation between UsageStore and the
provider classes)."""

import frappe

from qtt_platform.ai.core.response import AiUsage


def record_usage(
	*,
	tenant: str,
	product: str,
	user: str,
	feature: str,
	provider: str,
	model: str,
	usage: AiUsage,
	credits_used: float,
	provider_cost: float,
	status: str,
	duration_ms: int,
) -> None:
	frappe.get_doc(
		{
			"doctype": "QTT AI Usage Record",
			"tenant": tenant,
			"product": product,
			"user": user,
			"feature": feature,
			"provider": provider,
			"model": model,
			"input_tokens": usage.input_tokens,
			"output_tokens": usage.output_tokens,
			"total_tokens": usage.total_tokens,
			"credits_used": credits_used,
			"provider_cost": provider_cost,
			"status": status,
			"duration_ms": duration_ms,
		}
	).insert(ignore_permissions=True)
