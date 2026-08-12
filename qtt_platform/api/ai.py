"""
Tenant-facing AI endpoints. Deliberately just a balance check for now —
there is no whitelisted "generate" endpoint here, and there shouldn't be
one yet: an AI feature needs a real prompt and a real feature_key, both of
which are product-specific business logic (a future LMS QuizAiService
calling qtt_platform.ai.service.generate_and_track() directly). Building a
generic "generate" endpoint in the platform now would mean either
exposing raw prompt construction to Flutter (a real security/cost-control
problem — the server must own what prompt actually gets sent) or
inventing a fake feature to expose it against. Neither is real work; see
Phase 10 for where this actually gets a caller.
"""

import frappe

from qtt_platform.ai.services.credit_service import get_balance
from qtt_platform.product.guards import require_product_access


@frappe.whitelist()
def get_ai_credit_balance(tenant: str, product: str) -> dict:
	require_product_access(tenant, product)
	return {"tenant": tenant, "product": product, "balance": get_balance(tenant, product)}
