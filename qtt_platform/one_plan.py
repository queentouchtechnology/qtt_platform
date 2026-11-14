"""
The one plan for all 8 apps (PROJ-0024 task 4): a product of its own (QTT_OS) with a monthly and a yearly plan. Its prices
come from Desk › QTT App Settings › Free use and the one plan (₹1,999 a month, ₹19,990 a year) and are copied onto the two
QTT Plans whenever they're registered or someone subscribes. Being on it lifts every free-use limit
(qtt_platform.api.free_use.is_subscribed); it is the only subscription still billed (invoice_billing.renew_daily).
"""

import frappe

from qtt_platform import free_use as rules
from qtt_platform.house import ONE_PLAN_PRODUCT
from qtt_platform.product.registry import register_product

PLANS = (("OS_MONTHLY", "QTT OS — monthly", "monthly"), ("OS_YEARLY", "QTT OS — yearly", "yearly"))


def _prices() -> dict:
	try:
		return rules.plan_prices(frappe.get_cached_doc("QTT App Settings").as_dict())
	except Exception:
		return rules.plan_prices({})


def plan_name(period: str) -> str | None:
	code = "OS_YEARLY" if period == "yearly" else "OS_MONTHLY"
	return frappe.db.get_value("QTT Plan", {"product": ONE_PLAN_PRODUCT, "plan_code": code}, "name")


def sync_prices() -> None:
	"""Desk's prices onto the two plans (no-op when they already match)."""
	prices = _prices()
	for code, _name, period in PLANS:
		name = frappe.db.get_value("QTT Plan", {"product": ONE_PLAN_PRODUCT, "plan_code": code}, ["name", "base_price"], as_dict=True)
		want = prices["yearly" if period == "yearly" else "monthly"]
		if name and float(name.base_price or 0) != want:
			frappe.db.set_value("QTT Plan", name.name, "base_price", want)


def register() -> None:
	"""after_migrate (idempotent): the QTT_OS product and its two plans."""
	if not frappe.db.table_exists("QTT Product"):
		return
	register_product(ONE_PLAN_PRODUCT, display_name="QTT OS — all 8 apps", app_name="qtt_platform", icon="apps",
					 description="One plan for every app: HR & staff, ERP, Website, Store, WhatsApp, Social media, "
								 "Articles & newsletters and Studio — no limits.",
					 roles=[{"role_key": "Owner", "role_name": "Owner"}])
	prices = _prices()
	for code, name, period in PLANS:
		if frappe.db.exists("QTT Plan", {"product": ONE_PLAN_PRODUCT, "plan_code": code}):
			continue
		frappe.get_doc({"doctype": "QTT Plan", "plan_code": code, "product": ONE_PLAN_PRODUCT, "display_name": name,
						"base_price": prices["yearly" if period == "yearly" else "monthly"], "billing_period": period,
						"trial_days": 0, "is_public": 1}).insert(ignore_permissions=True)
	sync_prices()
	frappe.db.commit()
