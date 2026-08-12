"""
Tenant-facing product endpoints. Deliberately thin — this is not where
access decisions happen (that's require_product_access/require_product_role
in Phase 3), only where a caller finds out what products *exist* on the
platform at all, e.g. for a "subscribe to a new product" browsing screen.
"""

import frappe


@frappe.whitelist()
def list_available_products() -> list[dict]:
	"""Every enabled product's public-safe fields — never the internal
	QTT Product DocType registry (that stays System-Manager-only, per the
	hardening review section 3), and never gated by the caller's own
	Product Access, since browsing the catalog and holding access to
	something in it are different questions."""
	return frappe.get_all(
		"QTT Product",
		filters={"status": "active"},
		fields=["product_key", "display_name", "icon", "description"],
		order_by="display_name asc",
	)
