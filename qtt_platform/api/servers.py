"""
QTT Admin → Servers: status, meters and history of QTT's own servers.

Each server runs a small read-only agent (public/ops/qtt-server-agent.py)
from its own cron every 5 minutes and POSTs to `ingest` with its key and
secret token. Push, not pull: Frappe holds no SSH keys, so a compromised
Frappe can't reach the servers. Platform Owners see everything in the app;
a status change can post to Slack.
"""

import json
import secrets
from datetime import timedelta

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, get_url, now_datetime

from qtt_platform.audit import write_audit_event
from qtt_platform.ops import server_health as health
from qtt_platform.tenant.guards import require_platform_owner

SERVER = "QTT Server"
REPORT = "QTT Server Report"
SETTINGS = "QTT Ops Settings"
MAX_BODY = 256 * 1024
MIN_INTERVAL_SECONDS = 60
KEEP_DAYS = 30
AGENT_PATH = "/assets/qtt_platform/ops/qtt-server-agent.py"

# Known servers (docs/ops/vps-report-2026-10-10.md). Created once; edit in the app or Desk.
KNOWN = [
	("frappe", "Frappe (app.queentouchtech.in)", "185.217.127.94", "Contabo vmi2748666", "Frappe bench in Docker: app.queentouchtech.in, learn.truthofbible.org; Nginx Proxy Manager; Uptime Kuma"),
	("n8n", "n8n · Chatwoot · Nextcloud", "173.249.7.188", "Contabo vmi2682166", "n8n, Chatwoot (watz), Nextcloud, Discourse, MinIO, Qdrant, PostgreSQL, MariaDB"),
	("ai-os", "QTT-AI-OS", "31.220.83.224", "Contabo vmi3592353", "Marketing automation server (empty on 2026-10-10)"),
	("cloudpanel", "Cloud Panel", "169.58.212.154", "Contabo vmi3523687", "CloudPanel hosting"),
]


# --------------------------------------------------------------------------
# Agent → Frappe (no login: the server's token is the permission)
# --------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["POST"])
def ingest():
	key = (frappe.get_request_header("X-QTT-Server") or "").strip()
	token = (frappe.get_request_header("X-QTT-Token") or "").strip()
	body = frappe.request.get_data(cache=False) if frappe.request else b""
	if not key or not token or not frappe.db.exists(SERVER, key):
		frappe.throw(_("Unknown server."), frappe.AuthenticationError)
	server = frappe.get_doc(SERVER, key)
	expected = server.get_password("report_token", raise_exception=False)
	if not expected or not secrets.compare_digest(expected, token) or not server.enabled:
		frappe.throw(_("Not allowed."), frappe.AuthenticationError)
	if len(body or b"") > MAX_BODY:
		frappe.throw(_("Report too large."))
	if server.last_report_at and (now_datetime() - get_datetime(server.last_report_at)).total_seconds() < MIN_INTERVAL_SECONDS:
		return {"ok": True, "skipped": "too soon"}
	try:
		clean = health.clean_report(json.loads(body or b"{}"))
	except (ValueError, health.ReportError) as exc:
		frappe.throw(_("Bad report: {0}").format(str(exc)))

	report = frappe.get_doc({
		"doctype": REPORT,
		"server": key,
		"reported_at": now_datetime(),
		**{f: clean[f] for f in ("disk_used_pct", "mem_used_pct", "load5", "disk_total_gb", "disk_used_gb", "mem_total_gb", "cpu_count", "uptime_seconds")},
		"data": json.dumps(clean),
	}).insert(ignore_permissions=True)
	_apply_status(server, clean, report_name=report.name, reported_at=report.reported_at)
	return {"ok": True}


# --------------------------------------------------------------------------
# App (Platform Owners)
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_servers() -> dict:
	require_platform_owner()
	_seed_known()
	out = []
	for s in frappe.get_all(SERVER, fields=["name", "title", "ip_address", "provider_id", "purpose", "enabled", "status", "last_report_at", "last_report"],
							order_by="title asc"):
		latest = _latest(s.last_report)
		ev = health.evaluate(latest, last_report_at=get_datetime(s.last_report_at) if s.last_report_at else None, now=now_datetime(), limits=_limits())
		out.append({
			"key": s.name, "title": s.title, "ip": s.ip_address, "provider_id": s.provider_id, "purpose": s.purpose,
			"enabled": bool(s.enabled), "status": ev["status"] if s.enabled else "disabled",
			"last_report_at": str(s.last_report_at) if s.last_report_at else None,
			"problems": ev["problems"], "notices": ev["notices"], "latest": latest,
		})
	counts = {}
	for s in out:
		counts[s["status"]] = counts.get(s["status"], 0) + 1
	return {"servers": out, "counts": counts}


@frappe.whitelist(methods=["GET"])
def server_detail(key: str, days: int = 7) -> dict:
	require_platform_owner()
	days = max(1, min(int(days or 7), KEEP_DAYS))
	server = frappe.get_doc(SERVER, key)
	rows = frappe.get_all(
		REPORT,
		filters={"server": key, "reported_at": [">=", now_datetime() - timedelta(days=days)]},
		fields=["reported_at", "disk_used_pct", "mem_used_pct", "load5", "cpu_count"],
		order_by="reported_at asc",
		page_length=days * 24 * 12 + 10,
	)
	history = [{"t": str(r.reported_at), "disk": r.disk_used_pct, "mem": r.mem_used_pct, "load": r.load5, "cores": r.cpu_count} for r in rows]
	latest = _latest(server.last_report)
	ev = health.evaluate(latest, last_report_at=get_datetime(server.last_report_at) if server.last_report_at else None, now=now_datetime(), limits=_limits())
	return {
		"key": server.name, "title": server.title, "ip": server.ip_address, "provider_id": server.provider_id, "purpose": server.purpose,
		"enabled": bool(server.enabled), "status": ev["status"], "problems": ev["problems"], "notices": ev["notices"],
		"last_report_at": str(server.last_report_at) if server.last_report_at else None,
		"latest": latest, "history": health.thin(history, 240), "days": days,
	}


