"""
Launch (PROJ-0017) — "What do you want to launch today?", Help Me Choose and the dashboard counts. The app's home and
its wizard read everything from here; starting things stays where it is: an app's free trial or plan through
explore.activate, a QTT Business Suite service through its own order page (domain, design and set-up questions).

  home       the four products (apps and QTT Business Suite) with what the business has of each, the goals for Help Me
             Choose, the dashboard counts (active products, websites, automations, team) and whether this person may
             launch things (the owner)
  recommend  goals → the products, recommended first with reasons, and the Suite services that start ticked
  progress   what was launched and how far each has got (setup → design and content → connect → live)
  save_plan  the Suite services chosen in Help Me Choose, kept 30 days so the home can say "Finish setting up …" until
             each is ordered on its own page
"""

import json

import frappe
from frappe import _

from qtt_platform import launch_rules as rules
from qtt_platform.api import explore

SUITE_TAGLINE = "Websites, store, WhatsApp, AI and marketing — live in minutes"


def _catalog() -> dict:
	return explore.catalog()


def _products(cat: dict) -> list[dict]:
	"""The apps as Explore gives them, and QTT Business Suite as one product whose parts are its services."""
	items = cat.get("items") or []
	apps = [i for i in items if i.get("kind") == "app" and i["key"] in rules.APPS]
	services = [i for i in items if i.get("kind") == "service"]
	suite_name = frappe.db.get_value("QTT Product", rules.SUITE, "display_name") or "QTT Business Suite"
	have_any = [s for s in services if s.get("status") and s["status"] != "cancelled"]
	suite = {"key": rules.SUITE, "kind": "suite", "name": suite_name, "about": SUITE_TAGLINE, "icon": None,
			 "status": "active" if any(s["status"] in ("active", "setup") for s in have_any) else (have_any[0]["status"] if have_any else None),
			 "services": services, "included": cat.get("included"),
			 "price_from": min([s["price_from"] for s in services if s.get("price_from")] or [0])}
	order = {k: i for i, k in enumerate(rules.PRODUCTS)}
	return sorted(apps + [suite], key=lambda p: order.get(p["key"], 99))


def _counts(tenant: str, products: list[dict]) -> dict:
	active = sum(1 for p in products if p.get("status") in ("active", "trial"))
	websites = automations = 0
	if "qtt_services" in frappe.get_installed_apps():
		websites = frappe.db.count("Managed Asset", {"tenant": tenant, "asset_type": "website"})
		automations = frappe.db.count("Managed Automation", {"tenant": tenant, "enabled": 1})
	team = frappe.db.count("QTT Tenant Membership", {"tenant": tenant, "status": "active"})
	return {"products": active, "websites": websites, "automations": automations, "team": team}


@frappe.whitelist(methods=["GET"])
def home() -> dict:
	"""{products, goals, counts, pending, can_launch, included} — the launch home and Help Me Choose's first step.
	pending: Suite services chosen in Help Me Choose and not ordered yet ({code, option, name})."""
	cat = _catalog()
	products = _products(cat)
	tenant = explore._tenant()
	suite = next((p for p in products if p["kind"] == "suite"), None)
	ordered = {s["key"] for s in (suite or {}).get("services", []) if s.get("status") and s["status"] != "cancelled"}
	names = {s["key"]: s["name"] for s in (suite or {}).get("services", [])}
	pending = [{"code": c, "option": o, "name": names.get(c, c)} for c, o in (frappe.cache.get_value(_plan_key(tenant)) or {}).items()
			   if c in names and c not in ordered]
	return {"products": products, "goals": rules.goals(), "counts": _counts(tenant, products), "pending": pending,
			"can_launch": bool(cat.get("can_activate")), "included": bool(cat.get("included"))}


def _plan_key(tenant: str) -> str:
	return f"qtt_launch_plan:{tenant}"


@frappe.whitelist(methods=["POST"])
def save_plan(services: str | dict | None = None) -> dict:
	"""Help Me Choose › Launch: {service code: chosen package or ""} for QTT Business Suite, kept 30 days. Owner only."""
	from qtt_platform.tenant.guards import require_tenant_role

	tenant = explore._tenant()
	require_tenant_role(tenant, ["Tenant Owner"])
	chosen = json.loads(services) if isinstance(services, str) else (services or {})
	clean = {str(k): str(v or "")[:40] for k, v in (chosen or {}).items() if str(k) in rules.SERVICES}
	frappe.cache.set_value(_plan_key(tenant), clean, expires_in_sec=30 * 86400)
	return {"saved": list(clean)}


@frappe.whitelist(methods=["POST"])
def recommend(goals: str | list | None = None) -> dict:
	"""Help Me Choose step 2: {products: [{product, recommended, reasons, have}], suite: [service codes ticked]}."""
	chosen = json.loads(goals) if isinstance(goals, str) else (goals or [])
	if not isinstance(chosen, list):
		frappe.throw(_("Choose one or more goals."))
	cat = _catalog()
	have = {p["key"]: p.get("status") for p in _products(cat) if p.get("status")}
	return {"products": rules.recommend([str(g) for g in chosen][:10], have), "suite": rules.suite_pick(chosen)}


@frappe.whitelist(methods=["GET"])
def progress() -> dict:
	"""Launch success / the dashboard: each product the business has, with its steps from what really happened."""
	tenant = explore._tenant()
	out = []
	for p in _products(_catalog()):
		if p["kind"] != "suite":
			if p.get("status"):
				out.append({"key": p["key"], "name": p["name"], "status": p["status"], "steps": rules.steps("app", p["status"])})
			continue
		for s in p["services"]:
			if not s.get("status") or s["status"] == "cancelled":
				continue
			stage = None
			if "qtt_services" in frappe.get_installed_apps():
				svc = frappe.db.get_value("Managed Service", {"tenant": tenant, "service_type": s["key"], "status": ["!=", "cancelled"]}, "name")
				stage = frappe.db.get_value("Managed Asset", {"tenant": tenant, "service": svc, "asset_type": "website"}, "stage") if svc else None
			out.append({"key": s["key"], "name": s["name"], "status": s["status"], "steps": rules.steps("service", s["status"], stage)})
	return {"launched": out}
