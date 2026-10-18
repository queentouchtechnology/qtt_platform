"""
QTT Studio as a product (after_migrate, idempotent): the QTT Product row with its roles, and the three plans — created
once; prices, limits and trial days are then edited in Desk (QTT Plan) and never overwritten here.
"""

import frappe

from qtt_platform.product.registry import register_product
from qtt_platform.studio import rules


def register() -> None:
	if not frappe.db.table_exists("QTT Product"):
		return
	current = frappe.db.get_value("QTT Product", rules.PRODUCT, ["display_name", "description"], as_dict=True) or {}
	register_product(
		rules.PRODUCT,
		display_name=current.get("display_name") or "QTT Studio",
		app_name="qtt_platform",
		description=current.get("description") or (
			"Make anything your business needs with AI: posts, documents, logos, flyers, photos, Shorts and pages — in your "
			"brand, saved to one library every app uses."),
		roles=[{"role_key": r, "role_name": r} for r in rules.ROLES],
	)
	for code, name, price, features in rules.PLANS:
		if frappe.db.exists("QTT Plan", {"product": rules.PRODUCT, "plan_code": code}):
			continue
		plan = frappe.get_doc({"doctype": "QTT Plan", "plan_code": code, "product": rules.PRODUCT, "display_name": name,
							   "base_price": price, "billing_period": "monthly", "trial_days": rules.TRIAL_DAYS, "is_public": 1})
		for key, value in features.items():
			plan.append("features", {"feature_key": key, "limit_value": str(value)})
		plan.insert(ignore_permissions=True)
	frappe.db.commit()
