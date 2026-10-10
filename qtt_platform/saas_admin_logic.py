"""
QTT Admin → SaaS: plan input rules, trial extension and revenue maths.
Pure (no frappe) so it can be unit-tested without a bench; the saving and
querying live in api/saas_admin.py.
"""

from __future__ import annotations

import re
from datetime import date, timedelta


class SaasInputError(ValueError):
	"""Message is shown to the platform owner as-is."""


BILLING_PERIODS = ("monthly", "yearly")
_PLAN_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_]{1,29}$")
_FEATURE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.]{1,59}$")
MAX_TRIAL_EXTENSION_DAYS = 90


def _number(value, label: str, *, lo: float = 0, hi: float = 10_000_000, integer: bool = False):
	try:
		number = int(str(value).strip()) if integer else float(str(value).strip())
	except (TypeError, ValueError) as exc:
		raise SaasInputError(f"{label} must be a number.") from exc
	if not lo <= number <= hi:
		raise SaasInputError(f"{label} must be between {lo:g} and {hi:g}.")
	return number


def clean_plan(plan: dict, *, is_new: bool) -> dict:
	"""Whitelisted, normalised plan fields. plan_code/product only matter
	for a new plan — they never change afterwards (subscriptions and
	signup links refer to them)."""
	name = str(plan.get("display_name") or "").strip()
	if not 2 <= len(name) <= 80:
		raise SaasInputError("Give the plan a name (2–80 characters).")
	period = str(plan.get("billing_period") or "monthly").strip().lower()
	if period not in BILLING_PERIODS:
		raise SaasInputError("Billing period must be monthly or yearly.")
	clean = {
		"display_name": name,
		"base_price": round(_number(plan.get("base_price", 0), "Price"), 2),
		"billing_period": period,
		"trial_days": _number(plan.get("trial_days", 0), "Trial days", hi=365, integer=True),
		"is_public": 1 if str(plan.get("is_public")).lower() in ("1", "true", "yes") else 0,
		"features": clean_features(plan.get("features") or []),
	}
	if is_new:
		code = str(plan.get("plan_code") or "").strip().upper()
		if not _PLAN_CODE.match(code):
			raise SaasInputError("Plan codes use capital letters, digits and underscores, e.g. GROWTH.")
		product = str(plan.get("product") or "").strip()
		if not product:
			raise SaasInputError("Choose the product this plan is for.")
		clean.update({"plan_code": code, "product": product})
	return clean


def clean_features(features) -> list[dict]:
	"""[{feature_key, limit_value}] — keys unique, values kept as text
	(the entitlement engine stores them as strings: '10', '1', '0')."""
	rows, seen = [], set()
	for row in features:
		key = str((row or {}).get("feature_key") or "").strip().lower()
		if not key:
			continue
		if not _FEATURE_KEY.match(key):
			raise SaasInputError(f"Feature keys use lowercase letters, digits, dots or underscores: {key}")
		if key in seen:
			raise SaasInputError(f"Feature listed twice: {key}")
		seen.add(key)
		value = str((row or {}).get("limit_value") if (row or {}).get("limit_value") is not None else "").strip()
		if not value or len(value) > 40:
			raise SaasInputError(f"Give {key} a value (a number, or 1/0 for on/off).")
		rows.append({"feature_key": key, "limit_value": value})
	return rows


def billing_changed(before: dict, after: dict) -> bool:
	"""Price or period changes need a new payment-gateway plan (Razorpay
	plans can't be edited)."""
	return float(before.get("base_price") or 0) != float(after.get("base_price") or 0) or (
		before.get("billing_period") or "monthly"
	) != (after.get("billing_period") or "monthly")


def extended_trial(*, status: str, trial_end, linked_to_gateway: bool, days, today: date) -> tuple[str, date]:
	"""(new status, new trial end) for "extend trial by N days".
	- trialing: push trial_end out by N days.
	- suspended because an unlinked trial expired: restart as trialing
	  until today + N.
	Gateway-linked trials are refused: the payment gateway owns their
	trial and the nightly reconcile would undo a local change."""
	days = _number(days, "Days", lo=1, hi=MAX_TRIAL_EXTENSION_DAYS, integer=True)
	if linked_to_gateway:
		raise SaasInputError("This trial is managed by the payment gateway (Razorpay); extend it there.")
	end = _as_date(trial_end)
	if status == "trialing":
		return "trialing", max(end or today, today) + timedelta(days=days)
	if status == "suspended" and end is not None:
		return "trialing", today + timedelta(days=days)
	raise SaasInputError("Only trials (or trials that just expired) can be extended.")


