"""
QTT Admin › Apps: every app (HR & staff, ERP, Store, Website, WhatsApp & AI, Content Hub, Social media, Studio, Inbox,
Business Suite, Team & workplace) — who uses it and how fast it answers. QTT Platform Owners only; read-only (amounts
and flags are changed in Settings).

  apps()        one card per app: people active in 7 and 30 days, businesses using it in 30 days, actions in 30 days,
                its server calls' p50 / p95 over the last day (QTT Perf Hour)
  app(key)      one app: the same, plus each business's use, people per day over 30 days, its most used screens, its
                slowest calls over 7 days, its free amounts and plan fair use (qtt_platform.free_use) and the feature
                flags named after it

Areas: qtt_platform.app_areas (events by screen, calls by module).
"""

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from qtt_platform import app_areas, free_use, perf_rules
from qtt_platform.tenant.guards import require_platform_owner

EVENTS = "QTT App Event"
PERF = "QTT Perf Hour"
_SHOWN = [k for k, _l, _p, _s in app_areas.AREAS if k not in ("os", "admin")]


def _area_sql() -> str:
	"""Events saved before areas were noted are counted by screen in Python; this keeps SQL simple."""
	return "COALESCE(area, '')"


def _event_rows(since, extra: str = "", params: dict | None = None) -> list[dict]:
	return frappe.db.sql(
		f"""SELECT {_area_sql()} AS a, screen, product, user, tenant, DATE(occurred_at) AS d, COUNT(*) AS n
		    FROM `tab{EVENTS}` WHERE occurred_at >= %(since)s {extra}
		    GROUP BY a, screen, product, user, tenant, d""",
		{"since": since, **(params or {})},
		as_dict=True,
	)


def _key(r) -> str:
	return r.a or app_areas.area(r.screen, r.product)


def _speed(days: int) -> dict[str, dict]:
	"""Each app's calls' merged histogram → p50 / p95 / calls over the last [days] (people in the app only)."""
	hists: dict[str, list] = {}
	for r in frappe.get_all(PERF, filters={"hour": [">=", add_days(now_datetime(), -days)], "source": "app"}, fields=["call", "hist"], limit=0):
		if r.call == "*":
			continue
		hists.setdefault(app_areas.area_of_call(r.call), []).append(r.hist)
	return {k: perf_rules.summary(perf_rules.merge(v)) for k, v in hists.items()}


def _summary(rows: list[dict]) -> dict[str, dict]:
	week = str(add_days(now_datetime(), -7).date())
	out = {k: {"people_7": set(), "people_30": set(), "businesses": set(), "actions": 0} for k in _SHOWN}
	for r in rows:
		k = _key(r)
		if k not in out:
			continue
		o = out[k]
		o["people_30"].add(r.user)
		if str(r.d) >= week:
			o["people_7"].add(r.user)
		if r.tenant:
			o["businesses"].add(r.tenant)
		o["actions"] += r.n
	return {k: {"people_7": len(v["people_7"]), "people_30": len(v["people_30"]), "businesses": len(v["businesses"]), "actions": v["actions"]}
			for k, v in out.items()}


@frappe.whitelist(methods=["GET"])
def apps() -> dict:
	"""QTT Admin › Apps: every app with people active in 7 / 30 days, businesses using it, actions in 30 days and its
	speed over the last day (p50 / p95 of its server calls)."""
	require_platform_owner()
	usage = _summary(_event_rows(add_days(now_datetime(), -30)))
	speed = _speed(1)
	return {"apps": [{"key": k, "label": app_areas.LABELS[k], **usage[k], "speed": speed.get(k)} for k in _SHOWN]}


@frappe.whitelist(methods=["GET"])
def app(key: str) -> dict:
	"""QTT Admin › Apps › one app: its use by each business, people per day (30 days), most used screens, slowest calls
	(7 days), free amounts and plan fair use, and its feature flags."""
	require_platform_owner()
	if key not in _SHOWN:
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	since = add_days(now_datetime(), -30)
	rows = [r for r in _event_rows(since) if _key(r) == key]
	usage = _summary(rows)[key]

	names = {t.name: t.tenant_name for t in frappe.get_all("QTT Tenant", fields=["name", "tenant_name"], limit=0)}
	per_business: dict[str, dict] = {}
	daily: dict[str, set] = {}
	screens: dict[str, int] = {}
	for r in rows:
		b = per_business.setdefault(r.tenant or "", {"people": set(), "actions": 0, "last": None})
		b["people"].add(r.user)
		b["actions"] += r.n
		b["last"] = max(b["last"] or str(r.d), str(r.d))
		daily.setdefault(str(r.d), set()).add(r.user)
		if r.screen:
			screens[r.screen] = screens.get(r.screen, 0) + r.n
	days = [str(add_days(now_datetime(), -i).date()) for i in range(29, -1, -1)]

	calls: dict[str, list] = {}
	for r in frappe.get_all(PERF, filters={"hour": [">=", add_days(now_datetime(), -7)], "source": "app"}, fields=["call", "hist"], limit=0):
		if r.call != "*" and app_areas.area_of_call(r.call) == key:
			calls.setdefault(r.call, []).append(r.hist)
	slow = sorted(({"name": c, **perf_rules.summary(perf_rules.merge(h))} for c, h in calls.items()), key=lambda x: -(x["p95"] or 0))

	from qtt_platform.api.free_use import _settings

	settings = _settings()
	free = free_use.limits_from(settings)
	plan = free_use.plan_limits_from(settings)
	free_names = {k: (n, unit) for k, n, unit in free_use.APPS}
	plan_names = {k: (n, unit, period) for k, n, unit, period in free_use.PLAN_ITEMS}
	words = [key, app_areas.LABELS[key].split()[0].lower()]
	flags = [f for f in frappe.get_all("QTT App Feature Flag", fields=["flag_key", "enabled", "description"], limit=0)
			 if any(w in (f.flag_key or "").lower() for w in words)]

	return {
		"key": key,
		"label": app_areas.LABELS[key],
		**usage,
		"speed": _speed(1).get(key),
		"businesses_list": sorted(
			({"tenant": t, "name": names.get(t, t or _("No business")), "people": len(v["people"]), "actions": v["actions"], "last": v["last"]}
			 for t, v in per_business.items()),
			key=lambda x: -x["actions"],
		),
		"daily": [{"day": d, "people": len(daily.get(d, ()))} for d in days],
		"screens": [{"screen": s, "count": n} for s, n in sorted(screens.items(), key=lambda x: -x[1])[:10]],
		"slowest": slow[:10],
		"free": [{"key": k, "name": free_names[k][0], "unit": free_names[k][1], "limit": free.get(k), "period": free_use.FREE_PERIOD.get(k, "in_total")}
				 for k in app_areas.FREE_KEYS.get(key, []) if k in free_names],
		"plan": [{"key": k, "name": plan_names[k][0], "unit": plan_names[k][1], "limit": plan.get(k), "period": plan_names[k][2]}
				 for k in app_areas.PLAN_KEYS.get(key, []) if k in plan_names],
		"flags": flags,
	}
