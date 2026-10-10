"""
Read and change the run time of an n8n workflow's Schedule Trigger.

Only the simple, common shape is editable: ONE schedule trigger that runs
at one time of day on chosen weekdays. Anything else (every N hours,
several rules, several triggers, the legacy Cron node) is shown read-only
and must be changed in n8n itself — the console never guesses.

Pure (no frappe, no HTTP).
"""

from __future__ import annotations

import re

SCHEDULE_TYPE = "n8n-nodes-base.scheduleTrigger"
LEGACY_CRON_TYPE = "n8n-nodes-base.cron"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_CRON_DOW = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_DOW_NAME = {v: k for k, v in _CRON_DOW.items()}
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

#: Node keys the n8n public API accepts back on PUT (same set the
#: marketing scripts use).
NODE_KEYS = (
	"id", "name", "type", "typeVersion", "position", "parameters", "credentials", "disabled", "notes", "notesInFlow",
	"retryOnFail", "maxTries", "waitBetweenTries", "alwaysOutputData", "executeOnce", "onError", "continueOnFail", "webhookId",
)


class ScheduleError(ValueError):
	"""Message is shown to the platform owner as-is."""


def schedule_nodes(workflow: dict) -> list[dict]:
	return [n for n in workflow.get("nodes") or [] if n.get("type") in (SCHEDULE_TYPE, LEGACY_CRON_TYPE) and not n.get("disabled")]


def parse_time(value: str) -> tuple[int, int]:
	m = _TIME.match(str(value or "").strip())
	if not m:
		raise ScheduleError("Time must look like 08:30 (24-hour).")
	return int(m.group(1)), int(m.group(2))


def clean_days(days) -> list[str]:
	if isinstance(days, str):
		days = [d.strip() for d in days.split(",")]
	picked = [d.lower()[:3] for d in days or [] if str(d).strip()]
	unknown = [d for d in picked if d not in DAYS]
	if unknown:
		raise ScheduleError(f"Unknown day: {', '.join(unknown)}.")
	if not picked:
		raise ScheduleError("Pick at least one day.")
	return [d for d in DAYS if d in picked]


def _dow_field(days: list[str]) -> str:
	if len(days) == 7:
		return "*"
	nums = sorted(_CRON_DOW[d] for d in days)
	# compress runs: 1,2,3,4,5 -> 1-5
	parts, start, prev = [], nums[0], nums[0]
	for n in nums[1:] + [None]:
		if n is not None and n == prev + 1:
			prev = n
			continue
		parts.append(str(start) if start == prev else f"{start}-{prev}")
		if n is not None:
			start = prev = n
	return ",".join(parts)


def cron_for(time: str, days) -> str:
	hour, minute = parse_time(time)
	return f"{minute} {hour} * * {_dow_field(clean_days(days))}"


def _parse_dow(field: str) -> list[str] | None:
	if field in ("*", "?"):
		return list(DAYS)
	out = set()
	for part in field.split(","):
		if re.fullmatch(r"\d", part):
			n = int(part) % 7
			out.add(_DOW_NAME[n])
		elif re.fullmatch(r"\d-\d", part):
			a, b = (int(x) for x in part.split("-"))
			if a > b:
				return None
			out.update(_DOW_NAME[n % 7] for n in range(a, b + 1))
		elif part.lower()[:3] in _CRON_DOW and len(part) == 3:
			out.add(part.lower())
		else:
			return None
	return [d for d in DAYS if d in out]


def _from_cron(expression: str) -> dict | None:
	parts = str(expression or "").split()
	if len(parts) == 6:  # n8n allows a leading seconds field
		if parts[0] != "0":
			return None
		parts = parts[1:]
	if len(parts) != 5:
		return None
	minute, hour, dom, month, dow = parts
	if not (minute.isdigit() and hour.isdigit() and dom in ("*", "?") and month == "*"):
		return None
	days = _parse_dow(dow)
	if days is None:
		return None
	return {"time": f"{int(hour):02d}:{int(minute):02d}", "days": days}


def summarize(workflow: dict) -> dict:
	"""{editable, time, days, text, node} for the workflow's schedule.
	text is a short human description for anything not editable."""
	nodes = schedule_nodes(workflow)
	if not nodes:
		return {"editable": False, "text": "Not scheduled (runs on a webhook or by hand)", "node": None}
	if len(nodes) > 1:
		return {"editable": False, "text": f"{len(nodes)} schedule triggers — change in n8n", "node": None}
	node = nodes[0]
	if node.get("type") == LEGACY_CRON_TYPE:
		return {"editable": False, "text": "Legacy Cron node — change in n8n", "node": node.get("name")}

	rules = ((node.get("parameters") or {}).get("rule") or {}).get("interval") or [{}]
	if len(rules) != 1:
		return {"editable": False, "text": f"{len(rules)} schedule rules — change in n8n", "node": node.get("name")}
	rule = rules[0]
	field = rule.get("field") or "days"
	hour, minute = int(rule.get("triggerAtHour") or 0), int(rule.get("triggerAtMinute") or 0)
	parsed = None
	if field == "cronExpression":
		parsed = _from_cron(rule.get("expression"))
		if parsed is None:
			return {"editable": False, "text": f"Cron {rule.get('expression')} — change in n8n", "node": node.get("name")}
	elif field == "days" and int(rule.get("daysInterval") or 1) == 1:
		parsed = {"time": f"{hour:02d}:{minute:02d}", "days": list(DAYS)}
	elif field == "weeks" and int(rule.get("weeksInterval") or 1) == 1:
		picked = [_DOW_NAME[int(d) % 7] for d in rule.get("triggerAtDay") or [0]]
		parsed = {"time": f"{hour:02d}:{minute:02d}", "days": [d for d in DAYS if d in picked]}
	else:
		every = rule.get(f"{field}Interval") or 1
		return {"editable": False, "text": f"Every {every} {field} — change in n8n", "node": node.get("name")}
	return {"editable": True, "node": node.get("name"), **parsed}


def with_schedule(workflow: dict, time: str, days) -> tuple[dict, dict, dict]:
	"""(PUT body, old rule, new rule). Refuses anything summarize() calls
	read-only. Only the one trigger node's rule changes."""
	info = summarize(workflow)
	if not info["editable"]:
		raise ScheduleError(f"This workflow's schedule can't be changed here: {info['text']}.")
	expression = cron_for(time, days)
	nodes = []
	old_rule = new_rule = None
	for n in workflow.get("nodes") or []:
		n = {k: v for k, v in n.items() if k in NODE_KEYS}
		if n.get("name") == info["node"]:
			params = dict(n.get("parameters") or {})
			old_rule = params.get("rule")
			new_rule = {"interval": [{"field": "cronExpression", "expression": expression}]}
			params["rule"] = new_rule
			n["parameters"] = params
		nodes.append(n)
	body = {
		"name": workflow.get("name"),
		"nodes": nodes,
		"connections": workflow.get("connections") or {},
		"settings": {k: v for k, v in (workflow.get("settings") or {}).items() if k in ("executionOrder", "timezone")},
	}
	return body, old_rule, new_rule
