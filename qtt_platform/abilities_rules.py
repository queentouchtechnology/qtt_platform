"""Who may see what in a business, by role — pure (no frappe), tested without a bench.
qtt_platform.abilities applies it to a membership and enforces it."""

GOVERNANCE = ("Tenant Owner", "Tenant Admin")
CUSTOMER_PRODUCTS = ("QTT_ORBITRA", "QTT_ONBOX")


def rules(tenant_role: str | None, products, orbitra_customers: bool = False) -> dict:
	"""{ability: allowed} from someone's role in the business and the apps they can use.

	customers             owners, admins, and people who work with customers (Orbitra billing, Onbox chats)
	business              the business profile, team and plans: owners and admins only
	customers_in_orbitra  their customer list lives in Orbitra › Customers (their Orbitra role can use
	                      Customers) — the app then shows it only there, not also as its own menu item"""
	governs = tenant_role in GOVERNANCE
	products = set(products or [])
	return {
		"customers": governs or bool(products & set(CUSTOMER_PRODUCTS)),
		"business": governs,
		"customers_in_orbitra": "QTT_ORBITRA" in products and bool(orbitra_customers),
	}
