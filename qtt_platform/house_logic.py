"""
The house gate's rules — pure, no Frappe (tested in tests/test_house_logic.py).

Queen Touch Technology's own workspace (QTT Tenant › House workspace) uses
every product through one gate: no trials, no plan limits, no invoices.
Every other business keeps the normal subscription gate.
"""

#: A "limit" the house never reaches (counted features: employees, stores, inboxes…).
HOUSE_LIMIT = 1_000_000

#: House subscriptions run until this date (never expire, never renew).
HOUSE_PERIOD_END = "2099-12-31"


def _number(raw):
	try:
		return int(str(raw).strip())
	except (TypeError, ValueError):
		return None


def house_features(plan_features: list[dict], counted: set[str]) -> dict:
	"""Every feature any plan of the product has, at its best:
	counted features (a usage resolver is registered) → HOUSE_LIMIT;
	flags and other numbers → the highest value any plan gives;
	text values → the first non-empty one.

	plan_features: [{feature_key, limit_value}] across all the product's plans."""
	out: dict = {}
	for row in plan_features:
		key = row.get("feature_key")
		if not key:
			continue
		if key in counted:
			out[key] = HOUSE_LIMIT
			continue
		value = _number(row.get("limit_value"))
		if value is None:
			text = str(row.get("limit_value") or "").strip()
			if text and key not in out:
				out[key] = text
			continue
		current = out.get(key)
		if not isinstance(current, int) or value > current:
			out[key] = value
	return out


def billable_lines(lines: list[dict], *, house: bool) -> list[dict]:
	"""A Managed Service order's fee lines (setup, monthly, hosting). The house
	pays nothing for QTT's own services. A domain bought for it is a real
	outside cost — the shop adds that line after this, so it still stays."""
	return [] if house else lines


def apply_limits(features: dict, rows: list[dict], product: str) -> dict:
	"""Desk › QTT Tenant › House limits: the house's own limits for this product over its "everything" features.
	rows: [{product, limit_key, limit_value}]; an empty value means no limit (counted features → HOUSE_LIMIT)."""
	out = dict(features)
	for row in rows or []:
		key = str(row.get("limit_key") or "").strip()
		if row.get("product") != product or not key:
			continue
		raw = str(row.get("limit_value") or "").strip()
		number = _number(raw)
		out[key] = HOUSE_LIMIT if raw == "" else (number if number is not None else raw)
	return out


def marketing_caps(rows: list[dict]) -> dict:
	"""House limits for the Marketing assistant (product QTT_SERVICES, keys marketing_*) → {posts, articles, newsletters,
	pages, series: number}; a key not set, or set empty, has no cap."""
	out = {}
	for row in rows or []:
		key = str(row.get("limit_key") or "").strip()
		number = _number(row.get("limit_value"))
		if row.get("product") == "QTT_SERVICES" and key.startswith("marketing_") and number is not None:
			out[key[len("marketing_"):]] = number
	return out
