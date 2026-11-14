"""
Free use (PROJ-0024): all 8 apps without a plan until one simple limit per app; then one plan for everything.
Rules in qtt_platform.free_use; limits and the plan's prices in Desk › QTT App Settings › Free use and the one plan.

  status()                     for the app: each app's used / limit / left, whether the gate is up, the plan's prices
  usage(tenant)                how much of each app the business has used (hook `qtt_free_use`: (tenant) -> {key: n},
                               plus Studio's designs from here)
  check(tenant, key, adding)   the gate for code that makes something new: raises FreeLimitReached past the limit
  is_subscribed(tenant)        on the one plan (or QTT's own workspace) — never limited

One app failing to count never stops anyone: its count is just 0.
"""

import frappe
from frappe import _

from qtt_platform import free_use as rules
from qtt_platform.house import is_house
from qtt_platform.tenant.context import resolve_active_tenant

#: The one plan for all 8 apps (task 4 creates it); until then nobody is "subscribed" except QTT's own workspaces.
ONE_PLAN_PRODUCT = "QTT_OS"
_OPEN = ("trialing", "active", "past_due")


class FreeLimitReached(frappe.ValidationError):
	"""Past an app's free limit: the app shows the one plan instead of an error (HTTP 402)."""

	http_status_code = 402


def _settings() -> dict:
	try:
		return frappe.get_cached_doc("QTT App Settings").as_dict()
	except Exception:
		return {}


def is_subscribed(tenant: str) -> bool:
	if is_house(tenant):
		return True
	return bool(frappe.db.exists("QTT Product Subscription", {"tenant": tenant, "product": ONE_PLAN_PRODUCT, "status": ["in", list(_OPEN)]}))


def _studio(tenant: str) -> dict:
	return {"studio": frappe.db.count("QTT Design", {"tenant": tenant})}


def usage(tenant: str) -> dict:
	used = {}
	for source in [_studio] + [frappe.get_attr(path) for path in frappe.get_hooks("qtt_free_use") or []]:
		try:
			for key, n in (source(tenant) or {}).items():
				if key in rules.KEYS:
					used[key] = used.get(key, 0) + int(n or 0)
		except Exception:
			frappe.log_error(title=f"qtt free use: {getattr(source, '__module__', source)}", message=frappe.get_traceback())
	return used


def _state(tenant: str) -> dict:
	s = _settings()
	return {"settings": s, "enabled": bool(s.get("free_use_enabled", 1)), "subscribed": is_subscribed(tenant),
			"limits": rules.limits_from(s)}


def check(tenant: str, key: str, adding: int = 1) -> None:
	"""Call before making something new in an app (a person, a bill, a website, a post…). Past the free limit: raises
	FreeLimitReached, which the app turns into the one-plan sheet."""
	st = _state(tenant)
	if not rules.limited(st["enabled"], st["subscribed"]):
		return
	used = usage(tenant).get(key, 0)
	if rules.blocked(key, used, st["limits"], enabled=st["enabled"], subscribed=st["subscribed"], adding=adding):
		label = next((name for k, name, _u in rules.APPS if k == key), key)
		frappe.throw(_("You've used the free {0}. Subscribe to keep going — one plan for all 8 apps.").format(label),
					 FreeLimitReached, title=f"free_limit:{key}")


@frappe.whitelist(methods=["GET"])
def status() -> dict:
	"""What the app shows about free use for the signed-in person's business.

	Returns {limited, gate, reached: [app keys], apps: [{key, label, unit, used, limit, left, reached}],
	plan: {monthly, yearly}, subscribed}. `limit`/`left` are null when that app has no limit (or the business is on
	the plan, or free use is switched off in Desk)."""
	tenant = resolve_active_tenant(frappe.session.user)
	if not tenant:
		return {"limited": False, "gate": False, "reached": [], "apps": [], "plan": rules.plan_prices({}), "subscribed": False}
	st = _state(tenant)
	out = rules.status(usage(tenant), st["limits"], enabled=st["enabled"], subscribed=st["subscribed"])
	return {**out, "plan": rules.plan_prices(st["settings"]), "subscribed": st["subscribed"]}
