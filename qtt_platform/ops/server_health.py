"""
QTT Admin → Servers: clean a report sent by a server's agent, decide the
server's health (ok / warning / critical / offline) with plain reasons,
decide when to alert (only when something changes), and thin the history
for charts.

Pure (no frappe): api/servers.py does the storing and HTTP.
"""

from __future__ import annotations

from datetime import datetime, timedelta

MAX_CONTAINERS = 80
MAX_PORTS = 120

DEFAULTS = {
	"disk_warn": 85.0,
	"disk_critical": 95.0,
	"mem_warn": 90.0,
	"load_warn_per_core": 2.0,
	"offline_after_minutes": 15,
}

#: Ports that should never be reachable from the internet (databases, admin
#: panels, raw app servers). Matches the 2026-10-10 VPS report.
RISKY_PUBLIC_PORTS = {
	3306: "MySQL/MariaDB", 5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB", 6333: "Qdrant", 6334: "Qdrant",
	9000: "MinIO / app server", 9001: "MinIO console", 5678: "n8n (no HTTPS)", 8000: "Frappe dev server",
	81: "Nginx Proxy Manager admin", 3000: "app server", 3001: "app server", 8081: "app server",
}


class ReportError(ValueError):
	"""The agent sent something unusable."""


def _num(value, lo=0.0, hi=1e15) -> float | None:
	try:
		n = float(value)
	except (TypeError, ValueError):
		return None
	return n if lo <= n <= hi else None


def _int(value, lo=0, hi=10**9) -> int | None:
	n = _num(value, lo, hi)
	return int(n) if n is not None else None


def clean_report(raw: dict) -> dict:
	"""Whitelist and bound every field the agent sends."""
	if not isinstance(raw, dict):
		raise ReportError("Report must be a JSON object.")
	disk = raw.get("disk") or {}
	mem = raw.get("memory") or {}
	load = raw.get("load") or []
	total, used = _num(disk.get("total_bytes")), _num(disk.get("used_bytes"))
	mtotal, mavail = _num(mem.get("total_bytes")), _num(mem.get("available_bytes"))
	if not total or used is None or not mtotal or mavail is None:
		raise ReportError("Report is missing disk or memory numbers.")
	containers = []
	for c in raw.get("containers") or []:
		if len(containers) >= MAX_CONTAINERS:
			break
		if isinstance(c, dict) and c.get("name"):
			containers.append({
				"name": str(c.get("name"))[:80],
				"image": str(c.get("image") or "")[:120],
				"state": str(c.get("state") or "")[:20].lower(),
				"status": str(c.get("status") or "")[:80],
			})
	ports = []
	for p in raw.get("ports") or []:
		if len(ports) >= MAX_PORTS:
			break
		if isinstance(p, dict) and _int(p.get("port"), 1, 65535):
			ports.append({"port": _int(p.get("port"), 1, 65535), "public": bool(p.get("public")), "process": str(p.get("process") or "")[:40]})
	return {
		"hostname": str(raw.get("hostname") or "")[:80],
		"os": str(raw.get("os") or "")[:80],
		"kernel": str(raw.get("kernel") or "")[:60],
		"agent_version": str(raw.get("agent_version") or "")[:20],
		"cpu_count": _int(raw.get("cpu_count"), 1, 1024) or 1,
		"load1": _num(load[0] if len(load) > 0 else None, 0, 10000) or 0.0,
		"load5": _num(load[1] if len(load) > 1 else None, 0, 10000) or 0.0,
		"load15": _num(load[2] if len(load) > 2 else None, 0, 10000) or 0.0,
		"uptime_seconds": _int(raw.get("uptime_seconds")) or 0,
		"disk_total_gb": round(total / 1e9, 1),
		"disk_used_gb": round(used / 1e9, 1),
		"disk_used_pct": round(used / total * 100, 1),
		"mem_total_gb": round(mtotal / 1e9, 1),
		"mem_used_pct": round((mtotal - mavail) / mtotal * 100, 1),
		"swap_used_pct": _num((raw.get("swap") or {}).get("used_pct"), 0, 100),
		"updates": _int(raw.get("updates")),
		"security_updates": _int(raw.get("security_updates")),
		"reboot_required": bool(raw.get("reboot_required")),
		"failed_services": [str(s)[:80] for s in (raw.get("failed_services") or [])[:30]],
		"containers": containers,
		"ports": ports,
		"firewall_active": raw.get("firewall_active") if isinstance(raw.get("firewall_active"), bool) else None,
		"ssh_password_login": raw.get("ssh_password_login") if isinstance(raw.get("ssh_password_login"), bool) else None,
		"ssh_failed_24h": _int(raw.get("ssh_failed_24h")),
		"hermes": clean_hermes(raw.get("hermes")),
		"backups": clean_backups(raw.get("backups")),
	}


def clean_backups(raw) -> list[dict]:
	"""The server's backup jobs as the agent read them (/var/lib/qtt-backup/*.json): name, whether the last run worked,
	when it finished (unix time), its size, a short detail, and how old it may get before it counts as missed."""
	out = []
	for b in (raw or [])[:10] if isinstance(raw, list) else []:
		if not isinstance(b, dict) or not b.get("name"):
			continue
		out.append({"name": str(b["name"])[:60], "ok": bool(b.get("ok")), "finished_at": _int(b.get("finished_at"), 0, 4 * 10**9),
					"size_bytes": _int(b.get("size_bytes"), 0, 10**15), "detail": str(b.get("detail") or "")[:160],
					"max_age_hours": _int(b.get("max_age_hours"), 1, 24 * 60) or 26})
	return out


