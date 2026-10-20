"""
Office Pulse My work (PROJ-0016 D5; rules in planning_rules.py): everything waiting for this person in one place —
cards given to them on boards, Team tasks, today's calendar and team surveys to answer — by when it's due
(overdue / today / tomorrow / this week / later / no date). Owners and admins also see the team's workload.

  my_work    this person's list
  workload   per person: open and overdue cards, open Team tasks, due this week (owners and admins)
  morning    9 AM every day: "your day" on the phone for everyone with cards due today or overdue
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from qtt_platform import planning_rules as pr


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


@frappe.whitelist(methods=["GET"])
def my_work() -> dict:
	"""This person's open work by when it's due; today's events; team surveys waiting for their answer."""
	from qtt_platform.api import boards, forms, team_calendar, team_extras

	ctx = _ctx()
	today = getdate(nowdate())
	items = boards.my_cards(ctx)
	try:
		for t in team_extras.tasks("mine")["tasks"]:
			items.append({"kind": "task", "name": t["id"], "title": t["title"], "due": getdate(t["due"]) if t["due"] else None,
						  "where": t.get("chat") or _("Team"), "open_chat": t.get("open_chat"), "thread_of": t.get("thread_of")})
	except Exception:
		pass  # Team not set up for this person
	groups = {b: [] for b in pr.BUCKETS}
	for it in items:
		due = getdate(it["due"]) if it.get("due") else None
		it["due"] = str(due) if due else None
		groups[pr.bucket(due, today)].append(it)
	for b in groups.values():
		b.sort(key=lambda x: (x["due"] or "9999", x["title"].lower()))
	try:
		events = [e for e in team_calendar.events(str(today), str(add_days(today, 1)))["events"] if e.get("response") != "no"]
	except Exception:
		events = []
	try:
		surveys = forms.to_answer()["surveys"]
	except Exception:
		surveys = []
	return {"groups": [{"key": k, "items": v} for k, v in groups.items() if v], "events": events, "surveys": surveys,
			"counts": {"open": len(items), "overdue": len(groups["overdue"]), "today": len(groups["today"])}, "admin": bool(ctx.admin)}


@frappe.whitelist(methods=["GET"])
def workload() -> dict:
	"""How much each person has (owners and admins): open cards, overdue, due this week, open Team tasks."""
	from qtt_platform.api.boards import BOARD, CARD, _j
	from qtt_platform.api.team import MSG, _people

	ctx = _ctx()
	if not ctx.admin:
		frappe.throw(_("Only owners and admins see the team's workload."), frappe.PermissionError)
	people = _people(ctx.tenant)
	today = getdate(nowdate())
	week_end = add_days(today, 6 - today.weekday())
	stats = {u: {"user": u, "name": p["name"], "open": 0, "overdue": 0, "week": 0, "tasks": 0} for u, p in people.items()}
	rows = frappe.db.sql(f"""select c.assignees, c.due from `tab{CARD}` c join `tab{BOARD}` b on b.name = c.board
		where c.tenant = %s and c.done = 0 and c.archived = 0 and b.archived = 0""", ctx.tenant, as_dict=True)
	for r in rows:
		due = getdate(r.due) if r.due else None
		for u in _j(r.assignees, []):
			s = stats.get(u)
			if not s:
				continue
			s["open"] += 1
			s["overdue"] += bool(due and due < today)
			s["week"] += bool(due and today <= due <= week_end)
	if people:
		for u, n in frappe.db.sql(f"""select t.allocated_to, count(*) from `tabToDo` t join `tab{MSG}` m on m.name = t.reference_name
			where t.reference_type = %s and t.status = 'Open' and t.allocated_to in %s group by t.allocated_to""", (MSG, tuple(people))):
			if u in stats:
				stats[u]["tasks"] = n
	out = sorted(stats.values(), key=lambda s: (-s["overdue"], -(s["open"] + s["tasks"]), s["name"].lower()))
	return {"people": out}


def morning() -> None:
	"""9 AM: "your day" for everyone with cards due today or overdue (one message each, per business)."""
	from qtt_platform import push
	from qtt_platform.api.boards import BOARD, CARD, _j

	today = getdate(nowdate())
	rows = frappe.db.sql(f"""select c.tenant, c.assignees, c.due, c.title from `tab{CARD}` c join `tab{BOARD}` b on b.name = c.board
		where c.done = 0 and c.archived = 0 and b.archived = 0 and c.due <= %s and c.due >= %s""", (today, add_days(today, -60)), as_dict=True)
	per = defaultdict(lambda: {"today": [], "overdue": 0})
	for r in rows:
		for u in _j(r.assignees, []):
			k = per[(r.tenant, u)]
			if getdate(r.due) == today:
				k["today"].append(r.title)
			else:
				k["overdue"] += 1
	for (tenant, user), k in per.items():
		if not frappe.db.exists("QTT Tenant Membership", {"user": user, "tenant": tenant, "status": "active"}):
			continue
		bits = []
		if k["today"]:
			bits.append(_("{0} due today").format(len(k["today"])))
		if k["overdue"]:
			bits.append(_("{0} overdue").format(k["overdue"]))
		try:
			push.notify([user], title=_("Your day: {0}").format(", ".join(bits)), body=", ".join(k["today"][:3]) or _("Open My work to catch up."),
						data={"kind": "my_work", "tenant": tenant}, collapse_key="my-work")
		except Exception:
			frappe.log_error(title="My work: morning push failed")
