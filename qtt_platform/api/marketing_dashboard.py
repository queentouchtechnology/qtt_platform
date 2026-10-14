"""
QTT Admin → Marketing dashboard: today / yesterday / any day, the daily
schedule (rearrange, and move n8n run times), and the month plan
(targets, weeks, to-dos, special days). Platform Owners only.

Numbers come from QTT's own data on this site — CRM Lead (new leads, call
outcomes, calls due), FCRM Note (outreach emails, replies), Task (job
applications) — plus n8n runs. Definitions match the 08:00 n8n report
(marketing-ai-os/18_AUTOMATIONS/REPORTS/patch_daily_report.py) so the app
and the report never disagree. Past days are read from a snapshot saved
just after midnight, so they stay as they were.
"""

import json
from datetime import datetime, timedelta, timezone

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime, today
from frappe.utils.data import get_system_timezone

from qtt_platform.audit import write_audit_event
from qtt_platform.marketing import report as rpt
from qtt_platform.marketing.n8n import N8nClient, N8nError
from qtt_platform.marketing.n8n import _status as run_status
from qtt_platform.marketing.n8n_schedule import ScheduleError, clean_days, parse_time, summarize, with_schedule
from qtt_platform.tenant.guards import require_platform_owner

SETTINGS = "QTT Marketing Settings"
PLAN = "QTT Marketing Plan"
SLOT = "QTT Marketing Schedule Slot"
SNAPSHOT = "QTT Marketing Daily Report"

# Same definitions as the 08:00 report.
CALL_OUTCOMES = ("Interested", "Callback", "No answer", "Not interested", "Send info", "Do not call", "Wrong person",
				 "Requested human", "Appointment booked")
CALLABLE = ("To call", "No answer", "Callback", "Interested", "Send info", "Requested human", "Appointment booked")
SLOT_FIELDS = ("name", "title", "kind", "owner_name", "start_time", "end_time", "days", "valid_from", "valid_to",
			   "n8n_workflow_id", "notes", "sort_order", "enabled")


# --------------------------------------------------------------------------
# Dashboard and day reports
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def dashboard() -> dict:
	"""The Overview: what needs a decision, today against yesterday, the last 14 days, the
	outreach funnel, this month's content and targets, and how the automations are doing."""
	require_platform_owner()
	day = getdate(today())
	automation = _automation_data(day - timedelta(days=6))
	return {
		"today": _day(day, automation=automation),
		"yesterday": _stored_or_live(day - timedelta(days=1), automation=automation),
		"month": _month(day),
		"approvals_pending": frappe.db.count("QTT Marketing Content", {"status": "pending"})
		if frappe.db.table_exists("QTT Marketing Content") else 0,
		"pending": _pending(),
		"series": _series(day, 14),
		"funnel": _funnel(day, 30),
		"content_month": _content_month(day),
		"automation_week": _automation_week(automation),
		"n8n_error": automation.get("error"),
	}


def _pending() -> list[dict]:
	if not frappe.db.table_exists("QTT Marketing Content"):
		return []
	rows = frappe.get_all("QTT Marketing Content", filters={"status": "pending"}, order_by="expires_at asc",
						  fields=["name", "kind", "title", "site", "summary", "preview_url", "expires_at", "timeout_action", "creation"])
	for r in rows:
		r["expires_at"] = str(r.expires_at) if r.expires_at else None
		r["creation"] = str(r.creation)
	return rows


