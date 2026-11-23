"""
Each app's one entry since the one plan (PROJ-0024): every app comes with QTT OS — free until the free-use limits, then
the one plan for all 8 apps (product QTT_OS, qtt_platform.one_plan). The old per-app plans (Starter / Standard / Business /
Pro / Growth…, priced per app) are gone (owner, 23 Nov 2026: "no old plan presence any more").

What stays per app is one internal entry, never sold or shown: the INCLUDED plan (₹0, hidden). An app subscription must
point to a plan (QTT Product Subscription.plan), and the app's feature keys live on it (house.entitlements reads them).

  ensure(product, features, label)   the app's INCLUDED plan — made if missing; new feature keys added, set values kept
  plan_for(product)                  its name (what every app subscription uses)
  retire_old(product)                every subscription and history row moved to INCLUDED (feature keys the old plans had
                                     are added to it first, at their highest value), then the old plans deleted.
                                     Idempotent — each app runs ensure + retire_old on every migrate (its seed_plans).
"""

import frappe

INCLUDED = "INCLUDED"
PLAN = "QTT Plan"
ONE_PLAN_PRODUCT = "QTT_OS"


def plan_for(product: str) -> str | None:
	return frappe.db.get_value(PLAN, {"product": product, "plan_code": INCLUDED}, "name")


def ensure(product: str, features: dict, label: str) -> str | None:
	if product == ONE_PLAN_PRODUCT or not frappe.db.exists("QTT Product", product):
		return None
	name = plan_for(product)
	if not name:
		doc = frappe.get_doc({"doctype": PLAN, "product": product, "plan_code": INCLUDED, "display_name": label, "base_price": 0,
							  "billing_period": "monthly", "trial_days": 0, "is_public": 0,
							  "features": [{"feature_key": k, "limit_value": str(v)} for k, v in features.items()]})
		doc.insert(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc(PLAN, name)
	have = {f.feature_key for f in doc.features}
	missing = {k: v for k, v in features.items() if k not in have}
	for k, v in missing.items():
		doc.append("features", {"feature_key": k, "limit_value": str(v)})
	changed = bool(missing) or doc.base_price or doc.is_public or doc.trial_days
	doc.update({"base_price": 0, "is_public": 0, "trial_days": 0})
	if changed:
		doc.save(ignore_permissions=True)
	return name


def _higher(a: str | None, b: str | None) -> str:
	"""The bigger of two limit values ("0" = none for a switch; numbers compared as numbers)."""
	try:
		return str(max(float(a or 0), float(b or 0))).removesuffix(".0")
	except ValueError:
		return b or a or "0"


def retire_old(product: str) -> dict:
	"""Old per-app plans → gone; whatever pointed at them now points at INCLUDED. Returns what was moved and deleted."""
	included = plan_for(product)
	if not included or product == ONE_PLAN_PRODUCT:
		return {}
	old = frappe.get_all(PLAN, filters={"product": product, "name": ["!=", included]}, pluck="name")
	if not old:
		return {}
	# feature keys only the old plans had (e.g. Studio's on PRO) → on INCLUDED, at their highest value
	doc = frappe.get_doc(PLAN, included)
	have = {f.feature_key: f for f in doc.features}
	for r in frappe.get_all("QTT Plan Feature", filters={"parent": ["in", old], "parenttype": PLAN}, fields=["feature_key", "limit_value"]):
		if r.feature_key and r.feature_key not in have:
			have[r.feature_key] = doc.append("features", {"feature_key": r.feature_key, "limit_value": r.limit_value})
		elif r.feature_key and have[r.feature_key].limit_value != _higher(have[r.feature_key].limit_value, r.limit_value):
			have[r.feature_key].limit_value = _higher(have[r.feature_key].limit_value, r.limit_value)
	doc.save(ignore_permissions=True)
	moved = {}
	for doctype, fields in (("QTT Product Subscription", ("plan", "scheduled_plan")), ("QTT Subscription Event", ("from_plan", "to_plan"))):
		if not frappe.db.table_exists(doctype):
			continue
		for field in fields:
			n = frappe.db.count(doctype, {field: ["in", old]})
			if n:
				target = None if field == "scheduled_plan" else included  # a change waiting to an old plan is no change
				frappe.db.sql(f"UPDATE `tab{doctype}` SET `{field}` = %s WHERE `{field}` IN %s", (target, tuple(old)))
				moved[f"{doctype}.{field}"] = n
	for name in old:
		frappe.delete_doc(PLAN, name, ignore_permissions=True, force=True)
	from qtt_platform.audit import write_audit_event

	write_audit_event("old_app_plans_removed", target_doctype=PLAN, target_name=product, metadata={"deleted": old, "moved": moved})
	return {"deleted": old, "moved": moved}


def seed(product: str, features: dict, label: str) -> None:
	"""What each app's seed_plans does on migrate: its one INCLUDED entry, and no old plan left."""
	if ensure(product, features, label):
		retire_old(product)
