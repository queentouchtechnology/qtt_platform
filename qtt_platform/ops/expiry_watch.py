"""
QTT Admin › expiry register and the Monday ops report. Pure (no frappe): api/servers.py stores, sends and serves.

Expiry register (Desk › QTT Expiry Item, added 13 Nov 2026): anything that stops working on a date — access tokens,
API keys, domains at registrars the provider sync can't read, subscriptions, cards. On 12 Nov the daily report had
been failing for two weeks because a GitHub token expired unannounced. Telegram at 30, 14, 7, 3, 1 days, on the
day and once expired — one message per step, not every day; renewing (a later date) ends it.

Monday ops report: one message with everything slow-moving (orange servers, disks filling, certificates, expiries,
n8n failures, background jobs), so a warning can't sit unseen for weeks among the 5-minute alerts.
"""

from __future__ import annotations

from datetime import date

STEPS = (30, 14, 7, 3, 1, 0)
KINDS = ("Access token", "API key", "Domain", "Certificate", "Subscription", "Payment card", "Other")


def days_left(expires_on: date, today: date) -> int:
	return (expires_on - today).days


def bucket(days: int) -> int | None:
	"""The reminder step `days` falls in: 30, 14, 7, 3, 1, 0, -1 (expired) or None (more than 30 days)."""
	if days < 0:
		return -1
	steps = [s for s in STEPS if days <= s]
	return min(steps) if steps else None


def level(days: int) -> str:
	"""ok | warning | critical — for Needs attention and the app."""
	if days <= 3:
		return "critical"
	return "warning" if days <= 14 else "ok"


def step(prev_step: int | None, days: int) -> tuple[int | None, bool]:
	"""(new step, send a reminder now?). A later date (renewed) moves back up and goes quiet."""
	new = bucket(days)
	if new is None:
		return None, False
	return new, prev_step is None or new < prev_step


def when(days: int) -> str:
	if days < 0:
		return f"EXPIRED {-days} day{'s' if days != -1 else ''} ago"
	if days == 0:
		return "expires TODAY"
	return f"expires in {days} day{'s' if days != 1 else ''}"


def reminder(*, title: str, kind: str | None, days: int, used_by: str | None, renew_how: str | None) -> str:
	icon = "🔴" if days <= 3 else "🟠" if days <= 14 else "🔔"
	lines = [f"{icon} {kind or 'Expiry'}: {title} {when(days)}."]
	if used_by:
		lines.append(f"Used by: {used_by.strip()[:300]}")
	if renew_how:
		lines.append(f"Renew: {renew_how.strip()[:300]}")
	return "\n".join(lines)


def problems(items: list[dict], today: date) -> list[dict]:
	"""Watched items within 14 days, shaped like a server item for QTT Admin's Needs attention (no app update)."""
	out = []
	for i in items:
		if not i.get("watch") or not i.get("expires_on"):
			continue
		d = days_left(i["expires_on"], today)
		lvl = level(d)
		if lvl != "ok":
			out.append({"key": None, "title": i["title"], "status": lvl, "problems": f"{i.get('kind') or 'Expiry'} {when(d)}."})
	return out


# --------------------------------------------------------------------------
# Monday ops report
# --------------------------------------------------------------------------
def digest(*, today: date, servers: list[dict], certs: list[dict], expiries: list[dict], domains: list[dict],
		   n8n: dict, jobs_age_minutes: int | None, limit: int = 3800) -> str:
	"""Plain text for Telegram (under its 4096-character limit) and the app.

	servers: [{title, status, problems, disk_pct, forecast_days}]   certs: [{host, days, error}]
	expiries: [{title, kind, days}]   domains: [{domain, days}]   n8n: {failing: [(name, runs)], error}
	"""
	out = [f"📋 QTT weekly ops report — {today:%a %d %b %Y}"]
	attention = 0

	out.append("\nSERVERS")
	for s in servers:
		icon = {"ok": "🟢", "warning": "🟠", "critical": "🔴", "offline": "🔴"}.get(s["status"], "⚪")
		bits = [f"disk {s['disk_pct']:.0f}%"] if s.get("disk_pct") is not None else []
		if s.get("forecast_days") is not None:
			bits.append(f"full in ~{int(s['forecast_days'])} days")
		out.append(f"{icon} {s['title']}" + (f" — {', '.join(bits)}" if bits else ""))
		if s["status"] != "ok":
			attention += 1
			if s.get("problems"):
				out.append(f"   {s['problems'][:240]}")

	near = sorted([c for c in certs if c.get("error") or (c.get("days") is not None and c["days"] <= 30)],
				  key=lambda c: -1 if c.get("error") else c["days"])
	out.append("\nCERTIFICATES")
	if not certs:
		out.append("— none watched")
	elif not near:
		low = min((c["days"] for c in certs if c.get("days") is not None), default=None)
		out.append(f"✅ {len(certs)} watched, all fine" + (f" (nearest renewal in {low} days)" if low is not None else ""))
	else:
		for c in near[:8]:
			if c.get("error"):
				attention += 1
				out.append(f"🔴 {c['host']} — can't be read: {c['error'][:120]}")
			else:
				# Renewal normally happens at 30 days left; under 21 means it hasn't.
				icon = "🔴" if c["days"] <= 7 else "🟠" if c["days"] <= 21 else "🔁"
				attention += c["days"] <= 21
				out.append(f"{icon} {c['host']} — {c['days']} days left" + (" (should renew this week)" if c["days"] > 21 else ""))
		if len(near) > 8:
			out.append(f"   …and {len(near) - 8} more")

	soon = sorted([e for e in expiries if e["days"] <= 30], key=lambda e: e["days"])
	soon_domains = sorted([d for d in domains if d["days"] is not None and d["days"] <= 30], key=lambda d: d["days"])
	out.append("\nEXPIRING (next 30 days)")
	if not soon and not soon_domains:
		out.append("✅ nothing")
	for e in soon:
		attention += 1
		out.append(f"{'🔴' if e['days'] <= 3 else '🟠'} {e.get('kind') or 'Expiry'}: {e['title']} — {when(e['days'])}")
	for d in soon_domains:
		attention += 1
		out.append(f"{'🔴' if d['days'] <= 7 else '🟠'} Domain {d['domain']} — {when(d['days'])}")

	out.append("\nN8N WORKFLOWS (last 7 days)")
	if n8n.get("error"):
		out.append(f"⚪ couldn't check: {n8n['error'][:120]}")
	elif not n8n.get("failing"):
		out.append("✅ no failed runs")
	else:
		for name, runs in n8n["failing"][:8]:
			out.append(f"🟠 {name} — {runs} failed run{'s' if runs != 1 else ''}")
		attention += 1

	out.append("\nBACKGROUND JOBS")
	if jobs_age_minutes is None:
		out.append("⚪ couldn't check")
	elif jobs_age_minutes > 15:
		attention += 1
		out.append(f"🔴 no scheduled job for {jobs_age_minutes} minutes")
	else:
		out.append("✅ running")

	out.insert(1, "✅ All quiet — nothing needs you this week." if not attention else
			   f"👀 {attention} thing{'s' if attention != 1 else ''} to look at.")
	text = "\n".join(out)
	return text if len(text) <= limit else text[: limit - 20].rsplit("\n", 1)[0] + "\n…(shortened)"
