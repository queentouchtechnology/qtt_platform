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
										   approvals=approvals, setup_errors=setup_errors, today_str=today()),
		"subscriptions_by_product": overview.get("subscriptions_by_product") or {},
	}
