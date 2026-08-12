"""
Ported from qzmaster-ai-gateway's src/ai/services/ai-cost-service.ts —
what a request actually cost in provider fees, entirely separate from
credit consumption (credit_service.py): a 1-credit "explanation" feature
keeps costing the tenant exactly 1 credit even if the underlying
provider/pricing changes underneath it.

Pricing is sourced from QTT AI Model, not a hardcoded table — the one
place this port is a genuine improvement over the original: a pricing
change is a Desk UI edit, not a code deploy.
"""

import frappe

from qtt_platform.ai.core.response import AiUsage


def cost_for(provider: str, model: str, usage: AiUsage) -> float:
	pricing = frappe.db.get_value(
		"QTT AI Model",
		{"provider": provider, "model_id": model},
		["cost_input_per_1m", "cost_output_per_1m"],
		as_dict=True,
	)
	if not pricing:
		return 0.0
	input_cost = (usage.input_tokens or 0) / 1_000_000 * (pricing.cost_input_per_1m or 0)
	output_cost = (usage.output_tokens or 0) / 1_000_000 * (pricing.cost_output_per_1m or 0)
	return round(input_cost + output_cost, 6)
