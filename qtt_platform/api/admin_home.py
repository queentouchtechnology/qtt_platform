"""
QTT Admin home (the staff dashboard in the app): the key numbers and one
ranked "needs attention" list, in a single call. Platform Owner only.
"""

import frappe
from frappe.utils import today

from qtt_platform import saas_admin_logic as logic
from qtt_platform.api import platform_admin, saas_admin
from qtt_platform.tenant.guards import require_platform_owner


def _exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _automation_attention() -> list[dict]:
	"""From the latest usage snapshot: DeepSeek balance running low, n8n workflows failing."""
	if not _exists("QTT Usage Snapshot"):
		return []
	import json

	row = frappe.get_all("QTT Usage Snapshot", fields=["data"], order_by="taken_at desc", page_length=1)
	if not row:
		return []
	snap = json.loads(row[0].data or "{}")
	out = []
	ds = snap.get("deepseek") or {}
	low = float(frappe.get_cached_doc("QTT Ops Settings").get("deepseek_low_balance") or 2)
	if ds.get("balance") is not None and float(ds["balance"]) < low:
		out.append({"what": "deepseek_low", "value": ds["balance"]})
	n8n = snap.get("n8n") or {}
	if int(n8n.get("errors_24h") or 0) > 0:
		out.append({"what": "n8n_errors", "value": int(n8n["errors_24h"])})
	return out


def _domain_wait_attention() -> list[dict]:
	"""Approved websites waiting 3+ days for their domain (qtt_services golive; reminders go to the owner on days 1/3/7)."""
	try:
		from qtt_services.api.golive import waiting_attention
	except ImportError:
		return []
	return waiting_attention()


def _build_attention() -> list[dict]:
	"""Frappe's build queue (qtt_services builds_admin): builds that gave up, domains over the month's limit, domain buying
	switched on without a payment method."""
	try:
		from qtt_services.api.builds_admin import attention
	except ImportError:
		return []
	return attention()


def _cache_attention() -> list[dict]:
	"""Live websites whose CloudPanel cache staff haven't switched on yet (qtt_services site_cache; the task closes itself)."""
	try:
		from qtt_services.site_cache import attention
	except ImportError:
		return []
	return attention()


def _whatsapp_attention() -> list[dict]:
	"""QTT's WhatsApp number (qtt_services, the hourly check): quality dropping, templates rejected / paused, just approved."""
	try:
		from qtt_services.api.wa_business import attention
	except ImportError:
		return []
	return attention()


def _studio_attention() -> list[dict]:
	"""QTT Studio post templates whose nightly check found a problem."""
	try:
		from qtt_platform.api.studio_admin import attention

		return attention()
	except Exception:
		return []


def _marketing_attention() -> list[dict]:
	"""Marketing assistant (qtt_services, when installed): renderer down, festivals needing this year's date, series failing."""
	try:
		from qtt_services.api.marketing_admin import attention

		return attention()
	except Exception:
		return []


def _client_attention() -> tuple[list, list]:
	"""Managed Services (qtt_services, when installed): client sites that are down,
	and client requests still waiting for QTT's first answer."""
	if not _exists("Managed Asset"):
		return [], []
	names = {}

	def tenant_name(t):
		if t not in names:
			names[t] = frappe.db.get_value("QTT Tenant", t, "tenant_name") or t
		return names[t]

	sites = [{"label": a.label, "tenant": a.tenant, "tenant_name": tenant_name(a.tenant), "problem": a.last_error}
			 for a in frappe.get_all("Managed Asset", filters={"check_enabled": 1, "health": "down"}, fields=["label", "tenant", "last_error"])]
	requests = [{"subject": r.subject, "tenant": r.tenant, "tenant_name": tenant_name(r.tenant), "urgent": r.priority == "urgent"}
				for r in frappe.get_all("Managed Request", filters={"status": "open"}, fields=["subject", "tenant", "priority"], page_length=20)]
	return sites, requests


