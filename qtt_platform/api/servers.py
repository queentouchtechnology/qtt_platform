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
from datetime import datetime, timedelta

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, get_url, getdate, now_datetime, today

from qtt_platform import site_watch_rules as site_watch
from qtt_platform.audit import write_audit_event
from qtt_platform.ops import cert_watch
from qtt_platform.ops import expiry_watch
from qtt_platform.ops import providers
from qtt_platform.ops import server_health as health
from qtt_platform.tenant.guards import require_platform_owner

SERVER = "QTT Server"
REPORT = "QTT Server Report"
DOMAIN = "QTT Domain"
SETTINGS = "QTT Ops Settings"
MAX_BODY = 256 * 1024
MIN_INTERVAL_SECONDS = 60
KEEP_DAYS = 30
AGENT_PATH = "/assets/qtt_platform/ops/qtt-server-agent.py"

# Known servers (docs/ops/vps-report-2026-10-10.md). Created once; edit in the app or Desk.
KNOWN = [
	("frappe", "Frappe (app.queentouchtech.in)", "185.217.127.94", "Contabo vmi2748666", "Frappe bench in Docker: app.queentouchtech.in, learn.truthofbible.org; Nginx Proxy Manager; Uptime Kuma"),
	("n8n", "n8n · Chatwoot", "173.249.7.188", "Contabo vmi2682166", "n8n, Chatwoot (watz), Discourse, MinIO, Qdrant, PostgreSQL, MariaDB"),
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
	for s in frappe.get_all(SERVER, fields=["name", "title", "ip_address", "provider_id", "purpose", "enabled", "status", "last_report_at", "last_report",
											*_PROVIDER_FIELDS], order_by="title asc"):
		latest = _latest(s.last_report)
		ev = health.evaluate(latest, last_report_at=get_datetime(s.last_report_at) if s.last_report_at else None, now=now_datetime(), limits=_limits(),
							 forecast=_disk_forecast(s.name, latest))
		out.append({
			"key": s.name, "title": s.title, "ip": s.ip_address, "provider_id": s.provider_id, "purpose": s.purpose,
			"enabled": bool(s.enabled), "status": ev["status"] if s.enabled else "disabled",
			"last_report_at": str(s.last_report_at) if s.last_report_at else None,
			"problems": ev["problems"], "notices": ev["notices"] + _provider_notices(s), "latest": latest,
			"provider": _provider_out(s),
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
	ev = health.evaluate(latest, last_report_at=get_datetime(server.last_report_at) if server.last_report_at else None, now=now_datetime(), limits=_limits(),
						 forecast=_disk_forecast(server.name, latest))
	return {
		"key": server.name, "title": server.title, "ip": server.ip_address, "provider_id": server.provider_id, "purpose": server.purpose,
		"enabled": bool(server.enabled), "status": ev["status"], "problems": ev["problems"], "notices": ev["notices"] + _provider_notices(server),
		"provider": _provider_out(server),
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
# Hosting providers (Contabo servers + snapshots, Hostinger domains)
# --------------------------------------------------------------------------
_PROVIDER_FIELDS = ["provider_instance_id", "provider_status", "provider_plan", "provider_synced_at",
					"last_snapshot_at", "snapshot_auto_delete", "snapshot_count"]


@frappe.whitelist(methods=["GET"])
def list_domains() -> dict:
	require_platform_owner()
	settings = frappe.get_cached_doc(SETTINGS)
	warn = int(settings.get("domain_warn_days") or 30)
	today = now_datetime().date()
	out, counts = [], {}
	for d in frappe.get_all(DOMAIN, fields=["name", "registrar", "status", "expires_on", "watch"], order_by="expires_on asc"):
		level, days = providers.domain_level(status=d.status, expires_on=d.expires_on, today=today, warn_days=warn, watch=bool(d.watch))
		counts[level] = counts.get(level, 0) + 1
		out.append({"domain": d.name, "registrar": d.registrar, "status": d.status, "level": level, "days_left": days,
					"expires_on": str(d.expires_on) if d.expires_on else None, "watch": bool(d.watch)})
	return {"domains": out, "counts": counts,
			"synced_at": str(settings.providers_synced_at) if settings.get("providers_synced_at") else None,
			"error": settings.get("providers_error") or None, "configured": _providers_configured(settings)}


@frappe.whitelist(methods=["POST"])
def set_domain_watch(domain: str, watch=1) -> dict:
	"""Untick for a domain being let go: no more expiry warnings for it."""
	require_platform_owner()
	value = 1 if str(watch).lower() in ("1", "true", "yes") else 0
	frappe.db.set_value(DOMAIN, domain, "watch", value)
	write_audit_event("domain_watch_changed", target_doctype=DOMAIN, target_name=domain, metadata={"watch": value})
	return list_domains()


@frappe.whitelist(methods=["POST"])
def refresh_providers() -> dict:
	"""Fetch from Contabo and Hostinger now (otherwise every 6 hours)."""
	require_platform_owner()
	last = frappe.db.get_single_value(SETTINGS, "providers_synced_at")
	if not last or (now_datetime() - get_datetime(last)).total_seconds() >= MIN_INTERVAL_SECONDS:
		sync_providers()
		frappe.clear_document_cache(SETTINGS, SETTINGS)
	return list_domains()


def sync_providers() -> None:
	"""Scheduler (every 6 hours) and the app's refresh. Read-only calls; a failing
	provider is noted in QTT Ops Settings and does not stop the other one."""
	settings = frappe.get_doc(SETTINGS)
	errors = []
	if settings.get("contabo_client_id") and settings.get("contabo_api_user"):
		try:
			_apply_contabo(providers.contabo_inventory(
				settings.contabo_client_id, settings.get_password("contabo_client_secret", raise_exception=False) or "",
				settings.contabo_api_user, settings.get_password("contabo_api_password", raise_exception=False) or ""))
		except providers.ProviderError as exc:
			errors.append(str(exc))
	token = settings.get_password("hostinger_api_token", raise_exception=False) if settings.get("hostinger_api_token") else None
	if token:
		try:
			_apply_domains(providers.hostinger_domains(token), registrar="Hostinger")
		except providers.ProviderError as exc:
			errors.append(str(exc))
	frappe.db.set_single_value(SETTINGS, {"providers_synced_at": now_datetime(), "providers_error": " | ".join(errors)[:1000] or None})
	frappe.db.commit()


def _providers_configured(settings) -> dict:
	return {"contabo": bool(settings.get("contabo_client_id") and settings.get("contabo_api_user")),
			"hostinger": bool(settings.get("hostinger_api_token"))}


def _apply_contabo(instances: list[dict]) -> None:
	now = now_datetime()
	servers = frappe.get_all(SERVER, fields=["name", "ip_address", "provider_id", "provider_instance_id"])
	for inst in instances:
		match = (next((s for s in servers if s.provider_instance_id and s.provider_instance_id == inst["instance_id"]), None)
				 or next((s for s in servers if inst.get("ip") and s.ip_address == inst["ip"]), None)
				 or next((s for s in servers if inst.get("name") and inst["name"] in (s.provider_id or "")), None))
		if not match:
			# A server QTT pays for but doesn't monitor yet: list it so it isn't forgotten.
			key = (inst.get("name") or inst["instance_id"]).lower()[:30]
			frappe.get_doc({"doctype": SERVER, "server_key": key, "title": (inst.get("display_name") or key)[:80], "ip_address": inst.get("ip"),
							"provider_id": f"Contabo {inst.get('name') or ''}".strip(), "enabled": 1, "status": "new"}).insert(ignore_permissions=True)
			match = frappe._dict(name=key)
		frappe.db.set_value(SERVER, match.name, {
			"provider_instance_id": inst["instance_id"], "provider_status": inst.get("status"), "provider_plan": (inst.get("plan") or "")[:140],
			"provider_synced_at": now, **providers.snapshot_state(inst["snapshots"]),
		}, update_modified=False)


def _apply_domains(domains: list[dict], *, registrar: str) -> None:
	now = now_datetime()
	for d in domains:
		values = {"registrar": registrar, "status": d.get("status"), "expires_on": d.get("expires_on"), "synced_at": now}
		if frappe.db.exists(DOMAIN, d["domain"]):
			frappe.db.set_value(DOMAIN, d["domain"], values, update_modified=False)
		else:
			# Already expired when first seen = being let go: don't warn about it.
			frappe.get_doc({"doctype": DOMAIN, "domain": d["domain"], "watch": 0 if (d.get("status") or "").lower() == "expired" else 1,
							**values}).insert(ignore_permissions=True)


def _provider_out(s) -> dict | None:
	if not s.get("provider_synced_at"):
		return None
	return {
		"instance_id": s.provider_instance_id, "status": s.provider_status, "plan": s.provider_plan,
		"synced_at": str(s.provider_synced_at),
		"last_snapshot_at": _utc_iso(s.last_snapshot_at), "snapshot_auto_delete": _utc_iso(s.snapshot_auto_delete),
		"snapshot_count": s.snapshot_count or 0,
	}


def _utc_iso(value) -> str | None:
	return f"{get_datetime(value).isoformat()}Z" if value else None


def _provider_notices(s) -> list[str]:
	if not s.get("provider_synced_at"):
		return []
	max_age = int(frappe.get_cached_doc(SETTINGS).get("snapshot_max_age_days") or 14)
	return providers.server_notices(last_snapshot_at=s.last_snapshot_at, snapshot_auto_delete=s.snapshot_auto_delete,
									provider_status=s.provider_status, now=datetime.utcnow(), max_age_days=max_age)

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


def check_sites() -> None:
	"""Every 5 minutes: the websites in QTT Ops Settings › Website watch (site_watch_rules) — alert on down / back up."""
	s = frappe.get_cached_doc(SETTINGS)
	sites = site_watch.parse_sites(s.get("watched_sites"))
	if not sites:
		return
	try:
		states = json.loads(s.get("site_watch_state") or "{}")
	except ValueError:
		states = {}
	new_states = {}
	for site in sites:
		code, error = None, None
		try:
			code = requests.get(site["url"], timeout=20, headers={"User-Agent": "QTT site watch"}).status_code
		except requests.RequestException as e:
			error = type(e).__name__.replace("Error", " error").replace("Timeout", "timed out").strip()
		ok, problem = site_watch.describe(code, error)
		new_states[site["url"]], alert = site_watch.step(states.get(site["url"]), ok=ok, problem=problem, label=site["label"])
		_alert(alert)
	frappe.db.set_single_value(SETTINGS, "site_watch_state", json.dumps(new_states), update_modified=False)


def watched_sites_down() -> list[dict]:
	"""Down websites for QTT Admin's Needs attention (shaped like servers)."""
	s = frappe.get_cached_doc(SETTINGS)
	try:
		states = json.loads(s.get("site_watch_state") or "{}")
	except ValueError:
		states = {}
	return site_watch.down_sites(site_watch.parse_sites(s.get("watched_sites")), states)


def check_certs() -> None:
	"""Every 6 hours: the certificates in QTT Ops Settings › Certificates to watch (ops/cert_watch) — Telegram as one
	gets close to expiring without renewing, or can't be read twice in a row."""
	s = frappe.get_cached_doc(SETTINGS)
	hosts = cert_watch.parse_hosts(s.get("cert_watch_hosts"))
	if not hosts:
		return
	try:
		states = json.loads(s.get("cert_watch_state") or "{}")
	except ValueError:
		states = {}
	warn = int(s.get("cert_warn_days") or 14)
	new_states = {}
	for host in hosts:
		days, error = _cert_days(host)
		new_states[host], alert = cert_watch.step(states.get(host), host=host, days=days, error=error, warn_days=warn)
		new_states[host]["checked"] = str(now_datetime())
		_alert(alert)
	frappe.db.set_single_value(SETTINGS, "cert_watch_state", json.dumps(new_states), update_modified=False)


def cert_problems() -> list[dict]:
	"""Certificates close to expiring or unreadable, for QTT Admin's Needs attention (shaped like servers)."""
	s = frappe.get_cached_doc(SETTINGS)
	try:
		states = json.loads(s.get("cert_watch_state") or "{}")
	except ValueError:
		states = {}
	return cert_watch.problems(cert_watch.parse_hosts(s.get("cert_watch_hosts")), states, int(s.get("cert_warn_days") or 14))


def _cert_days(host: str) -> tuple[int | None, str | None]:
	"""(whole days the certificate has left, None) or (None, why it can't be read) — a full check, as a browser does."""
	import socket
	import ssl

	try:
		with socket.create_connection((host, 443), timeout=15) as sock, ssl.create_default_context().wrap_socket(sock, server_hostname=host) as tls:
			not_after = datetime.utcfromtimestamp(ssl.cert_time_to_seconds(tls.getpeercert()["notAfter"]))
	except ssl.SSLCertVerificationError as e:
		return None, (e.verify_message or "not trusted")[:160]
	except (OSError, ssl.SSLError, KeyError, ValueError) as e:
		return None, (type(e).__name__.replace("Error", " error").replace("Timeout", "timed out").strip() or "no answer")[:160]
	return (not_after - datetime.utcnow()).days, None


def _disk_forecast(server_key: str, latest: dict | None) -> dict | None:
	"""Disk growth over the last 7 days (hourly averages of the stored reports) → health.disk_forecast."""
	if not latest or not latest.get("disk_total_gb"):
		return None
	rows = frappe.db.sql(
		f"""SELECT MIN(reported_at), AVG(disk_used_gb) FROM `tab{REPORT}`
			WHERE server = %s AND reported_at >= %s AND disk_used_gb IS NOT NULL
			GROUP BY DATE_FORMAT(reported_at, '%%Y-%%m-%%d %%H')""",
		(server_key, now_datetime() - timedelta(days=7)))
	return health.disk_forecast([(get_datetime(t), float(u)) for t, u in rows if t is not None and u is not None], latest["disk_total_gb"])


# --------------------------------------------------------------------------
# Expiry register + Monday ops report (ops/expiry_watch)
# --------------------------------------------------------------------------
EXPIRY = "QTT Expiry Item"


@frappe.whitelist(methods=["GET"])
def ops_watch() -> dict:
	"""QTT Admin › Servers › Expiring and Weekly report: the expiry register (Desk › QTT Expiry Item), the watched
	certificates (QTT Ops Settings › Certificate watch) and the last Monday ops report."""
	require_platform_owner()
	day = getdate(today())
	items = []
	for i in frappe.get_all(EXPIRY, fields=["name", "title", "kind", "expires_on", "watch", "used_by", "renew_how"], order_by="expires_on asc"):
		d = expiry_watch.days_left(getdate(i.expires_on), day)
		items.append({"id": i.name, "title": i.title, "kind": i.kind, "expires_on": str(i.expires_on), "days_left": d,
					  "level": expiry_watch.level(d) if i.watch else "ok", "watch": bool(i.watch), "used_by": i.used_by, "renew_how": i.renew_how})
	s = frappe.get_cached_doc(SETTINGS)
	certs = []
	for c in _cert_rows(s):
		certs.append({"host": c["host"], "days_left": c["days"], "error": c["error"], "level": c["level"], "checked": c["checked"]})
	certs.sort(key=lambda c: (c["level"] == "ok", c["days_left"] if c["days_left"] is not None else -1))
	return {"expiries": items, "certs": certs,
			"report": {"at": str(s.last_report_at) if s.get("last_report_at") else None, "text": s.get("last_report_text") or None,
					   "on": bool(s.get("weekly_report"))}}


@frappe.whitelist(methods=["POST"])
def send_ops_report() -> dict:
	"""Make the weekly ops report now and send it to the ops Telegram (the app's Send now)."""
	require_platform_owner()
	weekly_report(force=True)
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	write_audit_event("ops_report_sent", target_doctype=SETTINGS, target_name=SETTINGS)
	return ops_watch()


def check_expiries() -> None:
	"""Daily 09:15: refresh looked-up domain dates, then one Telegram per reminder step (30/14/7/3/1/0/expired)."""
	day = getdate(today())
	for i in frappe.get_all(EXPIRY, filters={"watch": 1}, fields=["name", "title", "kind", "expires_on", "used_by", "renew_how",
																	"domain_lookup", "last_step"]):
		values = {"last_checked": now_datetime()}
		expires_on = getdate(i.expires_on)
		last_step = int(i.last_step) if str(i.last_step or "").lstrip("-").isdigit() else None  # Data field: "" = none yet
		if i.domain_lookup:
			found, error = _registry_expiry(i.domain_lookup)
			values["lookup_error"] = error
			if found and found != expires_on:
				expires_on = values["expires_on"] = found
				last_step = None  # renewed: start over
		days = expiry_watch.days_left(expires_on, day)
		new_step, send = expiry_watch.step(last_step, days)
		values["last_step"] = "" if new_step is None else str(new_step)
		frappe.db.set_value(EXPIRY, i.name, values, update_modified=False)
		if send:
			_alert(expiry_watch.reminder(title=i.title, kind=i.kind, days=days, used_by=i.used_by, renew_how=i.renew_how))
	frappe.db.commit()


def expiry_problems() -> list[dict]:
	"""Register items within 14 days, for QTT Admin's Needs attention (shaped like servers)."""
	rows = frappe.get_all(EXPIRY, filters={"watch": 1}, fields=["title", "kind", "expires_on", "watch"])
	return expiry_watch.problems([{**r, "expires_on": getdate(r.expires_on)} for r in rows], getdate(today()))


def weekly_report(force: bool = False) -> None:
	"""Mondays 09:00 (QTT Ops Settings › Send the Monday ops report): everything slow-moving in one message."""
	if not force and not frappe.db.get_single_value(SETTINGS, "weekly_report"):
		return
	text = expiry_watch.digest(**_report_facts())
	frappe.db.set_single_value(SETTINGS, {"last_report_at": now_datetime(), "last_report_text": text}, update_modified=False)
	frappe.db.commit()
	_alert(text, prefix=False)


def _cert_rows(s) -> list[dict]:
	"""Watched certificates with their last check: {host, days, error (after two failed reads), level, checked}."""
	try:
		states = json.loads(s.get("cert_watch_state") or "{}")
	except ValueError:
		states = {}
	warn = int(s.get("cert_warn_days") or 14)
	out = []
	for host in cert_watch.parse_hosts(s.get("cert_watch_hosts")):
		st = states.get(host) or {}
		fails = int(st.get("fails") or 0)
		out.append({"host": host, "days": st.get("days"), "error": st.get("error") if fails >= 2 else None,
					"level": cert_watch.level(st.get("days"), st.get("error"), fails, warn), "checked": st.get("checked")})
	return out


def _report_facts() -> dict:
	day = getdate(today())
	limits = _limits()
	servers = []
	for s in frappe.get_all(SERVER, filters={"enabled": 1}, fields=["name", "title", "last_report_at", "last_report"], order_by="title asc"):
		latest = _latest(s.last_report)
		fc = _disk_forecast(s.name, latest)
		ev = health.evaluate(latest, last_report_at=get_datetime(s.last_report_at) if s.last_report_at else None, now=now_datetime(),
							 limits=limits, forecast=fc)
		servers.append({"title": s.title, "status": ev["status"], "problems": " ".join(p["text"] for p in ev["problems"]) or None,
						"disk_pct": (latest or {}).get("disk_used_pct"), "forecast_days": fc["days"] if fc else None})
	certs = [{"host": c["host"], "days": c["days"], "error": c["error"]} for c in _cert_rows(frappe.get_cached_doc(SETTINGS))]
	expiries = [{"title": r.title, "kind": r.kind, "days": expiry_watch.days_left(getdate(r.expires_on), day)}
				for r in frappe.get_all(EXPIRY, filters={"watch": 1}, fields=["title", "kind", "expires_on"])]
	domains = [{"domain": d.name, "days": expiry_watch.days_left(getdate(d.expires_on), day)}
			   for d in frappe.get_all(DOMAIN, filters={"watch": 1, "expires_on": ["is", "set"]}, fields=["name", "expires_on"])]
	return {"today": day, "servers": servers, "certs": certs, "expiries": expiries, "domains": domains,
			"n8n": _n8n_failures(), "jobs_age_minutes": _jobs_age_minutes()}


def _n8n_failures() -> dict:
	"""Failed runs per workflow in the last 7 days (the n8n key lives in QTT Marketing Settings)."""
	try:
		from qtt_platform.marketing.n8n import N8nClient

		m = frappe.get_single("QTT Marketing Settings")
		key = m.get_password("n8n_api_key", raise_exception=False) if m.get("n8n_url") else None
		if not key:
			return {"error": "n8n isn't connected (QTT Marketing Settings)"}
		client = N8nClient(m.n8n_url, key)
		since = datetime.utcnow() - timedelta(days=7)
		names = {w["id"]: w["name"] for w in client.workflows()}
		counts: dict = {}
		for e in client.executions(status="error", limit=250):
			started = (e.get("startedAt") or "")[:19]
			if started and datetime.fromisoformat(started) >= since:
				counts[e.get("workflowId")] = counts.get(e.get("workflowId"), 0) + 1
		return {"failing": sorted(((names.get(w, w or "?"), n) for w, n in counts.items()), key=lambda x: -x[1])}
	except Exception as e:
		return {"error": f"{type(e).__name__}: {str(e)[:100]}"}


def _jobs_age_minutes() -> int | None:
	"""Minutes since the newest Scheduled Job Log row (stored in the site's time, like now_datetime)."""
	newest = frappe.db.sql("SELECT MAX(creation) FROM `tabScheduled Job Log`")[0][0]
	return max(0, int((now_datetime() - get_datetime(newest)).total_seconds() // 60)) if newest else None


_RDAP_BASES: dict = {}


def _registry_expiry(domain: str):
	"""(expiry date, None) or (None, why) from the domain's public registry (RDAP, via IANA's list of registries)."""
	domain = (domain or "").strip().lower().rstrip(".")
	tld = domain.rsplit(".", 1)[-1]
	try:
		if not _RDAP_BASES:
			for tlds, urls in requests.get("https://data.iana.org/rdap/dns.json", timeout=20).json().get("services", []):
				for t in tlds:
					_RDAP_BASES[t] = urls[0]
		base = _RDAP_BASES.get(tld)
		if not base:
			return None, f"no public registry lookup for .{tld}"
		r = requests.get(f"{base.rstrip('/')}/domain/{domain}", timeout=20, headers={"Accept": "application/rdap+json"})
		if r.status_code != 200:
			return None, f"registry answered {r.status_code}"
		for e in r.json().get("events", []):
			if e.get("eventAction") == "expiration":
				return getdate(e["eventDate"][:10]), None
		return None, "registry gave no expiry date"
	except (requests.RequestException, ValueError, KeyError) as e:
		return None, type(e).__name__[:140]


def purge_reports() -> None:
	frappe.db.sql(f"DELETE FROM `tab{REPORT}` WHERE reported_at < %s", now_datetime() - timedelta(days=KEEP_DAYS))


def seed_servers() -> None:
	"""after_migrate (insert-only)."""
	if frappe.db.table_exists(SERVER):
		_seed_known()
	_seed_watched_sites()
	_seed_cert_hosts()


def _seed_watched_sites() -> None:
	"""The first websites to watch, set once when the field is empty (edit them in Desk afterwards)."""
	if not frappe.get_meta(SETTINGS).has_field("watched_sites"):
		return
	if not frappe.db.get_single_value(SETTINGS, "watched_sites"):
		frappe.db.set_single_value(SETTINGS, "watched_sites", "QuizMaster server | https://app.quizmasterplus.in/api/method/ping",
								   update_modified=False)


# Live HTTPS hosts on 12 Nov 2026 (each answered with a valid certificate that day). Set once when the field is empty.
CERT_HOSTS = """app.queentouchtech.in
queentouchtech.in
queentouchtech.com
staging.queentouchtech.in
staging-api.queentouchtech.in
errors.queentouchtech.in
n8n.queentouchtech.in
watz.queentouchtech.in
share.queentouchtech.in
s3.queentouchtech.in
media.queentouchtech.in
storage.queentouchtech.in
docs.queentouchtech.in
pdf.queentouchtech.in
tools.queentouchtech.in
social.queentouchtech.in
dashbeam.queentouchtech.in
vector.queentouchtech.in
career.queentouchtech.in
meet.queentouchtech.in
office.queentouchtech.in
learn.truthofbible.org
truthofbible.org
community.truthofbible.org
s3.truthofbible.org
app.quizmasterplus.in
sathishkumar.pro"""


def _seed_cert_hosts() -> None:
	if frappe.get_meta(SETTINGS).has_field("cert_watch_hosts") and not frappe.db.get_single_value(SETTINGS, "cert_watch_hosts"):
		frappe.db.set_single_value(SETTINGS, "cert_watch_hosts", CERT_HOSTS, update_modified=False)


# --------------------------------------------------------------------------
def _seed_known() -> None:
	for key, title, ip, provider, purpose in KNOWN:
		if not frappe.db.exists(SERVER, key):
			frappe.get_doc({"doctype": SERVER, "server_key": key, "title": title, "ip_address": ip, "provider_id": provider,
							"purpose": purpose, "enabled": 1, "status": "new"}).insert(ignore_permissions=True)


def _apply_status(server, clean: dict, *, report_name: str, reported_at) -> None:
	ev = health.evaluate(clean, last_report_at=get_datetime(reported_at), now=now_datetime(), limits=_limits(),
						 forecast=_disk_forecast(server.name, clean))
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


def _alert(text: str | None, prefix: bool = True) -> None:
	"""An ops message: the ops Telegram (QTT Ops Settings › Telegram bot), and Slack when a webhook is set."""
	if not text:
		return
	s = frappe.get_cached_doc(SETTINGS)
	token, chat = s.get_password("telegram_bot_token", raise_exception=False), s.get("telegram_chat")
	if token and chat:
		try:
			requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": f"QTT — {text}" if prefix else text,
																				   "disable_web_page_preview": "true"}, timeout=10)
		except requests.RequestException:
			frappe.log_error(title="qtt_platform: Telegram alert failed")
	url = s.get_password("slack_webhook_url", raise_exception=False)
	if not url:
		return
	try:
		requests.post(url, json={"text": f"*QTT servers* — {text}"}, timeout=10)
	except requests.RequestException:
		frappe.log_error(title="qtt_platform servers: Slack alert failed")
