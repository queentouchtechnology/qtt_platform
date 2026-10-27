"""
The house gate: Queen Touch Technology's own workspace uses every QTT OS
product through one gate. Other businesses keep the subscription gate.

Desk › QTT Tenant › "House workspace" (System Manager only). When it's on:
  - every active product is open: a subscription that never expires
    (active, no trial, period to 2099) and the owner's access to it;
  - every feature is at its best and every counted limit is unlimited
    (entitlement engine);
  - trials never expire and Razorpay reconciliation leaves it alone;
  - Managed Services ordered by the house are not charged.
New products join automatically (after every migrate).

Rules (pure, tested): qtt_platform.house_logic.
"""

import frappe

from qtt_platform import house_logic

SUB = "QTT Product Subscription"


def is_house(tenant: str | None) -> bool:
	if not tenant:
		return False
	cache = getattr(frappe.local, "qtt_house", None)  # per request (frappe.local is a werkzeug Local: no __dict__)
	if cache is None:
		cache = frappe.local.qtt_house = {}
	if tenant not in cache:
		cache[tenant] = bool(frappe.db.get_value("QTT Tenant", tenant, "is_house"))
	return cache[tenant]


def house_tenants() -> list[str]:
	if not frappe.db.has_column("QTT Tenant", "is_house"):
		return []
	return frappe.get_all("QTT Tenant", filters={"is_house": 1}, pluck="name")


def limits(tenant: str) -> list[dict]:
	"""Desk › QTT Tenant › House limits (empty: everything, no limits)."""
	return frappe.get_all("QTT House Limit", filters={"parent": tenant, "parenttype": "QTT Tenant"},
						  fields=["product", "limit_key", "limit_value"]) if frappe.db.table_exists("QTT House Limit") else []


def entitlements(product: str, tenant: str | None = None) -> dict:
	"""The house's features for a product: everything, unlimited — except the limits set for this house in Desk."""
	from qtt_platform.exceptions import FeatureNotConfigured
	from qtt_platform.usage.registry import get_usage_resolver

	plans = frappe.get_all("QTT Plan", filters={"product": product}, pluck="name")
	rows = frappe.get_all("QTT Plan Feature", filters={"parent": ["in", plans or [""]], "parenttype": "QTT Plan"},
						  fields=["feature_key", "limit_value"])
	counted = set()
	for key in {r.feature_key for r in rows if r.feature_key}:
		try:
			get_usage_resolver(product, key)
			counted.add(key)
		except FeatureNotConfigured:
			pass
	features = house_logic.house_features(rows, counted)
	return house_logic.apply_limits(features, limits(tenant), product) if tenant else features


def _house_plan(product: str) -> str | None:
	"""The product's top plan (only a label for the house — features come from entitlements())."""
	plans = frappe.get_all("QTT Plan", filters={"product": product}, fields=["name", "base_price"], order_by="base_price desc, creation desc")
	return plans[0].name if plans else None


def ensure_house(tenant: str) -> list[str]:
	"""Opens every active product for the house workspace. Safe to run again. Returns what changed."""
	from qtt_platform.api.saas_admin import _grant_owner_initial_role
	from qtt_platform.audit import write_audit_event
	from qtt_platform.subscription import service as subscription_service
	from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES

	changed = []
	t = frappe.db.get_value("QTT Tenant", tenant, ["status", "trial_ends_on"], as_dict=True)
	if t and (t.status != "active" or t.trial_ends_on):
		frappe.db.set_value("QTT Tenant", tenant, {"status": "active", "trial_ends_on": None})
		changed.append("workspace active")
	for product in frappe.get_all("QTT Product", filters={"status": "active"}, pluck="name"):
		sub = subscription_service.get_current_subscription(tenant, product)
		if not sub or sub.status not in OPEN_SUBSCRIPTION_STATUSES:
			plan = _house_plan(product)
			if not plan:
				continue
			# One product failing (e.g. its workspace set-up) never stops the products after it, and leaves no
			# subscription behind without its pointer — the next run would add yet another one.
			frappe.db.savepoint("house_product")
			try:
				sub = subscription_service.create_subscription(tenant, product, plan)
			except Exception:
				frappe.db.rollback(save_point="house_product")
				frappe.log_error(title=f"qtt_platform.house: {product} for {tenant}")
				continue
			changed.append(f"{product}: added")
		if sub.status != "active" or sub.trial_end or str(sub.current_period_end) != house_logic.HOUSE_PERIOD_END:
			before = sub.status
			sub.save(ignore_permissions=True)  # keep_open() sets it always-on
			write_audit_event("subscription_house", tenant=tenant, product=product, target_doctype=SUB, target_name=sub.name,
							  metadata={"from": before, "to": "active", "source": "house"})
			changed.append(f"{product}: always on")
		granted = _grant_owner_initial_role(tenant, product)
		if granted:
			changed.append(f"{product}: {granted}")
	return changed


def ensure_all() -> None:
	"""after_migrate: new products join every house workspace."""
	for tenant in house_tenants():
		try:
			ensure_house(tenant)
		except Exception:
			frappe.log_error(title=f"qtt_platform.house: ensure_house failed for {tenant}")


def keep_open(doc, method=None) -> None:
	"""doc_events: QTT Product Subscription validate — a house subscription is always on,
	whichever path writes it (signup, QTT Admin, plan change, trial / Razorpay jobs).
	Cancelling stays possible: that's a deliberate choice by QTT staff."""
	if doc.status == "cancelled" or not is_house(doc.tenant):
		return
	doc.status = "active"
	doc.trial_start = doc.trial_end = None
	doc.current_period_end = house_logic.HOUSE_PERIOD_END
	doc.cancel_at_period_end = 0


def on_tenant_update(doc, method=None) -> None:
	"""doc_events: QTT Tenant on_update — switching "House workspace" on opens everything."""
	frappe.local.qtt_house = {}  # forget this request's cached answer
	if doc.get("is_house") and (doc.has_value_changed("is_house") or doc.status != "active"):
		ensure_house(doc.name)
