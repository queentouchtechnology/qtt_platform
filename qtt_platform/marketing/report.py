"""
QTT Admin → Marketing dashboard: the day report (yesterday / today), the
day's schedule with what actually ran, month progress against targets, and
the plan rendered as text for the 08:00 n8n report.

Pure (no frappe): api/marketing_dashboard.py gathers the rows (CRM counts,
n8n runs, schedule slots, plan) and passes them in, so all the rules here
are unit-tested.
"""

from __future__ import annotations

from datetime import date, datetime, time

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
METRIC_KEYS = ("leads", "emails_sent", "email_replies", "calls", "applications")


def _d(value) -> date | None:
	if value in (None, ""):
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def hhmm(value) -> str | None:
	"""'8:00:00' / '08:00' / time / timedelta → '08:00'."""
	if value in (None, ""):
		return None
	if isinstance(value, time):
		return value.strftime("%H:%M")
	if hasattr(value, "total_seconds"):  # timedelta from the DB
		minutes = int(value.total_seconds() // 60)
		return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"
	parts = str(value).split(":")
	return f"{int(parts[0]):02d}:{int(parts[1]) if len(parts) > 1 else 0:02d}"


def slot_days(slot: dict) -> list[str]:
	raw = slot.get("days")
	items = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
	return [d.strip().lower()[:3] for d in items if d.strip()]


def slots_for_day(slots: list[dict], day: date) -> list[dict]:
	key = DAY_KEYS[day.weekday()]
	out = []
	for s in slots:
		if not s.get("enabled", 1):
			continue
		if key not in slot_days(s):
			continue
		start, end = _d(s.get("valid_from")), _d(s.get("valid_to"))
		if (start and day < start) or (end and day > end):
			continue
		out.append(s)
	return sorted(out, key=lambda s: (hhmm(s.get("start_time")) or "", s.get("sort_order") or 0, s.get("title") or ""))


def _runs_by_workflow(executions: list[dict]) -> dict[str, dict]:
	runs: dict[str, dict] = {}
	for ex in executions:
		wf = str(ex.get("workflowId") or "")
		if not wf:
			continue
		r = runs.setdefault(wf, {"runs": 0, "failed": 0, "last_status": None, "last_at": None})
		r["runs"] += 1
		status = ex.get("status") or ("success" if ex.get("finished") else "failed")
		failed = status in ("error", "crashed", "failed")
		r["failed"] += 1 if failed else 0
		at = str(ex.get("startedAt") or "")
		if r["last_at"] is None or at > r["last_at"]:
			r["last_at"], r["last_status"] = at, "failed" if failed else status
	return runs


def slot_status(slot: dict, runs: dict[str, dict], *, day: date, now: datetime) -> str:
	"""done | failed | upcoming | now | missed | past.
	Automation slots linked to a workflow report what n8n actually did."""
	start, end = hhmm(slot.get("start_time")), hhmm(slot.get("end_time"))
	today = now.date()
	clock = now.strftime("%H:%M")
	wf = str(slot.get("n8n_workflow_id") or "")
	if wf:
		r = runs.get(wf)
		if r and r["runs"]:
			return "failed" if r["last_status"] == "failed" else "done"
		if day > today or (day == today and start and clock < start):
			return "upcoming"
		return "missed"
	if day < today:
		return "past"
	if day > today:
		return "upcoming"
	if start and clock < start:
		return "upcoming"
	if end and clock < end:
		return "now"
	if not end and start and clock[:2] == start[:2]:
		return "now"
	return "past"


def day_report(*, day: date, now: datetime, slots: list[dict], workflows: list[dict], executions: list[dict],
			   crm: dict, notes: list[str], week: dict | None = None) -> dict:
	"""Everything the Today / Yesterday screens show for one day."""
	runs = _runs_by_workflow(executions)
	names = {str(w.get("id")): w.get("name") for w in workflows}
	schedule = []
	for s in slots_for_day(slots, day):
		schedule.append({
			"name": s.get("name"),
			"title": s.get("title"),
			"kind": s.get("kind") or "task",
			"owner": s.get("owner_name"),
			"start": hhmm(s.get("start_time")),
			"end": hhmm(s.get("end_time")),
			"notes": s.get("notes"),
			"workflow_id": s.get("n8n_workflow_id"),
			"status": slot_status(s, runs, day=day, now=now),
		})
	automations = sorted(
		(
			{"id": wf, "name": names.get(wf) or wf, **r}
			for wf, r in runs.items()
		),
		key=lambda a: (-a["failed"], (a["name"] or "").lower()),
	)
	return {
		"date": day.isoformat(),
		"weekday": DAY_KEYS[day.weekday()],
		"is_today": day == now.date(),
		"generated_at": now.isoformat(timespec="minutes"),
		"numbers": {k: crm.get(k, {"count": 0}) for k in ("leads", "calls", "emails_sent", "email_replies", "applications")},
		"calls_due": crm.get("calls_due"),
		"automations": automations,
		"automation_totals": {
			"runs": sum(a["runs"] for a in automations),
			"failed": sum(a["failed"] for a in automations),
		},
		"schedule": schedule,
		"notes": notes,
		"week": week,
	}


def current_week(weeks: list[dict], day: date) -> dict | None:
	"""The week containing `day`, else the next one coming."""
	ordered = sorted((w for w in weeks if _d(w.get("start_date"))), key=lambda w: _d(w.get("start_date")))
	for w in ordered:
		if _d(w["start_date"]) <= day <= (_d(w.get("end_date")) or _d(w["start_date"])):
			return _week_out(w)
	upcoming = [w for w in ordered if _d(w["start_date"]) > day]
	return _week_out(upcoming[0]) if upcoming else None


def _week_out(w: dict) -> dict:
	return {
		"label": w.get("label"),
		"start_date": str(_d(w.get("start_date"))),
		"end_date": str(_d(w.get("end_date"))) if w.get("end_date") else None,
		"items": [line.strip(" -•\t") for line in str(w.get("details") or "").splitlines() if line.strip(" -•\t")],
	}


def progress(targets: list[dict], actuals: dict[str, int], *, day: date, month_days: int) -> list[dict]:
	"""Targets with month-to-date actuals (for metric-linked ones) and
	whether they're on pace for the day of the month."""
	out = []
	for t in targets:
		key = t.get("metric_key") or None
		number = float(t.get("target_number") or 0) or None
		actual = actuals.get(key) if key else None
		pct = round(actual / number * 100) if (actual is not None and number) else None
		expected = round(number * day.day / month_days) if number else None
		out.append({
			"metric": t.get("metric"),
			"target": t.get("target"),
			"target_number": number,
			"metric_key": key,
			"actual": actual,
			"percent": pct,
			"on_pace": (actual >= expected) if (actual is not None and expected is not None) else None,
			"notes": t.get("notes"),
		})
	return out


def plan_markdown(plan: dict) -> str:
	"""The plan as text in the same shape the 08:00 report already parses
	('## Week by week' + '### Week N — Mon 5 – Sun 11 Oct …')."""
	def pretty(value) -> str:
		d = _d(value)
		return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}" if d else ""

	lines = [f"# {plan.get('title') or 'Marketing plan ' + str(plan.get('month'))}", ""]
	if plan.get("summary"):
		lines += [str(plan["summary"]).strip(), ""]
	lines += ["## Week by week"]
	for w in sorted(plan.get("weeks") or [], key=lambda w: str(w.get("start_date") or "")):
		label = str(w.get("label") or "Week")
		head, _, rest = label.partition(" (")
		suffix = f" ({rest}" if rest else ""
		lines.append(f"### {head} — {pretty(w.get('start_date'))} – {pretty(w.get('end_date'))}{suffix}")
		for item in _week_out(w)["items"]:
			lines.append(f"- {item}")
		lines.append("")
	targets = plan.get("targets") or []
	if targets:
		lines += ["## Targets", "| Metric | Target |", "|---|---|"]
		lines += [f"| {t.get('metric')} | {t.get('target')} |" for t in targets]
		lines.append("")
	todos = plan.get("todos") or []
	if todos:
		lines += ["## To-dos", "| By | To-do | Status |", "|---|---|---|"]
		lines += [f"| {pretty(t.get('due_date')) or 'Any time'} | {t.get('title')} | {t.get('status') or 'open'} |" for t in todos]
		lines.append("")
	notes = plan.get("day_notes") or []
	if notes:
		lines += ["## Special days"] + [f"- {pretty(n.get('date'))}: {n.get('note')}" for n in notes] + [""]
	return "\n".join(lines).rstrip() + "\n"
