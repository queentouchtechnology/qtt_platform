"""Who may see what in a business, by role — pure (no frappe), tested without a bench.
qtt_platform.abilities applies it to a membership and enforces it."""

GOVERNANCE = ("Tenant Owner", "Tenant Admin")
CUSTOMER_PRODUCTS = ("QTT_ORBITRA", "QTT_ONBOX")


def rules(tenant_role: str | None, products) -> dict:
	"""{ability: allowed} from someone's role in the business and the apps they can use.

	customers  owners, admins, and people who work with customers (Orbitra billing, Onbox chats)
	business   the business profile, team and plans: owners and admins only"""
	governs = tenant_role in GOVERNANCE
	return {
		"customers": governs or bool(set(products or []) & set(CUSTOMER_PRODUCTS)),
		"business": governs,
	}