def clean_hermes(raw) -> dict | None:
	"""Hermes Agent usage from the agent (counts only) — None when the server doesn't run Hermes."""
	if not isinstance(raw, dict):
		return None
	out = {k: _int(raw.get(k)) for k in ("allowed_users", "sessions", "users", "sessions_7d", "users_7d", "messages_7d")}
	out.update({
		"gateway_running": bool(raw.get("gateway_running")),
		"cost_usd": _num(raw.get("cost_usd"), 0, 1e6),
		"cost_usd_7d": _num(raw.get("cost_usd_7d"), 0, 1e6),
		"by_source_7d": {str(k)[:30]: _int(v) or 0 for k, v in list((raw.get("by_source_7d") or {}).items())[:6]}
		if isinstance(raw.get("by_source_7d"), dict) else {},
		"error": str(raw["error"])[:120] if raw.get("error") else None,
	})
	return out


def evaluate(report: dict | None, *, last_report_at: datetime | None, now: datetime, limits: dict | None = None) -> dict:
	"""{status, problems: [{level, text}], notices: [...]} for one server."""
	lim = {**DEFAULTS, **{k: v for k, v in (limits or {}).items() if v}}
	if not report or not last_report_at:
		return {"status": "offline", "problems": [{"level": "critical", "text": "No report received yet."}], "notices": []}
	if now - last_report_at > timedelta(minutes=lim["offline_after_minutes"]):
		minutes = int((now - last_report_at).total_seconds() // 60)
		return {"status": "offline", "problems": [{"level": "critical", "text": f"No report for {minutes} minutes."}], "notices": []}

	problems, notices = [], []
	disk = report.get("disk_used_pct") or 0
	if disk >= lim["disk_critical"]:
		problems.append({"level": "critical", "text": f"Disk {disk:.0f}% full."})
	elif disk >= lim["disk_warn"]:
		problems.append({"level": "warning", "text": f"Disk {disk:.0f}% full."})
	mem = report.get("mem_used_pct") or 0
	if mem >= lim["mem_warn"]:
		problems.append({"level": "warning", "text": f"Memory {mem:.0f}% used."})
	if (report.get("swap_used_pct") or 0) >= 80:
		problems.append({"level": "warning", "text": f"Swap {report['swap_used_pct']:.0f}% used (memory is short)."})
	cores = report.get("cpu_count") or 1
	if (report.get("load5") or 0) > cores * lim["load_warn_per_core"]:
		problems.append({"level": "warning", "text": f"High load ({report['load5']:.1f} on {cores} cores)."})
	down = [c["name"] for c in report.get("containers") or [] if c.get("state") not in ("running", "")]
	if down:
		problems.append({"level": "critical", "text": f"Containers not running: {', '.join(down[:6])}."})
	if report.get("failed_services"):
		problems.append({"level": "warning", "text": f"Failed services: {', '.join(report['failed_services'][:6])}."})

	risky = sorted({p["port"] for p in report.get("ports") or [] if p.get("public") and p["port"] in RISKY_PUBLIC_PORTS})
	if risky:
		notices.append(f"Open to the internet: {', '.join(f'{p} ({RISKY_PUBLIC_PORTS[p]})' for p in risky)}.")
	if report.get("reboot_required"):
		notices.append("Reboot needed for updates.")
	if report.get("security_updates"):
		notices.append(f"{report['security_updates']} security updates waiting.")
	if report.get("firewall_active") is False:
		notices.append("Firewall is off.")
	if report.get("ssh_password_login"):
		notices.append("SSH password login is on.")
	if (report.get("ssh_failed_24h") or 0) > 1000:
		notices.append(f"{report['ssh_failed_24h']} failed SSH logins in 24 h.")
	h = report.get("hermes")
	if h and not h.get("gateway_running"):
		notices.append("Hermes gateway (Telegram) is not running.")
	if h and h.get("error"):
		notices.append("Hermes usage couldn't be read (after a Hermes update?).")

	for b in report.get("backups") or []:
		age_h = (now.timestamp() - b["finished_at"]) / 3600 if b.get("finished_at") else None
		if not b.get("ok"):
			problems.append({"level": "warning", "text": f"Backup failed: {b['name']}" + (f" — {b['detail']}" if b.get("detail") else "") + "."})
		elif age_h is None or age_h > b.get("max_age_hours", 26):
			problems.append({"level": "warning", "text": f"Backup missed: {b['name']} — last one {int(age_h)} h ago." if age_h is not None
							 else f"Backup missed: {b['name']}."})

	status = "critical" if any(p["level"] == "critical" for p in problems) else "warning" if problems else "ok"
	return {"status": status, "problems": problems, "notices": notices}


def alert_for_change(previous: str | None, current: str, title: str, problems: list[dict]) -> str | None:
	"""Slack text when the status changes (not on every report)."""
	if previous == current or (previous is None and current == "ok"):
		return None
	reasons = " ".join(p["text"] for p in problems)
	if current == "ok":
		return f"✅ {title} is healthy again."
	icon = {"offline": "🔴", "critical": "🔴", "warning": "🟠"}.get(current, "⚪")
	return f"{icon} {title}: {current}. {reasons}".strip()


def thin(points: list[dict], max_points: int = 200) -> list[dict]:
	"""Keep at most max_points evenly spread (charts don't need every 5-min report)."""
	if len(points) <= max_points:
		return points
	step = len(points) / max_points
	return [points[int(i * step)] for i in range(max_points - 1)] + [points[-1]]
