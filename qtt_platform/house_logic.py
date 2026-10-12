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
