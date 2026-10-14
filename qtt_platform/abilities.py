"""
What a person may see in a business, by their role — one rule for the whole platform, used by the
APIs (which enforce it) and sent to the app with the session (which only shows what's allowed).

  customers  the shared customer list (and customers in search): owners and admins, and people
             who work with customers — anyone with Orbitra (billing) or Onbox (chats) access.
  business   the business profile, team and plans: owners and admins only.

A new screen or API that shows business-wide data should ask here instead of checking roles itself.
"""

import frappe
from frappe import _

from qtt_platform.abilities_rules import CUSTOMER_PRODUCTS, GOVERNANCE, rules  # noqa: F401 (re-exported)


def for_member(membership) -> dict:
	"""The abilities of a QTT Tenant Membership (document or dict with name / tenant_role)."""
	get = membership.get if hasattr(membership, "get") else (lambda k: getattr(membership, k, None))
	access = frappe.get_all("QTT Product Access", filters={"membership": get("name"), "status": "active"}, fields=["product", "product_role", "tenant"])
	products = [a.product for a in access]
	orbitra = next((a for a in access if a.product == "QTT_ORBITRA"), None)
	return rules(get("tenant_role"), products, orbitra_customers=bool(orbitra) and _orbitra_customers(orbitra))


def _orbitra_customers(access) -> bool:
	"""Can this Orbitra role use Customers (the owner can switch it off for a role)?"""
	try:
		from qtt_platform import role_access

		return "customers" in role_access.areas(access.tenant, "QTT_ORBITRA", access.product_role)
	except Exception:
		return False  # unsure: keep the shared list where it is


def require(membership, ability: str) -> None:
	if not for_member(membership).get(ability):
		message = {
			"customers": _("Customers are for the people who sell or chat with customers. Ask your business owner."),
			"business": _("Only the business owner or an admin can see this."),
		}.get(ability, _("You don't have access to this."))
		frappe.throw(message, frappe.PermissionError)