def _provider_attention() -> tuple[list, list]:
	"""Watched domains near or past expiry, and servers whose last Contabo snapshot is missing or old."""
	if not _exists("QTT Domain"):
		return [], []
	from datetime import datetime

	from frappe.utils import getdate

	from qtt_platform.ops import providers

	settings = frappe.get_cached_doc("QTT Ops Settings")
	warn = int(settings.get("domain_warn_days") or 30)
	max_age = int(settings.get("snapshot_max_age_days") or 14)
	domains = []
	for d in frappe.get_all("QTT Domain", filters={"watch": 1}, fields=["name", "status", "expires_on"]):
		level, days = providers.domain_level(status=d.status, expires_on=d.expires_on, today=getdate(today()), warn_days=warn)
		if level in ("warning", "critical"):
			domains.append({"domain": d.name, "level": level, "days_left": days})
	snapshots = []
	for s in frappe.get_all("QTT Server", filters={"enabled": 1, "provider_synced_at": ["is", "set"]},
							fields=["server_key", "title", "last_snapshot_at"]):
		days = (datetime.utcnow() - s.last_snapshot_at).days if s.last_snapshot_at else None
		if days is None or days > max_age:
			snapshots.append({"key": s.server_key, "title": s.title, "days": days})
	return domains, snapshots


@frappe.whitelist(methods=["GET"])
def home() -> dict:
	require_platform_owner()
	overview = platform_admin.overview()
	rev = saas_admin.revenue()

	servers = []
	if _exists("QTT Server"):
		servers = [{"key": r.server_key, "title": r.title, "status": r.status, "problems": r.problems}
				   for r in frappe.get_all("QTT Server", filters={"enabled": 1, "status": ["in", ["warning", "critical", "offline"]]},
										   fields=["server_key", "title", "status", "problems"])]
	domains, snapshots = _provider_attention()
	client_sites, client_requests = _client_attention()
	automation = _automation_attention()
	approvals = []
	if _exists("QTT Marketing Content"):
		approvals = frappe.get_all("QTT Marketing Content", filters={"status": "pending"}, fields=["name", "title"],
								   order_by="creation desc", page_length=20)

	setup_errors = []
	for doctype, product in (("QTT Onbox Tenant Binding", "Onbox"), ("Office Pulse Workspace", "Office Pulse")):
		if _exists(doctype):
			for r in frappe.get_all(doctype, filters={"status": "error"}, fields=["tenant", "last_error"]):
				setup_errors.append({"tenant": r.tenant, "product": product, "error": r.last_error,
									 "tenant_name": frappe.db.get_value("QTT Tenant", r.tenant, "tenant_name")})

	tenants = overview.get("tenants") or {}
	return {
		"currency": rev.get("currency"),
		"kpis": {
			"workspaces": overview.get("tenants_total", 0),
			"active": tenants.get("active", 0),
			"trial": tenants.get("trial", 0),
			"mrr": rev.get("mrr", 0),
			"collected_this_month": (rev.get("collected") or {}).get("this_month", 0),
			"servers_ok": frappe.db.count("QTT Server", {"enabled": 1, "status": "ok"}) if _exists("QTT Server") else 0,
			"servers_total": frappe.db.count("QTT Server", {"enabled": 1}) if _exists("QTT Server") else 0,
		},
		"attention": logic.attention_items(servers=servers, trials=rev.get("trials_ending") or [], past_due=rev.get("past_due") or [],
										   approvals=approvals, setup_errors=setup_errors, domains=domains,
										   snapshots=snapshots, client_sites=client_sites, client_requests=client_requests, automation=automation,
										   whatsapp=_whatsapp_attention(), website_cache=_cache_attention(), domain_wait=_domain_wait_attention(), builds=_build_attention(),
										   studio=_studio_attention(),
										   marketing=_marketing_attention(),
										   today_str=today()),
		"subscriptions_by_product": overview.get("subscriptions_by_product") or {},
	}
