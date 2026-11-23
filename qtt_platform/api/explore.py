"""
Explore QTT OS — every app and managed service in one place, for the business owner (app: Home › Explore QTT OS).
Every app comes with QTT OS (free until the free-use limits, then the one plan for all 8 apps — api/free_use): an app
shows what it does and Open / Turn on; there are no per-app plans (gone 23 Nov 2026). Managed services are ordered on
their own page (qtt_services.api.shop.order).

  catalog    the apps and services, and what this business has of each
  activate   turn on an app the business hasn't opened yet (owner) — included, no plan to choose, no invoice
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.subscription import service as subscription_service
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

SUB = "QTT Product Subscription"
SERVICES = "QTT_SERVICES"  # Managed Services: the home of the services, not an app of its own here
APP_ORDER = ("QTT_ORBITRA", "QTT_OFFICE_PULSE", "QTT_STUDIO")
# Not offered here: the team inbox (Onbox) comes with AI & WhatsApp Automation and the website services
# (qtt_services/inbox.py); QTT_OS is the one plan itself (billing, not an app).
NOT_OFFERED = ("QTT_ONBOX", "QTT_OS")
_ACTIVATE_ROLES = ["Tenant Owner"]


def _tenant() -> str:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."), frappe.PermissionError)
	require_tenant_membership(tenant)
	return tenant


def _is_owner(tenant: str) -> bool:
	return frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": frappe.session.user, "status": "active"},
							   "tenant_role") == "Tenant Owner"


def _app(product: dict, tenant: str) -> dict:
	sub = subscription_service.get_current_subscription(tenant, product.product_key)
	on = bool(sub and sub.status in OPEN_SUBSCRIPTION_STATUSES)
	return {
		"key": product.product_key, "kind": "app", "name": product.display_name, "about": product.description,
		"highlights": [x.strip() for x in (product.get("highlights") or "").splitlines() if x.strip()],
		"icon": product.icon, "status": "active" if on else None, "included": True,
	}


@frappe.whitelist(methods=["GET"])
def catalog() -> dict:
	"""All of QTT OS for this business: the apps first (each included — on, or one tap to turn on), then the managed
	services. Everyone in the business may look; only the owner turns things on or orders (can_activate)."""
	tenant = _tenant()
	fields = ["product_key", "display_name", "description", "icon"] + (["highlights"] if frappe.get_meta("QTT Product").has_field("highlights") else [])
	products = [p for p in frappe.get_all("QTT Product", filters={"status": "active"}, fields=fields)
				if p.product_key != SERVICES and (p.product_key not in NOT_OFFERED or subscription_service.get_current_subscription(tenant, p.product_key))]
	products.sort(key=lambda p: (APP_ORDER.index(p.product_key) if p.product_key in APP_ORDER else len(APP_ORDER), p.display_name or ""))
	items = [_app(p, tenant) for p in products]
	if "qtt_services" in frappe.get_installed_apps():
		from qtt_services.api.shop import explore_items

		items += explore_items(tenant)
	return {"items": items, "can_activate": _is_owner(tenant), "included": True}


@frappe.whitelist(methods=["POST"])
def activate(product: str) -> dict:
	"""Turn on an app this business hasn't opened yet (the owner). Every app comes with QTT OS: no plan to choose, no
	invoice — free until the free-use limits, then the one plan. → {status: "active"}"""
	from qtt_platform import house

	tenant = _tenant()
	require_tenant_role(tenant, _ACTIVATE_ROLES)
	if product in (SERVICES,) + NOT_OFFERED or not frappe.db.exists("QTT Product", {"name": product, "status": "active"}):
		frappe.throw(_("That app isn't available."))
	house.ensure_included(tenant)
	from qtt_platform.api.saas_admin import _grant_owner_initial_role

	_grant_owner_initial_role(tenant, product)
	write_audit_event("app_turned_on_by_owner", tenant=tenant, product=product)
	from qtt_platform.realtime import notify_users, tenant_users

	notify_users(tenant_users(tenant), tenant=tenant, reason="app_assigned")  # everyone's apps refresh
	return {"status": "active"}