def _series(day, days: int) -> dict:
	"""Per day for the last `days` days (oldest first): leads, calls, emails sent, replies."""
	first = day - timedelta(days=days - 1)
	lo, hi = str(first), str(day + timedelta(days=1))
	dates = [str(first + timedelta(days=i)) for i in range(days)]
	out: dict = {"dates": dates}

	def per_day(sql: str, params: dict | None = None) -> list[int]:
		rows = dict(frappe.db.sql(sql, {"lo": lo, "hi": hi, **(params or {})}))
		return [int(rows.get(getdate(d), 0) or rows.get(d, 0) or 0) for d in dates]

	if frappe.db.table_exists("CRM Lead"):
		out["leads"] = per_day("SELECT DATE(creation), COUNT(*) FROM `tabCRM Lead` WHERE creation >= %(lo)s AND creation < %(hi)s GROUP BY DATE(creation)")
		if frappe.db.has_column("CRM Lead", "custom_call_status"):
			out["calls"] = per_day("""SELECT DATE(modified), COUNT(*) FROM `tabCRM Lead` WHERE modified >= %(lo)s AND modified < %(hi)s
									  AND custom_call_status IN %(o)s GROUP BY DATE(modified)""", {"o": CALL_OUTCOMES})
	if frappe.db.table_exists("FCRM Note"):
		out["emails_sent"] = per_day("""SELECT DATE(creation), COUNT(*) FROM `tabFCRM Note` WHERE creation >= %(lo)s AND creation < %(hi)s
										AND title REGEXP 'Outreach email [0-9] sent' GROUP BY DATE(creation)""")
		out["email_replies"] = per_day("""SELECT DATE(creation), COUNT(*) FROM `tabFCRM Note` WHERE creation >= %(lo)s AND creation < %(hi)s
										  AND title LIKE %(r)s AND title NOT LIKE %(b)s GROUP BY DATE(creation)""",
									   {"r": "%📥 Outreach%", "b": "%bounce%"})
	return out


def _funnel(day, days: int) -> list[dict]:
	"""Outreach over the last `days` days: leads → called → emailed → replied → interested."""
	crm = _crm_numbers(day - timedelta(days=days - 1), day)
	steps = [("leads", "New leads"), ("calls", "Calls made"), ("emails_sent", "Emails sent"), ("email_replies", "Replies")]
	out = [{"key": k, "label": label, "count": (crm.get(k) or {}).get("count", 0)} for k, label in steps if k in crm]
	calls = (crm.get("calls") or {}).get("by") or {}
	if calls:
		out.append({"key": "interested", "label": "Interested or booked",
					"count": sum(v for k, v in calls.items() if k in ("Interested", "Appointment booked"))})
	return out


def _content_month(day) -> dict:
	"""This month's content by kind: published (or sent), skipped, rejected, waiting."""
	if not frappe.db.table_exists("QTT Marketing Content"):
		return {}
	rows = frappe.db.sql("""SELECT kind, status, COUNT(*) FROM `tabQTT Marketing Content`
							WHERE creation >= %(lo)s GROUP BY kind, status""", {"lo": str(day.replace(day=1))})
	out: dict = {}
	for kind, status, n in rows:
		bucket = {"published": "done", "approved": "done", "expired": "skipped", "rejected": "rejected", "pending": "waiting",
				  "failed": "failed"}.get(status, "skipped")
		out.setdefault(kind, {}).setdefault(bucket, 0)
		out[kind][bucket] += n
	return out


def _automation_week(automation: dict) -> dict:
	"""Runs and failures over the last 7 days, and which workflows failed."""
	names = {w["id"]: w["name"] for w in automation.get("workflows", [])}
	runs = failed = 0
	failing: dict = {}
	for e in automation.get("executions", []):
		runs += 1
		if run_status(e) == "failed":
			failed += 1
			wid = str(e.get("workflowId"))
			f = failing.setdefault(wid, {"id": wid, "name": names.get(wid, wid), "failed": 0, "last": None})
			f["failed"] += 1
			f["last"] = max(f["last"] or "", str(e.get("startedAt") or ""))
	return {"runs": runs, "failed": failed, "active": sum(1 for w in automation.get("workflows", []) if w.get("active")),
			"failing": sorted(failing.values(), key=lambda f: -f["failed"])}


@frappe.whitelist(methods=["GET"])
def day_report(date: str) -> dict:
	require_platform_owner()
	return _stored_or_live(getdate(date))


def snapshot_yesterday() -> None:
	"""Scheduler (daily): keep yesterday's report as it was."""
	day = getdate(today()) - timedelta(days=1)
	try:
		data = _day(day)
	except Exception:
		frappe.log_error(title="qtt_platform marketing snapshot failed")
		return
	doc = frappe.get_doc(SNAPSHOT, str(day)) if frappe.db.exists(SNAPSHOT, str(day)) else frappe.new_doc(SNAPSHOT)
	doc.update({"report_date": day, "generated_at": now_datetime(), "data": json.dumps(data, default=str)})
	doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)


