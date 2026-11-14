"""
Free use (PROJ-0024): every business can use all 8 apps without a plan until one simple limit per app is reached;
then one plan for everything. Pure rules here (tested in tests/test_free_use.py); the counts come from each app
(hook `qtt_free_use`: (tenant) -> {app key: how many so far}), the limits from Desk › QTT App Settings › Free use.

  APPS            the 8 apps: key, name, what is counted
  limits_from     the limits set in Desk (0 = no limit for that app)
  status          what the app shows: each app's used / limit / left, and whether the gate is up
  blocked         would adding `n` more go past the limit? (the gate)

QTT's own workspaces and subscribed businesses are never limited; with free use switched off nobody is stopped.
"""

#: (key, name, what is counted) — in the order Home shows them.
APPS = (
	("hr", "HR & staff", "staff"),
	("erp", "ERP", "bills"),
	("website", "Website", "websites"),
	("store", "Store", "orders"),
	("whatsapp", "WhatsApp", "chats"),
	("social", "Social media", "posts"),
	("articles", "Articles & newsletters", "articles"),
	("studio", "Studio", "designs"),
)
KEYS = tuple(k for k, _, _ in APPS)

#: The owner's Standard set (14 Nov 2026) — also the Desk defaults.
DEFAULT_LIMITS = {"hr": 10, "erp": 50, "website": 1, "store": 20, "whatsapp": 100, "social": 10, "articles": 3, "studio": 10}


def _int(v) -> int:
	try:
		return max(0, int(v or 0))
	except (TypeError, ValueError):
		return 0


def limits_from(settings: dict | None) -> dict:
	"""The limits from Desk's fields free_limit_<key>; a field Desk doesn't have yet → the default. 0 = no limit."""
	settings = settings or {}
	return {k: _int(settings[f"free_limit_{k}"]) if f"free_limit_{k}" in settings and settings[f"free_limit_{k}"] is not None
			else DEFAULT_LIMITS[k] for k in KEYS}


def limited(enabled: bool, subscribed: bool) -> bool:
	"""Whether limits apply at all: free use on, and the business isn't on the plan (or QTT's own)."""
	return bool(enabled) and not subscribed


def status(used: dict | None, limits: dict, *, enabled: bool = True, subscribed: bool = False) -> dict:
	"""{limited, gate, reached: [keys], apps: [{key, label, unit, used, limit, left, reached}]} — `left` is None when
	there is no limit (0, free use off, or subscribed)."""
	used = used or {}
	on = limited(enabled, subscribed)
	apps = []
	for key, label, unit in APPS:
		n, limit = _int(used.get(key)), _int(limits.get(key))
		capped = on and limit > 0
		apps.append({"key": key, "label": label, "unit": unit, "used": n, "limit": limit if capped else None,
					 "left": max(0, limit - n) if capped else None, "reached": capped and n >= limit})
	reached = [a["key"] for a in apps if a["reached"]]
	return {"limited": on, "gate": bool(reached), "reached": reached, "apps": apps}


def blocked(key: str, used: int, limits: dict, *, enabled: bool = True, subscribed: bool = False, adding: int = 1) -> bool:
	"""True when adding `adding` more of `key` would go past its limit (the gate shows instead)."""
	if key not in KEYS or not limited(enabled, subscribed):
		return False
	limit = _int(limits.get(key))
	return limit > 0 and _int(used) + max(1, _int(adding)) > limit


def plan_prices(settings: dict | None) -> dict:
	"""The one plan's prices from Desk (₹1,999 a month, ₹19,990 a year by default)."""
	settings = settings or {}

	def money(field, default):
		try:
			v = float(settings.get(field) or 0)
		except (TypeError, ValueError):
			v = 0
		return v if v > 0 else default

	return {"monthly": money("one_plan_monthly", 1999.0), "yearly": money("one_plan_yearly", 19990.0)}
