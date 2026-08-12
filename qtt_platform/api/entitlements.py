"""
The one whitelisted question Flutter asks: "can this tenant perform X."
Purely informational — grays out UI affordances. The real enforcement is
qtt_platform.entitlement.engine.check_limit(), called again independently
inside the actual mutating whitelisted method; skipping this endpoint
changes nothing about whether an action ultimately succeeds.
"""

import frappe

from qtt_platform.entitlement.engine import can_i as _can_i
from qtt_platform.product.guards import require_product_access


@frappe.whitelist()
def can_i(tenant: str, product: str, feature_key: str) -> dict:
	require_product_access(tenant, product)
	return _can_i(tenant, product, feature_key)