def _stored_or_live(day, *, automation: dict | None = None) -> dict:
	if day < getdate(today()) and frappe.db.exists(SNAPSHOT, str(day)):
		try:
			data = json.loads(frappe.db.get_value(SNAPSHOT, str(day), "data") or "{}")
			if data:
				return {**data, "snapshot": True}
		except ValueError:
			pass
	return _day(day, automation=automation)


def _day(day, *, automation: dict | None = None) -> dict:
	automation = automation if automation is not None else _automation_data(day)
	now = now_datetime()
	executions = [e for e in automation.get("executions", []) if str(e.get("startedAt", ""))[:10] == str(day)]
	plan = _plan_doc(day.strftime("%Y-%m"))
	notes = [n.note for n in (plan.day_notes if plan else []) if getdate(n.date) == day]
	week = rpt.current_week([w.as_dict() for w in plan.weeks], day) if plan else None
	return rpt.day_report(
		day=day,
		now=now,
		slots=_slots(),
		workflows=automation.get("workflows", []),
		executions=executions,
		crm=_crm_numbers(day, day, calls_due=day >= getdate(today())),
		notes=notes,
		week=week,
	) | {"n8n_error": automation.get("error")}


def _automation_data(since_day) -> dict:
	"""Workflows + runs since the start of `since_day` (local), with each
	run's startedAt converted to local time. Never fails the dashboard: an
	n8n problem comes back as `error`."""
	settings = frappe.get_cached_doc(SETTINGS)
	key = settings.get_password("n8n_api_key", raise_exception=False) if settings.n8n_url else None
	if not (settings.enabled and settings.n8n_url and key):
		return {"workflows": [], "executions": [], "error": None}
	tz = get_system_timezone()
	start_local = datetime.combine(since_day, datetime.min.time())
	start_utc = _to_utc(start_local, tz)
	try:
		client = N8nClient(settings.n8n_url, key)
		workflows = [{"id": str(w.get("id")), "name": w.get("name"), "active": bool(w.get("active"))} for w in client.workflows()]
		executions = []
		for e in client.executions_since(start_utc):
			started = e.get("startedAt")
			if not started:
				continue
			local = _to_local(started, tz)
			executions.append({**e, "startedAt": local.isoformat()})
		return {"workflows": workflows, "executions": executions, "error": None}
	except N8nError as exc:
		return {"workflows": [], "executions": [], "error": str(exc)}


def _to_utc(local: datetime, tz: str) -> datetime:
	from zoneinfo import ZoneInfo
	return local.replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def _to_local(value: str, tz: str) -> datetime:
	from zoneinfo import ZoneInfo
	dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
	if not dt.tzinfo:
		dt = dt.replace(tzinfo=timezone.utc)
	return dt.astimezone(ZoneInfo(tz)).replace(tzinfo=None)


# --------------------------------------------------------------------------
# CRM numbers (same definitions as the 08:00 report)
# --------------------------------------------------------------------------
def _crm_numbers(start, end, *, calls_due: bool = False) -> dict:
	"""Counts between start and end (inclusive dates)."""
	lo, hi = str(start), str(end + timedelta(days=1))
	out: dict = {}
	lead = "CRM Lead"
	if frappe.db.table_exists(lead):
		region = "custom_region" if frappe.db.has_column(lead, "custom_region") else None
		out["leads"] = _count_by(lead, "creation", lo, hi, region)
		if frappe.db.has_column(lead, "custom_call_status"):
			out["calls"] = _count_by(lead, "modified", lo, hi, "custom_call_status",
									 extra="custom_call_status IN %(outcomes)s", params={"outcomes": CALL_OUTCOMES})
			if calls_due:
				nxt = "AND (custom_next_call IS NULL OR DATE(custom_next_call) <= %(day)s)" if frappe.db.has_column(lead, "custom_next_call") else ""
				rows = frappe.db.sql(
					f"""SELECT {region or "''"} AS k, COUNT(*) AS n FROM `tabCRM Lead`
					    WHERE custom_call_status IN %(callable)s {nxt} GROUP BY k""",
					{"callable": CALLABLE, "day": str(start)},
					as_dict=True,
				)
				out["calls_due"] = {"count": sum(r.n for r in rows), "by": {r.k or "—": r.n for r in rows}}
	if frappe.db.table_exists("FCRM Note"):
		out["emails_sent"] = _note_count(lo, hi, "title REGEXP 'Outreach email [0-9] sent'")
		out["email_replies"] = _note_count(lo, hi, "title LIKE %(reply)s AND title NOT LIKE %(bounce)s")
	if frappe.db.table_exists("QTT Marketing Content"):
		for kind, key in (("article", "articles"), ("linkedin", "linkedin_posts")):
			n = frappe.db.sql(
				"""SELECT COUNT(*) FROM `tabQTT Marketing Content` WHERE kind=%(k)s AND status='published'
				   AND COALESCE(published_at, decided_at) >= %(lo)s AND COALESCE(published_at, decided_at) < %(hi)s""",
				{"k": kind, "lo": lo, "hi": hi},
			)[0][0]
			out[key] = {"count": n}
	project = frappe.db.get_single_value(SETTINGS, "jobs_project") if frappe.db.table_exists("Task") else None
	if project:
		n = frappe.db.sql(
			"SELECT COUNT(*) FROM `tabTask` WHERE project=%(p)s AND creation >= %(lo)s AND creation < %(hi)s",
			{"p": project, "lo": lo, "hi": hi},
		)[0][0]
		out["applications"] = {"count": n}
	return out


