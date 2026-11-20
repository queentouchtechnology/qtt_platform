"""
QTT Admin › People: everyone in every business — who they are, where, how much they use QTT OS and which apps.
QTT Platform Owners only. Read-only: memberships and roles are changed in Workspaces (each business).

  people(q, show, start)  everyone with a membership: name, email, businesses and roles, last seen, days active and
                          actions in the last 30 days, the apps they used, phone or web and app version
  person(user)            one person: the same, plus each app's use, their last 30 days day by day and their latest
                          activity (QTT App Event, areas from qtt_platform.app_areas)
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

from qtt_platform import app_areas
from qtt_platform.tenant.guards import require_platform_owner

EVENTS = "QTT App Event"
DAYS = 30
_NOT_APPS = {"os", "admin"}
_SHOWS = ("all", "active", "quiet", "never")


def _members() -> dict[str, list[dict]]:
	rows = frappe.db.sql(
		"""SELECT m.user, m.tenant, m.tenant_role, t.tenant_name
		   FROM `tabQTT Tenant Membership` m JOIN `tabQTT Tenant` t ON t.name = m.tenant
		   WHERE m.status = 'active' ORDER BY t.tenant_name""",
		as_dict=True,
	)
	out: dict[str, list[dict]] = {}
	for r in rows:
		out.setdefault(r.user, []).append({"tenant": r.tenant, "name": r.tenant_name, "role": r.tenant_role})
	return out


def _usage(users: list[str]) -> dict[str, dict]:
	"""Per person: last seen (ever), days active, actions and apps in the last 30 days, last platform and version."""
	if not users:
		return {}
	since = add_days(now_datetime(), -DAYS)
	out = {u: {"last_seen": None, "days": 0, "actions": 0, "apps": [], "platform": None, "version": None} for u in users}
	for r in frappe.db.sql(f"SELECT user, MAX(occurred_at) AS last FROM `tab{EVENTS}` WHERE user IN %(u)s GROUP BY user", {"u": users}, as_dict=True):
		out[r.user]["last_seen"] = r.last
	for r in frappe.db.sql(
		f"""SELECT user, COUNT(*) AS n, COUNT(DISTINCT DATE(occurred_at)) AS days FROM `tab{EVENTS}`
		    WHERE user IN %(u)s AND occurred_at >= %(s)s GROUP BY user""",
		{"u": users, "s": since},
		as_dict=True,
	):
		out[r.user].update(actions=r.n, days=r.days)
	per_app: dict[str, dict[str, int]] = {}
	for r in frappe.db.sql(
		f"""SELECT user, COALESCE(area, '') AS a, screen, product, COUNT(*) AS n FROM `tab{EVENTS}`
		    WHERE user IN %(u)s AND occurred_at >= %(s)s GROUP BY user, a, screen, product""",
		{"u": users, "s": since},
		as_dict=True,
	):
		key = r.a or app_areas.area(r.screen, r.product)  # older events are filled by analytics.backfill_areas
		if key not in _NOT_APPS:
			apps = per_app.setdefault(r.user, {})
			apps[key] = apps.get(key, 0) + r.n
	for user, apps in per_app.items():
		out[user]["apps"] = [{"key": k, "label": app_areas.LABELS.get(k, k), "count": n} for k, n in sorted(apps.items(), key=lambda x: -x[1])]
	for r in frappe.db.sql(
		f"""SELECT e.user, e.platform, e.app_version FROM `tab{EVENTS}` e
		    JOIN (SELECT user, MAX(occurred_at) AS last FROM `tab{EVENTS}` WHERE user IN %(u)s GROUP BY user) x
		      ON x.user = e.user AND x.last = e.occurred_at""",
		{"u": users},
		as_dict=True,
	):
		out[r.user].update(platform=r.platform, version=r.app_version)
	return out


def _show_ok(show: str, u: dict) -> bool:
	if show == "active":
		return u["days"] > 0
	if show == "quiet":  # seen before, nothing in the last 30 days
		return bool(u["last_seen"]) and u["days"] == 0
	if show == "never":
		return not u["last_seen"]
	return True


@frappe.whitelist(methods=["GET"])
def people(q: str | None = None, show: str | None = "all", start: int = 0) -> dict:
	"""QTT Admin › People: everyone in every business (most recently seen first), with counts for the filters.
	`show`: all | active (used the app in the last 30 days) | quiet (not in 30 days) | never (never opened it)."""
	require_platform_owner()
	show = show if show in _SHOWS else "all"
	members = _members()
	users = list(members)
	profiles = {r.name: r for r in frappe.get_all("User", filters={"name": ["in", users or [""]]}, fields=["name", "full_name", "user_image", "enabled"])}
	usage = _usage(users)
	text = (q or "").strip().lower()
	rows = []
	counts = {s: 0 for s in _SHOWS}
	for u in users:
		p = profiles.get(u) or frappe._dict()
		us = usage.get(u) or {}
		businesses = members[u]
		hay = " ".join([u, p.get("full_name") or ""] + [b["name"] or "" for b in businesses]).lower()
		if text and text not in hay:
			continue
		for s in _SHOWS:
			if _show_ok(s, us):
				counts[s] += 1
		if not _show_ok(show, us):
			continue
		rows.append({
			"user": u,
			"name": p.get("full_name") or u,
			"image": p.get("user_image"),
			"enabled": bool(p.get("enabled", 1)),
			"businesses": businesses,
			**us,
		})
	rows.sort(key=lambda r: (r["last_seen"] is None, -(get_datetime(r["last_seen"]).timestamp() if r["last_seen"] else 0), r["name"].lower()))
	start = max(0, int(start or 0))
	return {"people": rows[start:start + 100], "total": len(rows), "counts": counts, "days": DAYS}


@frappe.whitelist(methods=["GET"])
def person(user: str) -> dict:
	"""QTT Admin › People › one person: businesses and roles, sign-in, each app's use and their last 30 days day by
	day, and their latest 50 actions (screens opened, sign-ins…)."""
	require_platform_owner()
	if not frappe.db.exists("User", user):
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	p = frappe.db.get_value("User", user, ["full_name", "user_image", "enabled", "last_login", "last_active", "mobile_no", "creation"], as_dict=True)
	businesses = _members().get(user, [])
	us = _usage([user]).get(user, {})
	since = add_days(now_datetime(), -DAYS)
	daily = {
		str(r.d): r.n
		for r in frappe.db.sql(
			f"SELECT DATE(occurred_at) AS d, COUNT(*) AS n FROM `tab{EVENTS}` WHERE user = %(u)s AND occurred_at >= %(s)s GROUP BY d",
			{"u": user, "s": since},
			as_dict=True,
		)
	}
	days = [str(add_days(now_datetime(), -i).date()) for i in range(DAYS - 1, -1, -1)]
	recent = frappe.get_all(EVENTS, filters={"user": user}, fields=["event", "screen", "area", "occurred_at", "platform", "app_version"],
							order_by="occurred_at desc", limit=50)
	for r in recent:
		r["area"] = r.area or app_areas.area(r.screen, None)
		r["area_label"] = app_areas.LABELS.get(r["area"])
	return {
		"user": user,
		"name": p.full_name or user,
		"image": p.user_image,
		"enabled": bool(p.enabled),
		"mobile": p.mobile_no,
		"joined": p.creation,
		"last_login": p.last_login,
		"last_active": p.last_active,
		"businesses": businesses,
		**us,
		"daily": [{"day": d, "count": daily.get(d, 0)} for d in days],
		"recent": recent,
	}
