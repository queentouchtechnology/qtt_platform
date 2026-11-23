"""
QTT Studio as a product (after_migrate, idempotent): the QTT Product row with its roles, and its one internal entry
(qtt_platform.app_plans) — Studio comes with QTT OS.
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
	# Studio comes with QTT OS (the one plan, PROJ-0024): one internal entry; the old Starter / Growth / Pro are gone.
	from qtt_platform import app_plans

	app_plans.seed(rules.PRODUCT, rules.FEATURES, "QTT Studio — with QTT OS")
	frappe.db.commit()