def _count_by(doctype, date_field, lo, hi, group_field, *, extra: str | None = None, params: dict | None = None) -> dict:
	where = f"`{date_field}` >= %(lo)s AND `{date_field}` < %(hi)s" + (f" AND {extra}" if extra else "")
	key = f"`{group_field}`" if group_field else "''"
	rows = frappe.db.sql(
		f"SELECT {key} AS k, COUNT(*) AS n FROM `tab{doctype}` WHERE {where} GROUP BY k",
		{"lo": lo, "hi": hi, **(params or {})},
		as_dict=True,
	)
	return {"count": sum(r.n for r in rows), "by": {(r.k or "—"): r.n for r in rows} if group_field else {}}


def _note_count(lo, hi, condition: str) -> dict:
	n = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabFCRM Note` WHERE creation >= %(lo)s AND creation < %(hi)s AND {condition}",
		{"lo": lo, "hi": hi, "reply": "%📥 Outreach%", "bounce": "%bounce%"},
	)[0][0]
	return {"count": n}


# --------------------------------------------------------------------------
# Month plan
# --------------------------------------------------------------------------
def _plan_doc(month: str):
	return frappe.get_doc(PLAN, month) if frappe.db.exists(PLAN, month) else None


def _month(day) -> dict:
	month = day.strftime("%Y-%m")
	plan = _plan_doc(month)
	first = day.replace(day=1)
	nxt = (first + timedelta(days=32)).replace(day=1)
	crm = _crm_numbers(first, day)
	actuals = {k: (crm.get(k) or {}).get("count") for k in rpt.METRIC_KEYS if k in crm}
	return {
		"month": month,
		"exists": bool(plan),
		"title": plan.title if plan else None,
		"progress": rpt.progress([t.as_dict() for t in plan.targets], actuals, day=day, month_days=(nxt - first).days) if plan else [],
		"actuals": actuals,
		"week": rpt.current_week([w.as_dict() for w in plan.weeks], day) if plan else None,
		"todos_open": [
			{"idx": t.idx, "title": t.title, "due_date": str(t.due_date) if t.due_date else None, "owner": t.owner_name}
			for t in (plan.todos if plan else []) if (t.status or "open") == "open"
		],
	}


@frappe.whitelist(methods=["GET"])
def get_plan(month: str | None = None) -> dict:
	require_platform_owner()
	month = month or getdate(today()).strftime("%Y-%m")
	plan = _plan_doc(month)
	if not plan:
		return {"month": month, "exists": False, "months": _plan_months()}
	return {"exists": True, "months": _plan_months(), **_plan_dict(plan)}


@frappe.whitelist(methods=["POST"])
def save_plan(plan) -> dict:
	"""Create or replace one month's plan (targets, weeks, to-dos, special
	days). The app always sends the whole plan."""
	require_platform_owner()
	data = _json(plan)
	month = str(data.get("month") or "").strip()
	doc = _plan_doc(month) or frappe.new_doc(PLAN)
	before = _plan_dict(doc) if not doc.is_new() else None
	doc.month = month
	doc.title = (data.get("title") or "").strip()
	doc.status = data.get("status") if data.get("status") in ("draft", "active", "done") else "active"
	doc.summary = (data.get("summary") or "").strip()
	doc.set("targets", [_pick(t, "metric", "target", "target_number", "metric_key", "notes") for t in data.get("targets") or [] if t.get("metric")])
	doc.set("weeks", [_pick(w, "label", "start_date", "end_date", "details") for w in data.get("weeks") or [] if w.get("label")])
	doc.set("todos", [_pick(t, "due_date", "title", "owner_name", "status") for t in data.get("todos") or [] if t.get("title")])
	doc.set("day_notes", [_pick(n, "date", "note") for n in data.get("day_notes") or [] if n.get("date") and n.get("note")])
	for t in doc.targets:
		if t.metric_key and t.metric_key not in rpt.METRIC_KEYS:
			t.metric_key = None
	doc.save(ignore_permissions=True) if before else doc.insert(ignore_permissions=True)
	write_audit_event("marketing_plan_saved", target_doctype=PLAN, target_name=doc.name,
					  metadata={"month": month, "created": before is None})
	return get_plan(month)


@frappe.whitelist(methods=["POST"])
def set_todo_status(month: str, idx: int, status: str) -> dict:
	require_platform_owner()
	if status not in ("open", "done"):
		frappe.throw(_("Status must be open or done."))
	plan = _plan_doc(month)
	row = next((t for t in (plan.todos if plan else []) if t.idx == int(idx)), None)
	if not row:
		frappe.throw(_("Unknown to-do."), frappe.DoesNotExistError)
	row.status = status
	plan.save(ignore_permissions=True)
	write_audit_event("marketing_todo_" + status, target_doctype=PLAN, target_name=plan.name, metadata={"todo": row.title})
	return get_plan(month)


@frappe.whitelist(methods=["GET"])
def plan_text(month: str | None = None) -> str:
	"""The month plan as text, for the 08:00 n8n report (which used to read
	OCTOBER_2026_SCHEDULE.md from GitHub). Empty when there is no plan."""
	require_platform_owner()
	plan = _plan_doc(month or getdate(today()).strftime("%Y-%m"))
	return rpt.plan_markdown(_plan_dict(plan)) if plan else ""


def _plan_dict(plan) -> dict:
	def rows(table, *fields):
		return [{"idx": r.idx, **{f: (str(r.get(f)) if r.get(f) is not None and f.endswith("date") else r.get(f)) for f in fields}} for r in table]
	return {
		"month": plan.month,
		"title": plan.title,
		"status": plan.status,
		"summary": plan.summary,
		"targets": rows(plan.targets, "metric", "target", "target_number", "metric_key", "notes"),
		"weeks": rows(plan.weeks, "label", "start_date", "end_date", "details"),
		"todos": rows(plan.todos, "due_date", "title", "owner_name", "status"),
		"day_notes": rows(plan.day_notes, "date", "note"),
	}


def _plan_months() -> list[str]:
	return [r.name for r in frappe.get_all(PLAN, fields=["name"], order_by="name desc", page_length=24)]


# --------------------------------------------------------------------------
# Schedule (rearrange) and n8n run times
# --------------------------------------------------------------------------
def _slots() -> list[dict]:
	return frappe.get_all(SLOT, fields=list(SLOT_FIELDS), order_by="start_time asc, sort_order asc")


@frappe.whitelist(methods=["GET"])
def list_slots() -> dict:
	require_platform_owner()
	slots = _slots()
	for s in slots:
		s["start_time"], s["end_time"] = rpt.hhmm(s.start_time), rpt.hhmm(s.end_time)
		s["valid_from"] = str(s.valid_from) if s.valid_from else None
		s["valid_to"] = str(s.valid_to) if s.valid_to else None
		s["days"] = rpt.slot_days(s)
	return {"slots": slots}


@frappe.whitelist(methods=["POST"])
def save_slot(slot, name: str | None = None) -> dict:
	require_platform_owner()
	data = _json(slot)
	doc = frappe.get_doc(SLOT, name) if name else frappe.new_doc(SLOT)
	before = {f: str(doc.get(f)) for f in SLOT_FIELDS if f != "name"} if name else None
	days = data.get("days")
	doc.update({
		"title": (data.get("title") or "").strip(),
		"kind": data.get("kind") or "task",
		"owner_name": (data.get("owner_name") or "").strip() or None,
		"start_time": data.get("start_time"),
		"end_time": data.get("end_time") or None,
		"days": ",".join(days) if isinstance(days, list) else days,
		"valid_from": data.get("valid_from") or None,
		"valid_to": data.get("valid_to") or None,
		"n8n_workflow_id": data.get("n8n_workflow_id") or None,
		"notes": (data.get("notes") or "").strip() or None,
		"sort_order": int(data.get("sort_order") or 0),
		"enabled": 1 if data.get("enabled", True) in (True, 1, "1", "true") else 0,
	})
	doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
	write_audit_event("marketing_slot_saved", target_doctype=SLOT, target_name=doc.name, before_state=before,
					  after_state={"title": doc.title, "start_time": str(doc.start_time), "days": doc.days})
	return list_slots()


@frappe.whitelist(methods=["POST"])
def delete_slot(name: str) -> dict:
	require_platform_owner()
	doc = frappe.get_doc(SLOT, name)
	write_audit_event("marketing_slot_deleted", target_doctype=SLOT, target_name=name,
					  before_state={"title": doc.title, "start_time": str(doc.start_time), "days": doc.days})
	doc.delete(ignore_permissions=True)
	return list_slots()


@frappe.whitelist(methods=["GET"])
def automation_schedules() -> dict:
	"""Every n8n workflow with its run time — editable ones (one trigger,
	one time of day) can be moved from the app."""
	require_platform_owner()
	client = _client()
	tz = None
	rows = []
	for w in _call(client.workflows):
		info = summarize(w)
		tz = tz or (w.get("settings") or {}).get("timezone")
		rows.append({
			"id": str(w.get("id")),
			"name": w.get("name"),
			"active": bool(w.get("active")),
			"timezone": (w.get("settings") or {}).get("timezone"),
			**{k: info.get(k) for k in ("editable", "time", "days", "text")},
		})
	rows.sort(key=lambda r: (not r["active"], not r["editable"], r.get("time") or "99", (r["name"] or "").lower()))
	return {"workflows": rows, "timezone": tz or get_system_timezone()}


@frappe.whitelist(methods=["POST"])
def set_automation_schedule(workflow_id: str, time: str, days) -> dict:
	"""Move one n8n workflow's run time. Only the schedule trigger's rule
	changes; the previous rule is kept in the audit log so it can be put
	back. Schedule slots linked to the workflow move with it."""
	require_platform_owner()
	try:
		parse_time(time)
		if isinstance(days, str) and days.strip().startswith("["):
			days = json.loads(days)
		day_list = clean_days(days)
	except (ScheduleError, ValueError) as exc:
		frappe.throw(_(str(exc)))
	client = _client()
	workflow = _call(lambda: client.workflow(str(workflow_id)))
	try:
		body, old_rule, new_rule = with_schedule(workflow, time, day_list)
	except ScheduleError as exc:
		frappe.throw(_(str(exc)))
	_call(lambda: client.update_workflow(str(workflow_id), body))
	write_audit_event(
		"marketing_automation_rescheduled",
		target_doctype=SETTINGS,
		target_name=SETTINGS,
		before_state={"rule": old_rule},
		after_state={"rule": new_rule},
		metadata={"workflow_id": str(workflow_id), "name": workflow.get("name"), "time": time, "days": day_list},
	)
	for slot in frappe.get_all(SLOT, filters={"n8n_workflow_id": str(workflow_id)}, pluck="name"):
		doc = frappe.get_doc(SLOT, slot)
		doc.start_time, doc.days = time, ",".join(day_list)
		doc.save(ignore_permissions=True)
	return automation_schedules()


# --------------------------------------------------------------------------
def _client() -> N8nClient:
	settings = frappe.get_cached_doc(SETTINGS)
	try:
		return N8nClient(settings.n8n_url, settings.get_password("n8n_api_key", raise_exception=False) or "")
	except N8nError as exc:
		frappe.throw(_(str(exc)))


def _call(fn):
	try:
		return fn()
	except N8nError as exc:
		frappe.throw(_(str(exc)), title=_("Marketing automation"))


def _json(value) -> dict:
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid data."))
	if not isinstance(value, dict):
		frappe.throw(_("Invalid data."))
	return value


def _pick(row: dict, *fields) -> dict:
	return {f: (row.get(f) if row.get(f) not in ("",) else None) for f in fields}
