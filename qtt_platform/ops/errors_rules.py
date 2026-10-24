"""
QTT Admin › Servers › Errors — pure rules (tests/test_errors_rules.py).

Crashes and errors from the QTT OS app (phone and web) and the Frappe server go to QTT's own error monitoring (GlitchTip,
Sentry-compatible, self-hosted at errors.queentouchtech.in on QTT-AI-OS). Frappe reads the unresolved issues every 10
minutes: new ones (and old ones that suddenly happen a lot) are posted to the ops Telegram; QTT Admin lists them.
"""

from datetime import datetime

PROJECTS = {"qtt-os-app": "App", "qtt-os-server-frappe": "Server"}
SPIKE = 50  # an old error seen this many more times since the last look is worth a message again


def _when(v) -> str | None:
	return str(v)[:19].replace("T", " ") if v else None


def issue_out(raw: dict, base: str, org: str) -> dict:
	"""One GlitchTip issue in the app's words."""
	project = (raw.get("project") or {}).get("slug") or ""
	try:
		count = int(raw.get("count") or 0)
	except (TypeError, ValueError):
		count = 0
	return {"id": str(raw.get("id") or ""), "title": str(raw.get("title") or "")[:300], "where": str(raw.get("culprit") or "")[:200],
			"level": raw.get("level") or "error", "count": count, "users": int(raw.get("userCount") or 0),
			"first_seen": _when(raw.get("firstSeen")), "last_seen": _when(raw.get("lastSeen")), "short_id": raw.get("shortId") or "",
			"source": PROJECTS.get(project, project or "—"),
			"url": f"{base.rstrip('/')}/{org}/issues/{raw.get('id')}" if raw.get("id") else base}


def to_alert(issues: list[dict], since: datetime | None, counts_before: dict[str, int]) -> list[tuple[str, dict]]:
	"""Which issues deserve a message: ('new', issue) first seen after `since`; ('again', issue) seen SPIKE+ more times
	since the last look. Nothing on the very first look (no `since`) — no flood when monitoring starts."""
	if since is None:
		return []
	out = []
	for i in issues:
		first = datetime.fromisoformat(i["first_seen"]) if i.get("first_seen") else None
		if first and first > since:
			out.append(("new", i))
		elif i["count"] - counts_before.get(i["id"], i["count"]) >= SPIKE:
			out.append(("again", i))
	return out


def alert_text(kind: str, i: dict) -> str:
	head = "New error" if kind == "new" else "Error happening a lot"
	users = f" · {i['users']} people" if i.get("users") else ""
	return f"{head} ({i['source']}): {i['title']}\n{i['count']}× so far{users} · {i['url']}"


def summary(issues: list[dict]) -> dict:
	return {"open": len(issues), "app": sum(1 for i in issues if i["source"] == "App"),
			"server": sum(1 for i in issues if i["source"] == "Server"), "events": sum(i["count"] for i in issues)}
