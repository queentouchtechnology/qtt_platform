"""
QTT Admin › Studio (PROJ-0012 S9): the post template library (each design's picture, how often businesses use it, the
nightly check, on / off) and Studio's use and cost by business. Platform Owner only.

  templates_admin   every template: picture, groups, post types, used, check (ok / problem + what), on / off
  set_template      switch a template on or off (an off one isn't offered to businesses; designs made from it stay)
  run_checks        run the quality check now (it also runs every night)
  usage_admin       this month (or another): by business — designs by kind, AI credits used, what QTT paid the providers,
                    AI jobs that failed; and the totals
"""

import json

import frappe
from frappe import _
from frappe.utils import add_months, get_first_day, get_url, getdate, today

from qtt_platform.design import library, quality
from qtt_platform.tenant.guards import require_platform_owner

DESIGN = "QTT Design"
USAGE = "QTT AI Usage Record"


@frappe.whitelist(methods=["GET"])
def templates_admin() -> dict:
	"""Every post template with its picture, use, nightly check and on / off; the check's totals."""
	require_platform_owner()
	used = {r.template: r.n for r in frappe.db.sql(f"select template, count(*) n from `tab{DESIGN}` where kind='post' group by template", as_dict=True)}
	rows = []
	for d in frappe.get_all(library.DT, fields=["name", "title", "enabled", "layout", "post_types", "groups", "thumbs", "check_status", "check_note",
												"checked_on", "sort"], order_by="sort asc"):


		thumbs = json.loads(d.thumbs or "{}")
		pic = next(iter(thumbs.values()), None)
		rows.append({"key": d.name, "title": d.title, "enabled": bool(d.enabled), "layout": d.layout, "post_types": library._lines(d.post_types),
					 "groups": library._lines(d.groups), "picture": get_url(pic) if pic else None, "used": used.get(d.name, 0),
					 "check_status": d.check_status or "", "check_note": d.check_note or "", "checked_on": str(d.checked_on) if d.checked_on else None})
	last = max((r["checked_on"] for r in rows if r["checked_on"]), default=None)
	return {"templates": rows, "checks": quality.summary(rows), "last_check": last,
			"enabled": sum(1 for r in rows if r["enabled"]), "total": len(rows)}


@frappe.whitelist(methods=["POST"])
def set_template(key: str, enabled: int = 1) -> dict:
	"""Switch a template on or off for every business (designs already made from it stay as they are)."""
	require_platform_owner()
	if not frappe.db.exists(library.DT, key):
		frappe.throw(_("No such template."), frappe.DoesNotExistError)
	frappe.db.set_value(library.DT, key, "enabled", 1 if str(enabled).lower() in ("1", "true") else 0)
	return templates_admin()


@frappe.whitelist(methods=["POST"])
def run_checks() -> dict:
	"""Start the quality check now (every enabled template in every size, on the renderer; a few minutes)."""
	require_platform_owner()
	library.queue_checks()
	return {"queued": True}


@frappe.whitelist(methods=["GET"])
def usage_admin(month: str | None = None) -> dict:
	"""Studio this month (or `month`, YYYY-MM): each business's designs by kind, AI credits used, provider cost (what QTT
	paid), failed AI jobs — most used first — and the totals."""
	require_platform_owner()
	start = getdate(f"{month}-01") if month else get_first_day(today())
	end = add_months(start, 1)
	designs = frappe.db.sql(f"""select tenant, kind, count(*) n from `tab{DESIGN}` where creation >= %s and creation < %s group by tenant, kind""",
							(start, end), as_dict=True)
	ai = frappe.db.sql(f"""select tenant, sum(credits_used) credits, sum(provider_cost) cost, count(*) jobs, sum(status != 'success') failed
						   from `tab{USAGE}` where product='QTT_STUDIO' and creation >= %s and creation < %s group by tenant""", (start, end), as_dict=True)
	by = {}
	for r in designs:
		b = by.setdefault(r.tenant, {"tenant": r.tenant, "designs": {}, "credits": 0.0, "cost": 0.0, "jobs": 0, "failed": 0})
		b["designs"][r.kind] = int(r.n)
	for r in ai:
		b = by.setdefault(r.tenant, {"tenant": r.tenant, "designs": {}, "credits": 0.0, "cost": 0.0, "jobs": 0, "failed": 0})
		b.update({"credits": float(r.credits or 0), "cost": round(float(r.cost or 0), 4), "jobs": int(r.jobs or 0), "failed": int(r.failed or 0)})
	names = {t.name: t.tenant_name for t in frappe.get_all("QTT Tenant", filters={"name": ["in", list(by) or [""]]}, fields=["name", "tenant_name"])}
	rows = sorted(by.values(), key=lambda b: (sum(b["designs"].values()), b["credits"]), reverse=True)
	for b in rows:
		b["name"] = names.get(b["tenant"]) or b["tenant"]
		b["total_designs"] = sum(b["designs"].values())
	by_feature = frappe.db.sql(f"""select feature, count(*) jobs, sum(credits_used) credits, sum(provider_cost) cost from `tab{USAGE}`
								   where product='QTT_STUDIO' and creation >= %s and creation < %s group by feature order by jobs desc""", (start, end), as_dict=True)
	return {"month": str(start)[:7], "businesses": rows,
			"totals": {"designs": sum(b["total_designs"] for b in rows), "credits": sum(b["credits"] for b in rows),
					   "cost": round(sum(b["cost"] for b in rows), 4), "jobs": sum(b["jobs"] for b in rows), "failed": sum(b["failed"] for b in rows)},
			"features": [{"feature": f.feature, "jobs": int(f.jobs or 0), "credits": float(f.credits or 0), "cost": round(float(f.cost or 0), 4)} for f in by_feature]}


def attention() -> list[dict]:
	"""For QTT Admin's home: templates whose last nightly check found a problem."""
	return [{"key": r.name, "title": r.title, "note": (r.check_note or "").split("\n")[0]}
			for r in frappe.get_all(library.DT, filters={"enabled": 1, "check_status": "problem"}, fields=["name", "title", "check_note"])]