@frappe.whitelist(methods=["POST"])
def save_server(key: str, title: str, ip_address: str | None = None, purpose: str | None = None, provider_id: str | None = None, enabled=1) -> dict:
	"""Add (new key) or edit a server."""
	require_platform_owner()
	key = (key or "").strip().lower()
	if not key or not all(ch.isalnum() or ch in "-_" for ch in key) or len(key) > 30:
		frappe.throw(_("The key uses letters, digits, - or _, e.g. frappe or n8n."))
	doc = frappe.get_doc(SERVER, key) if frappe.db.exists(SERVER, key) else frappe.new_doc(SERVER)
	doc.update({"server_key": key, "title": (title or key).strip()[:80], "ip_address": (ip_address or "").strip()[:60] or None,
				"purpose": (purpose or "").strip()[:500] or None, "provider_id": (provider_id or "").strip()[:60] or None,
				"enabled": 1 if str(enabled).lower() in ("1", "true", "yes") else 0})
	doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
	write_audit_event("server_saved", target_doctype=SERVER, target_name=key, metadata={"title": doc.title})
	return list_servers()


@frappe.whitelist(methods=["POST"])
def install_command(key: str) -> dict:
	"""Make a NEW token for the server and return the one-line install
	command (shown once). An agent already installed with the old token
	stops being accepted — run the new command there."""
	require_platform_owner()
	doc = frappe.get_doc(SERVER, key)
	token = secrets.token_urlsafe(32)
	doc.report_token = token
	doc.save(ignore_permissions=True)
	write_audit_event("server_token_rotated", target_doctype=SERVER, target_name=key)
	base = get_url().rstrip("/")
	command = (
		f"curl -fsSL {base}{AGENT_PATH} -o /usr/local/bin/qtt-server-agent && chmod 755 /usr/local/bin/qtt-server-agent && "
		f"printf 'QTT_URL={base}\\nQTT_SERVER={key}\\nQTT_TOKEN={token}\\n' > /etc/qtt-server-agent.env && chmod 600 /etc/qtt-server-agent.env && "
		"echo '*/5 * * * * root /usr/local/bin/qtt-server-agent >/dev/null 2>&1' > /etc/cron.d/qtt-server-agent && "
		"/usr/local/bin/qtt-server-agent --verbose"
	)
	return {"key": key, "command": command}


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------
def check_offline() -> None:
	"""Every 5 minutes: servers that stopped reporting become offline (alert once)."""
	limits = _limits()
	cutoff = now_datetime() - timedelta(minutes=limits["offline_after_minutes"])
	for s in frappe.get_all(SERVER, filters={"enabled": 1, "status": ["not in", ["offline", "new"]], "last_report_at": ["<", cutoff]},
							fields=["name", "title", "status", "last_report_at"]):
		ev = health.evaluate({"x": 1}, last_report_at=get_datetime(s.last_report_at), now=now_datetime(), limits=limits)
		frappe.db.set_value(SERVER, s.name, {"status": "offline", "problems": " ".join(p["text"] for p in ev["problems"])})
		_alert(health.alert_for_change(s.status, "offline", s.title, ev["problems"]))


def purge_reports() -> None:
	frappe.db.sql(f"DELETE FROM `tab{REPORT}` WHERE reported_at < %s", now_datetime() - timedelta(days=KEEP_DAYS))


def seed_servers() -> None:
	"""after_migrate (insert-only)."""
	if frappe.db.table_exists(SERVER):
		_seed_known()


# --------------------------------------------------------------------------
def _seed_known() -> None:
	for key, title, ip, provider, purpose in KNOWN:
		if not frappe.db.exists(SERVER, key):
			frappe.get_doc({"doctype": SERVER, "server_key": key, "title": title, "ip_address": ip, "provider_id": provider,
							"purpose": purpose, "enabled": 1, "status": "new"}).insert(ignore_permissions=True)


def _apply_status(server, clean: dict, *, report_name: str, reported_at) -> None:
	ev = health.evaluate(clean, last_report_at=get_datetime(reported_at), now=now_datetime(), limits=_limits())
	previous = None if server.status == "new" else server.status
	frappe.db.set_value(SERVER, server.name, {
		"status": ev["status"],
		"last_report_at": reported_at,
		"last_report": report_name,
		"problems": " ".join(p["text"] for p in ev["problems"]) or None,
	})
	_alert(health.alert_for_change(previous, ev["status"], server.title, ev["problems"]))


def _latest(report_name: str | None) -> dict | None:
	if not report_name:
		return None
	raw = frappe.db.get_value(REPORT, report_name, "data")
	try:
		return json.loads(raw) if raw else None
	except ValueError:
		return None


def _limits() -> dict:
	s = frappe.get_cached_doc(SETTINGS)
	return {k: s.get(k) or v for k, v in health.DEFAULTS.items()}


def _alert(text: str | None) -> None:
	if not text:
		return
	url = frappe.get_cached_doc(SETTINGS).get_password("slack_webhook_url", raise_exception=False)
	if not url:
		return
	try:
		requests.post(url, json={"text": f"*QTT servers* — {text}"}, timeout=10)
	except requests.RequestException:
		frappe.log_error(title="qtt_platform servers: Slack alert failed")
