"""
The public price list: every app's public plans and every managed service's plans and add-ons — what
queentouchtech.in/pricing/ shows live and website/export_data.py writes into the website's data. No login, read
only, nothing about any business. Kept for 5 minutes (a price saved in QTT Admin shows within 5 minutes; saving a
plan clears it at once) and rate-limited per address against bots.
"""

import frappe
from frappe.rate_limiter import rate_limit

CACHE_KEY = "qtt_public_pricing"
TTL = 300


def build() -> dict:
	"""{apps: [{key, name, about, highlights, plans}], services: [{key, name, about, highlights, price_from, setup_from,
	plans, addons}]} from the live plans."""
	from qtt_platform.api import explore

	fields = ["product_key", "display_name", "description"] + (["highlights"] if frappe.get_meta("QTT Product").has_field("highlights") else [])
	apps = []
	for p in frappe.get_all("QTT Product", filters={"status": "active"}, fields=fields):
		if p.product_key == explore.SERVICES:
			continue
		apps.append({"key": p.product_key, "name": p.display_name, "about": p.description,
					 "highlights": [x.strip() for x in (p.get("highlights") or "").splitlines() if x.strip()],
					 "plans": [{k: pl[k] for k in ("code", "name", "price", "period", "trial_days", "features")} for pl in explore._plans(p.product_key)]})
	services = []
	if "qtt_services" in frappe.get_installed_apps():
		from qtt_services.api.shop import explore_items

		house = frappe.db.get_value("QTT Tenant", {"is_house": 1}, "name") if frappe.get_meta("QTT Tenant").has_field("is_house") else None
		tenant = house or (frappe.get_all("QTT Tenant", pluck="name", limit=1) or [None])[0]
		for s in explore_items(tenant) if tenant else []:
			services.append({"key": s["key"], "name": s["name"], "about": s["about"], "highlights": s.get("highlights") or [],
							 "price_from": s.get("price_from"), "setup_from": s.get("setup_from"),
							 "plans": [{k: p.get(k) for k in ("code", "name", "price", "setup", "period", "features")} for p in s.get("plans") or []],
							 "addons": [{k: a.get(k) for k in ("key", "name", "price", "setup")} for a in s.get("addons") or []]})
	return {"apps": apps, "services": services}


def clear(*_args, **_kwargs) -> None:
	frappe.cache().delete_value(CACHE_KEY)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=600)
def get() -> dict:
	"""The public price list (apps and managed services, with plans, features and add-ons) — for queentouchtech.in."""
	data = frappe.cache().get_value(CACHE_KEY)
	if not data:
		data = frappe.as_json(build())
		frappe.cache().set_value(CACHE_KEY, data, expires_in_sec=TTL)
	frappe.local.response["http_cache_control"] = "public, max-age=60"
	return frappe.parse_json(data)
