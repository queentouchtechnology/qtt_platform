"""
QTT Admin → Usage: AI spend (DeepSeek, OpenAI), Hermes and n8n, in one place.

The usage collector on the automation server (public/ops/qtt-usage-collector.py)
pushes a snapshot every 30 minutes — push, not pull: Frappe holds none of the
AI or n8n keys. `dashboard` shows the newest snapshot plus DeepSeek's daily
spend, worked out from how its balance went down between snapshots.
"""

import json
import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, get_url, now_datetime

from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_platform_owner

SNAPSHOT = "QTT Usage Snapshot"
SETTINGS = "QTT Ops Settings"
COLLECTOR_PATH = "/assets/qtt_platform/ops/qtt-usage-collector.py"
MAX_BODY = 512 * 1024
KEEP_DAYS = 90


def deepseek_daily_spend(points: list[tuple[str, float]]) -> list[dict]:
	"""[(iso time, balance)] oldest first → [{date, spent}]: only drops count (a top-up is not spending)."""
	by_day: dict[str, float] = {}
	prev = None
	for at, balance in points:
		if prev is not None and balance < prev:
			day = str(at)[:10]
			by_day[day] = round(by_day.get(day, 0) + (prev - balance), 4)
		prev = balance
	return [{"date": d, "spent": v} for d, v in sorted(by_day.items())]


@frappe.whitelist(allow_guest=True, methods=["POST"])
def ingest():
	token = (frappe.get_request_header("X-QTT-Usage-Token") or "").strip()
	settings = frappe.get_single(SETTINGS)
	expected = settings.get_password("usage_token", raise_exception=False) if settings.get("usage_token") else None
	if not token or not expected or not secrets.compare_digest(expected, token):
		frappe.throw(_("Not allowed."), frappe.AuthenticationError)
	body = frappe.request.get_data(cache=False) if frappe.request else b""
	if len(body or b"") > MAX_BODY:
		frappe.throw(_("Too large."))
	try:
		data = json.loads(body or b"{}")
	except ValueError:
		frappe.throw(_("Send JSON."))
	frappe.get_doc({"doctype": SNAPSHOT, "taken_at": now_datetime(), "data": json.dumps(data)}).insert(ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["GET"])
def dashboard() -> dict:
	require_platform_owner()
	latest = frappe.get_all(SNAPSHOT, fields=["taken_at", "data"], order_by="taken_at desc", page_length=1)
	if not latest:
		return {"installed": False}
	snap = json.loads(latest[0].data or "{}")
	since = now_datetime() - timedelta(days=30)
	points = []
	for r in frappe.get_all(SNAPSHOT, filters={"taken_at": [">", since]}, fields=["taken_at", "data"], order_by="taken_at asc", page_length=2000):
		ds = (json.loads(r.data or "{}").get("deepseek") or {})
		if ds.get("balance") is not None:
			points.append((str(r.taken_at), float(ds["balance"])))
	ds = snap.get("deepseek") or {}
	if ds.get("connected"):
		ds["daily"] = deepseek_daily_spend(points)
		ds["spent_30d"] = round(sum(d["spent"] for d in ds["daily"]), 4)
		ds["low"] = ds.get("balance") is not None and ds["balance"] < float(frappe.get_cached_doc(SETTINGS).get("deepseek_low_balance") or 2)
	snap["deepseek"] = ds
	oa = snap.get("openai") or {}
	if oa.get("daily"):
		oa["spent_30d"] = round(sum(d["cost_usd"] for d in oa["daily"]), 4)
	return {"installed": True, "taken_at": str(latest[0].taken_at),
			"stale": (now_datetime() - get_datetime(latest[0].taken_at)).total_seconds() > 3 * 3600, **snap}


@frappe.whitelist(methods=["POST"])
def install_command() -> dict:
	"""New token + the one-line install for the collector (shown once)."""
	require_platform_owner()
	token = secrets.token_urlsafe(32)
	settings = frappe.get_single(SETTINGS)
	settings.usage_token = token
	settings.save(ignore_permissions=True)
	write_audit_event("usage_token_rotated", target_doctype=SETTINGS, target_name=SETTINGS)
	base = get_url().rstrip("/")
	command = (
		f"curl -fsSL {base}{COLLECTOR_PATH} -o /usr/local/bin/qtt-usage-collector && chmod 755 /usr/local/bin/qtt-usage-collector && "
		f"touch /etc/qtt-usage-collector.env && chmod 600 /etc/qtt-usage-collector.env && "
		f"sed -i '/^QTT_URL=/d;/^QTT_TOKEN=/d' /etc/qtt-usage-collector.env && "
		f"printf 'QTT_URL={base}\\nQTT_TOKEN={token}\\n' >> /etc/qtt-usage-collector.env && "
		"echo '*/30 * * * * root /usr/local/bin/qtt-usage-collector >/dev/null 2>&1' > /etc/cron.d/qtt-usage-collector && "
		"/usr/local/bin/qtt-usage-collector"
	)
	return {"command": command, "note": "Add DEEPSEEK_API_KEY= and OPENAI_ADMIN_KEY= lines to /etc/qtt-usage-collector.env for AI spend."}


def purge_snapshots() -> None:
	frappe.db.sql(f"DELETE FROM `tab{SNAPSHOT}` WHERE taken_at < %s", now_datetime() - timedelta(days=KEEP_DAYS))
