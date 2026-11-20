"""
QTT Admin › Reports: one month of QTT OS on one page — businesses gained and lost, people using it, each app's use,
money in, and how fast it answered — and the same as a PDF or CSV. QTT Platform Owners only; read-only.

  monthly(month)          month "YYYY-MM" (default: this month) → the report
  download(month, kind)   kind "pdf" | "csv" → the file (downloaded)
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils import add_months, get_first_day, get_last_day, getdate, today

from qtt_platform import app_areas, perf_rules
from qtt_platform.tenant.guards import require_platform_owner


def _month(month: str | None):
	try:
		start = get_first_day(getdate(f"{month}-01")) if month else get_first_day(getdate(today()))
	except Exception:
		frappe.throw(_("Month as YYYY-MM."))
	return start, get_last_day(start)


def _report(month: str | None) -> dict:
	start, end = _month(month)
	s, e = f"{start} 00:00:00", f"{end} 23:59:59"
	p = {"s": s, "e": e}
	q = lambda sql: frappe.db.sql(sql, p)[0][0] or 0  # noqa: E731

	businesses = {
		"total": q("SELECT COUNT(*) FROM `tabQTT Tenant` WHERE creation <= %(e)s"),
		"new": q("SELECT COUNT(*) FROM `tabQTT Tenant` WHERE creation BETWEEN %(s)s AND %(e)s"),
		"lost": q("SELECT COUNT(*) FROM `tabQTT Tenant` WHERE status IN ('suspended','cancelled','archived') AND modified BETWEEN %(s)s AND %(e)s"),
		"active": q("SELECT COUNT(DISTINCT tenant) FROM `tabQTT App Event` WHERE tenant IS NOT NULL AND occurred_at BETWEEN %(s)s AND %(e)s"),
	}
	people = {
		"members": q("SELECT COUNT(*) FROM `tabQTT Tenant Membership` WHERE status='active' AND creation <= %(e)s"),
		"joined": q("SELECT COUNT(*) FROM `tabQTT Tenant Membership` WHERE creation BETWEEN %(s)s AND %(e)s"),
		"active": q("SELECT COUNT(DISTINCT user) FROM `tabQTT App Event` WHERE occurred_at BETWEEN %(s)s AND %(e)s"),
		"actions": q("SELECT COUNT(*) FROM `tabQTT App Event` WHERE occurred_at BETWEEN %(s)s AND %(e)s"),
	}

	use: dict[str, dict] = {}
	for r in frappe.db.sql(
		"""SELECT COALESCE(area, '') AS a, screen, product, user, tenant, COUNT(*) AS n FROM `tabQTT App Event`
		   WHERE occurred_at BETWEEN %(s)s AND %(e)s GROUP BY a, screen, product, user, tenant""", p, as_dict=True):
		k = r.a or app_areas.area(r.screen, r.product)
		if k in ("os", "admin"):
			continue
		u = use.setdefault(k, {"people": set(), "businesses": set(), "actions": 0})
		u["people"].add(r.user)
		if r.tenant:
			u["businesses"].add(r.tenant)
		u["actions"] += r.n
	apps = sorted(({"key": k, "label": app_areas.LABELS.get(k, k), "people": len(v["people"]), "businesses": len(v["businesses"]),
					"actions": v["actions"]} for k, v in use.items()), key=lambda x: -x["actions"])

	money = {
		"collected": float(q("SELECT SUM(amount) FROM `tabQTT Payment` WHERE status='succeeded' AND paid_at BETWEEN %(s)s AND %(e)s")),
		"invoiced": float(q("SELECT SUM(amount) FROM `tabQTT Invoice` WHERE status IN ('open','paid') AND creation BETWEEN %(s)s AND %(e)s")),
		"open": float(q("SELECT SUM(amount) FROM `tabQTT Invoice` WHERE status='open' AND creation <= %(e)s")),
		"currency": "INR",
	}

	hists = {"app": [], "screen": []}
	for r in frappe.get_all("QTT Perf Hour", filters=[["hour", ">=", s], ["hour", "<=", e], ["call", "=", "*"], ["source", "in", ["app", "screen"]]],
							fields=["source", "hist"], limit=0):
		hists[r.source].append(r.hist)
	speed = {k: perf_rules.summary(perf_rules.merge(v)) for k, v in hists.items()}

	return {"month": str(start)[:7], "from": str(start), "to": str(end), "businesses": businesses, "people": people, "apps": apps, "money": money,
			"speed": speed, "previous": str(add_months(start, -1))[:7], "next": str(add_months(start, 1))[:7] if add_months(start, 1) <= getdate(today()) else None}


@frappe.whitelist(methods=["GET"])
def monthly(month: str | None = None) -> dict:
	"""QTT Admin › Reports: one month (YYYY-MM, default this one) — businesses (total, new, lost, active), people (members,
	joined, active, actions), each app's people / businesses / actions, money (collected, invoiced, open) and speed
	(app calls and screens, p50 / p95)."""
	require_platform_owner()
	return _report(month)


def _rows(r: dict) -> list[tuple[str, str, object]]:
	out = [("Businesses", k, v) for k, v in r["businesses"].items()] + [("People", k, v) for k, v in r["people"].items()]
	for a in r["apps"]:
		out += [(f"App: {a['label']}", k, a[k]) for k in ("people", "businesses", "actions")]
	out += [("Money (INR)", k, v) for k, v in r["money"].items() if k != "currency"]
	for k, v in r["speed"].items():
		out += [(f"Speed: {k}", m, v.get(m)) for m in ("calls", "p50", "p95", "p99")]
	return out


_PDF = """
<div style="font-family: Helvetica, Arial, sans-serif; color:#1E293B; font-size:12px">
  <div style="font-size:20px; font-weight:bold; color:#1E3FB8">QTT OS — {{ r.month }}</div>
  <div style="color:#64748B; margin-bottom:14px">{{ r['from'] }} to {{ r['to'] }}</div>
  {% for section, rows in groups %}
  <div style="font-weight:bold; margin:14px 0 6px; color:#1E3FB8">{{ section }}</div>
  <table style="width:100%; border-collapse:collapse">
    {% for k, v in rows %}<tr style="border-bottom:1px solid #E5E7EB"><td style="padding:5px 6px">{{ k }}</td>
    <td style="padding:5px 6px; text-align:right">{{ v if v is not none else "—" }}</td></tr>{% endfor %}
  </table>
  {% endfor %}
</div>
"""


@frappe.whitelist(methods=["GET"])
def download(month: str | None = None, kind: str = "pdf"):
	"""The month's report as a file: kind "pdf" (one page per section) or "csv" (section, measure, value)."""
	require_platform_owner()
	r = _report(month)
	rows = _rows(r)
	name = f"qtt-os-report-{r['month']}"
	if kind == "csv":
		buf = io.StringIO()
		w = csv.writer(buf)
		w.writerow(["section", "measure", "value"])
		w.writerows(rows)
		frappe.local.response.filename = f"{name}.csv"
		frappe.local.response.filecontent = buf.getvalue().encode("utf-8")
		frappe.local.response.type = "download"
		return
	from frappe.utils.pdf import get_pdf

	groups: dict[str, list] = {}
	for section, k, v in rows:
		groups.setdefault(section, []).append((k, v))
	html = frappe.render_template(_PDF, {"r": r, "groups": list(groups.items())})
	frappe.local.response.filename = f"{name}.pdf"
	frappe.local.response.filecontent = get_pdf(html, {"page-size": "A4", "margin-top": "12mm", "margin-bottom": "12mm", "margin-left": "12mm",
													   "margin-right": "12mm"})
	frappe.local.response.type = "pdf"
