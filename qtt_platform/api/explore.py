"""
Explore QTT OS — every app and managed service in one place, for the business owner (app: Home › Explore QTT OS,
Business › Plans and billing). Each shows what it does and its plans; the owner starts an app's free trial or
chooses a plan. Managed services are ordered on their own page (qtt_services.api.shop.order).

  catalog    the apps and services, their plans and what this business has of each
  activate   start an app: its free trial (once per app) or a plan — a paid plan starts when its first
             invoice is paid (Pay now); a free plan, or QTT's own (house) business, starts at once
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from qtt_platform import explore_rules as rules
from qtt_platform import invoice_billing, invoice_billing_rules as billing_rules
from qtt_platform.audit import write_audit_event
from qtt_platform.house import is_house
from qtt_platform.subscription import service as subscription_service
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

SUB = "QTT Product Subscription"
SERVICES = "QTT_SERVICES"  # Managed Services: the home of the services, not an app of its own here
APP_ORDER = ("QTT_ORBITRA", "QTT_ONBOX", "QTT_OFFICE_PULSE", "QTT_STUDIO")
_ACTIVATE_ROLES = ["Tenant Owner"]  # starting an app is a billing decision (api/subscription.py)


def _tenant() -> str:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."), frappe.PermissionError)
	require_tenant_membership(tenant)
	return tenant


def _is_owner(tenant: str) -> bool:
	return frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": frappe.session.user, "status": "active"},
							   "tenant_role") == "Tenant Owner"


def _plans(product: str) -> list[dict]:
	"""The plans owners may choose (QTT Admin › Plans › Public), cheapest first, with their features in words."""
	out = []
	for p in frappe.get_all("QTT Plan", filters={"product": product, "is_public": 1},
							fields=["name", "plan_code", "display_name", "base_price", "billing_period", "trial_days"], order_by="base_price asc"):
		rows = frappe.get_all("QTT Plan Feature", filters={"parent": p.name, "parenttype": "QTT Plan"}, fields=["feature_key", "limit_value"])
		out.append({"plan": p.name, "code": p.plan_code, "name": p.display_name or p.plan_code, "price": float(p.base_price or 0),
					"period": p.billing_period or "monthly", "trial_days": int(p.trial_days or 0),
					"features": rules.feature_lines({r.feature_key: r.limit_value for r in rows}, product)})
	return out


def _app(product: dict, tenant: str, house: bool) -> dict:
	sub = subscription_service.get_current_subscription(tenant, product.product_key)
	sub_d = sub.as_dict() if sub else None
	has_open = bool(sub and invoice_billing.open_invoice(sub.name))
	status = rules.app_status(sub_d, has_open)
	had_before = bool(frappe.db.exists(SUB, {"tenant": tenant, "product": product.product_key}))
	plans = _plans(product.product_key)
	for p in plans:
		p["can_trial"] = not house and rules.can_trial(p["trial_days"], had_before)
	return {
		"key": product.product_key, "kind": "app", "name": product.display_name, "about": product.description,
		"highlights": [x.strip() for x in (product.get("highlights") or "").splitlines() if x.strip()],
		"icon": product.icon, "status": status,
		"plan": frappe.db.get_value("QTT Plan", sub.plan, "display_name") if sub and status else None,
		"trial_end": str(sub.trial_end) if sub and status == "trial" and sub.trial_end else None,
		"trial_days": max([p["trial_days"] for p in plans if p["can_trial"]] or [0]),
		"price_from": min([p["price"] for p in plans] or [0]), "plans": plans, "included": house,
	}


@frappe.whitelist(methods=["GET"])
def catalog() -> dict:
	"""All of QTT OS for this business: the apps first, then the managed services, each with its plans and what
	the business has of it. Everyone in the business may look; only the owner starts things (can_activate)."""
	tenant = _tenant()
	house = is_house(tenant)
	fields = ["product_key", "display_name", "description", "icon"] + (["highlights"] if frappe.get_meta("QTT Product").has_field("highlights") else [])
	products = [p for p in frappe.get_all("QTT Product", filters={"status": "active"}, fields=fields) if p.product_key != SERVICES]
	products.sort(key=lambda p: (APP_ORDER.index(p.product_key) if p.product_key in APP_ORDER else len(APP_ORDER), p.display_name or ""))
	items = [_app(p, tenant, house) for p in products]
	if "qtt_services" in frappe.get_installed_apps():
		from qtt_services.api.shop import explore_items

		items += explore_items(tenant)
	return {"items": items, "can_activate": _is_owner(tenant), "included": house}


@frappe.whitelist(methods=["POST"])
def activate(product: str, plan: str, trial=0) -> dict:
	"""Start an app on one of its public plans. trial=1: its free trial (once per app; the first invoice comes
	before the trial ends). Otherwise a paid plan waits for its first invoice (pay_url); a free plan, or QTT's own
	business, starts at once. → {status, invoice, pay_url}"""
	tenant = _tenant()
	require_tenant_role(tenant, _ACTIVATE_ROLES)
	p = frappe.db.get_value("QTT Plan", {"name": plan, "product": product, "is_public": 1},
							["name", "base_price", "billing_period", "trial_days", "display_name"], as_dict=True)
	if not p or product == SERVICES:
		frappe.throw(_("That plan isn't available. Please choose again."))
	current = subscription_service.get_current_subscription(tenant, product)
	if current and current.status in OPEN_SUBSCRIPTION_STATUSES + ("suspended",):
		frappe.throw(_("You already have this app. Change its plan in Business › Plans and billing."))
	house = is_house(tenant)
	wants_trial = str(trial).lower() in ("1", "true", "yes")
	if wants_trial and (house or not rules.can_trial(p.trial_days, bool(frappe.db.exists(SUB, {"tenant": tenant, "product": product})))):
		frappe.throw(_("The free trial was already used for this app. Choose a plan to continue."))

	sub = subscription_service.create_subscription(tenant, product, p.name)
	start = getdate(today())
	months = billing_rules.months_for(p.billing_period)
	price = float(p.base_price or 0)
	invoice = None
	if wants_trial:
		# The trial runs; renew_daily sends the first invoice 3 days before it ends.
		sub.db_set({"billing_mode": "invoice", "paid_until": sub.trial_end})
		status = "trial"
	elif house or price <= 0:
		sub.db_set({"status": "active", "trial_start": None, "trial_end": None, "current_period_start": start,
					"current_period_end": billing_rules.add_months(start, months)})
		status = "active"
	else:
		# Paid: off until the first invoice is paid — paying turns it on (invoice_billing.on_invoice_update).
		sub.db_set({"status": "suspended", "billing_mode": "invoice", "trial_start": None, "trial_end": None, "paid_until": None,
					"current_period_start": start, "current_period_end": start})
		invoice = invoice_billing.invoice_period(sub.name, start)
		status = "awaiting_payment"
	from qtt_platform.api.saas_admin import _grant_owner_initial_role

	_grant_owner_initial_role(tenant, product)
	write_audit_event("app_activated_by_owner", tenant=tenant, product=product, target_doctype=SUB, target_name=sub.name,
					  metadata={"plan": p.name, "trial": wants_trial, "invoice": invoice, "house": house})
	from qtt_platform.realtime import notify_users, tenant_users

	notify_users(tenant_users(tenant), tenant=tenant, reason="app_assigned")  # everyone's apps refresh
	pay_url = None
	if invoice:
		from qtt_platform.billing import paylink

		pay_url = paylink.payment_url(invoice)
	return {"status": status, "invoice": invoice, "pay_url": pay_url}
