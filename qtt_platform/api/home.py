"""
The app's home: adaptive action cards for the signed-in person in their
active business (rules and card shape in qtt_platform.home_cards).

  actions()        ranked cards — business cards for owners/admins, plus each
                   app's own cards (hook `qtt_home_cards`: (user, tenant) -> list)
  dismiss(key)     hide a card for this person for a week

One app failing never breaks the home: its cards are just left out.
"""

import frappe
from frappe.utils import date_diff, getdate, today

from qtt_platform import home_cards
from qtt_platform.tenant.context import resolve_active_tenant

DISMISS_DAYS = 7


def _dismiss_key(user: str, key: str) -> str:
	return f"qtt_home_dismissed:{user}:{key}"


def _platform(user: str, tenant: str) -> list[dict]:
	m = frappe.db.get_value("QTT Tenant Membership", {"user": user, "tenant": tenant, "status": "active"}, "tenant_role")
	can_manage = m in ("Tenant Owner", "Tenant Admin")
	if not can_manage:
		return []
	sub = frappe.get_all("QTT Product Subscription", filters={"tenant": tenant, "status": ["in", ["trialing", "active", "past_due"]]},
						 fields=["status", "trial_end"], order_by="modified desc")
	status = "past_due" if any(s.status == "past_due" for s in sub) else (sub[0].status if sub else None)
	trial_left = None
	trial_ends = [s.trial_end for s in sub if s.status == "trialing" and s.trial_end]
	if trial_ends:
		trial_left = date_diff(getdate(min(trial_ends)), getdate(today()))
	profile = frappe.db.get_value("QTT Business Profile", tenant, ["gstin", "address_line1", "phone"], as_dict=True) or {}
	logo = frappe.db.get_value("QTT Tenant", tenant, "logo")
	missing = [label for label, value in (("logo", logo), ("address", profile.get("address_line1")),
										  ("phone", profile.get("phone")), ("GSTIN", profile.get("gstin"))) if not value]
	team = frappe.db.count("QTT Tenant Membership", {"tenant": tenant, "status": "active"})
	return home_cards.platform_cards(can_manage=True, sub_status=status, trial_days_left=trial_left,
									 profile_missing=missing, team_size=team)


@frappe.whitelist(methods=["GET"])
def actions() -> list[dict]:
	user = frappe.session.user
	tenant = resolve_active_tenant(user)
	if not tenant:
		return []
	cards = []
	sources = [_platform] + [frappe.get_attr(path) for path in frappe.get_hooks("qtt_home_cards") or []]
	for source in sources:
		try:
			cards.extend(source(user, tenant) or [])
		except Exception:
			# Not set up yet, no access, or a bug: the rest of home still works.
			frappe.log_error(title=f"qtt home cards: {getattr(source, '__module__', source)}", message=frappe.get_traceback())
	dismissed = {c["key"] for c in cards if isinstance(c, dict) and frappe.cache.get_value(_dismiss_key(user, str(c.get("key"))))}
	return home_cards.rank(cards, dismissed)


@frappe.whitelist(methods=["POST"])
def dismiss(key: str) -> dict:
	frappe.cache.set_value(_dismiss_key(frappe.session.user, (key or "")[:140]), 1, expires_in_sec=DISMISS_DAYS * 86400)
	return {"ok": True}
