"""
QTT Admin → Marketing: QTT's own marketing automation (n8n) — settings,
workflow health and on/off. Platform Owners only, like the rest of the
console (api/platform_admin.py).

The n8n API key is stored encrypted (Password field on QTT Marketing
Settings) and never returned; the app only learns whether one is set.
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.marketing.n8n import N8nClient, N8nError, run_row, summarize
from qtt_platform.tenant.guards import require_platform_owner

SETTINGS = "QTT Marketing Settings"
_CACHE_KEY = "qtt_marketing:overview"
_CACHE_SECONDS = 30


@frappe.whitelist(methods=["GET"])
def get_settings() -> dict:
	require_platform_owner()
	doc = frappe.get_cached_doc(SETTINGS)
	return {
		"enabled": bool(doc.enabled),
		"n8n_url": doc.n8n_url or "",
		"has_api_key": bool(doc.get_password("n8n_api_key", raise_exception=False)),
	}


@frappe.whitelist(methods=["POST"])
def save_settings(n8n_url: str, api_key: str | None = None, enabled=1) -> dict:
	"""Empty api_key keeps the stored one (the app never has it to resend)."""
	require_platform_owner()
	doc = frappe.get_doc(SETTINGS)
	before_url = doc.n8n_url
	doc.n8n_url = n8n_url
	doc.enabled = 1 if str(enabled).lower() in ("1", "true", "yes") else 0
	key_changed = bool((api_key or "").strip())
	if key_changed:
		doc.n8n_api_key = api_key.strip()
	doc.save(ignore_permissions=True)
	frappe.cache().delete_value(_CACHE_KEY)
	write_audit_event(
		"marketing_settings_changed",
		target_doctype=SETTINGS,
		target_name=SETTINGS,
		before_state={"n8n_url": before_url},
		after_state={"n8n_url": doc.n8n_url, "enabled": doc.enabled},
		metadata={"api_key_changed": key_changed},
	)
	return get_settings()


@frappe.whitelist(methods=["POST"])
def test_connection() -> dict:
	require_platform_owner()
	workflows = _call(lambda c: c.workflows())
	return {"ok": True, "workflows": len(workflows), "active": sum(1 for w in workflows if w.get("active"))}


@frappe.whitelist(methods=["GET"])
def overview(refresh=0) -> dict:
	"""Workflows with last run and 24 h counts, failing ones first.
	Cached briefly so opening the tab repeatedly doesn't hammer n8n."""
	require_platform_owner()
	settings = get_settings()
	if not settings["enabled"] or not settings["n8n_url"] or not settings["has_api_key"]:
		return {"configured": False, **settings}
	cache = frappe.cache()
	if str(refresh).lower() not in ("1", "true"):
		cached = cache.get_value(_CACHE_KEY)
		if cached:
			return cached
	result = _call(lambda c: summarize(c.workflows(), c.executions()))
	result.update({"configured": True, "n8n_url": settings["n8n_url"], "fetched_at": frappe.utils.now()})
	cache.set_value(_CACHE_KEY, result, expires_in_sec=_CACHE_SECONDS)
	return result


@frappe.whitelist(methods=["GET"])
def workflow_runs(workflow_id: str) -> list[dict]:
	require_platform_owner()
	return [run_row(e) for e in _call(lambda c: c.executions(workflow_id=str(workflow_id), limit=25))]


@frappe.whitelist(methods=["POST"])
def set_workflow_active(workflow_id: str, active, name: str | None = None) -> dict:
	"""Turn a workflow on or off. The app confirms first; audited."""
	require_platform_owner()
	active = str(active).lower() in ("1", "true", "yes")
	wf = _call(lambda c: c.set_active(str(workflow_id), active))
	frappe.cache().delete_value(_CACHE_KEY)
	write_audit_event(
		"marketing_workflow_activated" if active else "marketing_workflow_deactivated",
		metadata={"workflow_id": str(workflow_id), "name": wf.get("name") or name},
	)
	return {"id": str(workflow_id), "active": bool(wf.get("active", active))}


# --------------------------------------------------------------------------
def _call(fn):
	doc = frappe.get_cached_doc(SETTINGS)
	try:
		client = N8nClient(doc.n8n_url, doc.get_password("n8n_api_key", raise_exception=False) or "")
		return fn(client)
	except N8nError as exc:
		frappe.throw(_(str(exc)), title=_("Marketing automation"))