def _as_date(value) -> date | None:
	if value in (None, ""):
		return None
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def monthly_value(price, period: str, items=()) -> float:
	"""Recurring value per month: plan price (yearly ÷ 12) plus add-ons."""
	base = float(price or 0)
	if period == "yearly":
		base /= 12
	addons = sum(float(i.get("unit_price") or 0) * int(i.get("quantity") or 0) for i in items or ())
	return round(base + addons, 2)


def revenue_summary(subscriptions: list[dict]) -> dict:
	"""subscriptions: current rows {product, status, base_price,
	billing_period, items}. MRR counts paying ones (active, past_due);
	trials are shown separately as potential revenue."""
	mrr = 0.0
	at_risk = 0.0
	trial_value = 0.0
	by_product: dict[str, float] = {}
	counts = {"active": 0, "trialing": 0, "past_due": 0}
	for s in subscriptions:
		value = monthly_value(s.get("base_price"), s.get("billing_period") or "monthly", s.get("items") or ())
		status = s.get("status")
		if status in counts:
			counts[status] += 1
		if status in ("active", "past_due"):
			mrr += value
			by_product[s.get("product") or ""] = round(by_product.get(s.get("product") or "", 0) + value, 2)
			if status == "past_due":
				at_risk += value
		elif status == "trialing":
			trial_value += value
	return {
		"mrr": round(mrr, 2),
		"arr": round(mrr * 12, 2),
		"at_risk_mrr": round(at_risk, 2),
		"trial_mrr": round(trial_value, 2),
		"mrr_by_product": by_product,
		"counts": counts,
	}


# --------------------------------------------------------------------------
# QTT Admin home: one ranked "needs attention" list
# --------------------------------------------------------------------------
_LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}
_KIND_ORDER = {"server": 0, "setup": 1, "payment": 2, "trial": 3, "approval": 4}


def attention_items(*, servers=(), trials=(), past_due=(), approvals=(), setup_errors=(), today_str: str) -> list[dict]:
	"""Everything a QTT admin should look at, most urgent first. Each item:
	{level, kind, title, area, target} plus facts the app turns into a
	translated sentence (product, days, count, status) and, where the server
	wrote one, a raw `detail`. `area` is the admin page the app opens,
	`target` the record in it."""
	items = []
	for s in servers:
		level = "critical" if s["status"] in ("critical", "offline") else "warning"
		items.append({"level": level, "kind": "server", "title": s["title"], "status": s["status"],
					  "detail": s.get("problems") or None, "area": "servers", "target": s["key"]})
	for p in past_due:
		items.append({"level": "critical", "kind": "payment", "title": p.get("tenant_name") or p["tenant"],
					  "product": p["product"], "area": "customers", "target": p["tenant"]})
	for t in trials:
		days = _days_between(today_str, t.get("trial_end"))
		level = "warning" if days is not None and days <= 2 else "info"
		items.append({"level": level, "kind": "trial", "title": t.get("tenant_name") or t["tenant"],
					  "product": t["product"], "days": days, "area": "customers", "target": t["tenant"]})
	for e in setup_errors:
		items.append({"level": "critical", "kind": "setup", "title": e.get("tenant_name") or e["tenant"],
					  "product": e["product"], "detail": (e.get("error") or "")[:160] or None,
					  "area": "customers", "target": e["tenant"]})
	if approvals:
		items.append({"level": "warning", "kind": "approval", "title": approvals[0].get("title") or "",
					  "count": len(approvals), "area": "marketing", "target": None})
	return sorted(items, key=lambda i: (_LEVEL_ORDER.get(i["level"], 9), _KIND_ORDER.get(i["kind"], 9),
										 i["days"] if i.get("days") is not None else 99, (i["title"] or "").lower()))


def _days_between(today_str: str, date_str) -> int | None:
	from datetime import date

	try:
		return (date.fromisoformat(str(date_str)[:10]) - date.fromisoformat(today_str[:10])).days
	except (TypeError, ValueError):
		return None
