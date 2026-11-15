"""
Free use (PROJ-0024): every business can use all 8 apps without a plan until one simple limit per app is reached;
then one plan for everything — with fair use each month and top-ups (owner, 15 Nov 2026). Pure rules here (tested in
tests/test_free_use.py); the counts come from each app (hooks `qtt_free_use` and `qtt_plan_use`), every amount and
price from Desk › QTT App Settings › Free use and the one plan.

  APPS / FREE_PERIOD   the free amounts: what is counted, and how — "at a time" (what exists now; removing one frees a
                       place) or "in total" (everything ever made; for trying, they never reset)
  limits_from          the free amounts set in Desk (0 = no limit for that app)
  status / blocked     the free amounts' gate
  PLAN_ITEMS           the plan's fair use: monthly amounts (reset on the plan's date each month) and "at a time" ones
  plan_limits_from     the plan's amounts set in Desk (0 = unlimited)
  plan_status / plan_blocked   the plan's use this month, with top-ups added
  month_window         the plan month a day falls in (from the plan's start date)
  TOPUPS / topups_from the packs (what each adds, its price) from Desk
  plan_prices          the one plan's prices

QTT's own workspaces are never limited; with free use switched off nobody is stopped.
"""

from datetime import date, timedelta

#: (key, name, what is counted) — in the order Home shows them.
APPS = (
	("hr", "HR & staff", "staff"),
	("erp", "ERP", "bills"),
	("website", "Website", "websites"),
	("store", "Store", "orders"),
	("whatsapp", "WhatsApp", "customers"),
	("social", "Social media", "posts"),
	("articles", "Articles", "articles"),
	("newsletters", "Newsletters", "newsletters"),
	("studio", "Studio", "designs"),
)
KEYS = tuple(k for k, _, _ in APPS)

#: How each free amount counts: what exists now ("at_a_time") or everything ever made ("in_total").
FREE_PERIOD = {"hr": "at_a_time", "website": "at_a_time"}

#: The owner's Standard set (14 Nov 2026; newsletters 15 Nov) — also the Desk defaults.
DEFAULT_LIMITS = {"hr": 10, "erp": 50, "website": 1, "store": 20, "whatsapp": 100, "social": 10, "articles": 3,
				  "newsletters": 2, "studio": 10}

#: The plan's fair use (owner, 15 Nov 2026): (key, name, unit, period). Everything not listed is unlimited on the plan
#: (bills, store orders, customers, designs, WhatsApp replies to customers).
PLAN_ITEMS = (
	("offer_messages", "Offer messages", "messages", "month"),
	("ai", "AI actions", "actions", "month"),
	("social", "Social posts", "posts", "month"),
	("articles", "Articles", "articles", "month"),
	("newsletters", "Newsletters", "newsletters", "month"),
	("hr", "Staff", "staff", "at_a_time"),
	("website", "Websites", "websites", "at_a_time"),
	("stores", "Stores", "stores", "at_a_time"),
)
PLAN_KEYS = tuple(k for k, _, _, _ in PLAN_ITEMS)
DEFAULT_PLAN_LIMITS = {"offer_messages": 1000, "ai": 500, "social": 60, "articles": 8, "newsletters": 4, "hr": 25,
					   "website": 1, "stores": 1}

#: Top-up packs (owner, 15 Nov 2026 — suggested prices, set in Desk): pack -> (name, adds to, how much, price).
#: Each is for the rest of the plan month it's bought in.
TOPUPS = {
	"messages": ("2,000 offer messages", "offer_messages", 2000, 499.0),
	"ai": ("1,000 AI actions", "ai", 1000, 299.0),
	"staff": ("25 more staff", "hr", 25, 499.0),
	"site": ("Another website or store", "website", 1, 999.0),
}

NEAR = 0.8  # "nearly used" (a heads-up, amber bars) from 80%


def _int(v) -> int:
	try:
		return max(0, int(v or 0))
	except (TypeError, ValueError):
		return 0


def _desk(settings: dict, field: str, default: int) -> int:
	return _int(settings[field]) if field in settings and settings[field] is not None else default


def limits_from(settings: dict | None) -> dict:
	"""The limits from Desk's fields free_limit_<key>; a field Desk doesn't have yet → the default. 0 = no limit."""
	settings = settings or {}
	return {k: _desk(settings, f"free_limit_{k}", DEFAULT_LIMITS[k]) for k in KEYS}


def limited(enabled: bool, subscribed: bool) -> bool:
	"""Whether the free amounts apply at all: free use on, and the business isn't on the plan (or QTT's own)."""
	return bool(enabled) and not subscribed


def status(used: dict | None, limits: dict, *, enabled: bool = True, subscribed: bool = False) -> dict:
	"""{limited, gate, reached: [keys], apps: [{key, label, unit, period, used, limit, left, reached}]} — `left` is None
	when there is no limit (0, free use off, or subscribed)."""
	used = used or {}
	on = limited(enabled, subscribed)
	apps = []
	for key, label, unit in APPS:
		n, limit = _int(used.get(key)), _int(limits.get(key))
		capped = on and limit > 0
		apps.append({"key": key, "label": label, "unit": unit, "period": FREE_PERIOD.get(key, "in_total"), "used": n,
					 "limit": limit if capped else None, "left": max(0, limit - n) if capped else None,
					 "reached": capped and n >= limit})
	reached = [a["key"] for a in apps if a["reached"]]
	return {"limited": on, "gate": bool(reached), "reached": reached, "apps": apps}


def blocked(key: str, used: int, limits: dict, *, enabled: bool = True, subscribed: bool = False, adding: int = 1) -> bool:
	"""True when adding `adding` more of `key` would go past its free amount (the gate shows instead)."""
	if key not in KEYS or not limited(enabled, subscribed):
		return False
	limit = _int(limits.get(key))
	return limit > 0 and _int(used) + max(1, _int(adding)) > limit


# ---------------------------------------------------------------- the plan's fair use


def plan_limits_from(settings: dict | None) -> dict:
	"""The plan's amounts from Desk's fields plan_limit_<key> (0 = unlimited)."""
	settings = settings or {}
	return {k: _desk(settings, f"plan_limit_{k}", DEFAULT_PLAN_LIMITS[k]) for k in PLAN_KEYS}


def _add_months(d: date, n: int) -> date:
	m = d.month - 1 + n
	y, m = d.year + m // 12, m % 12 + 1
	last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
	return date(y, m, min(d.day, last))


def month_window(start: date, today: date) -> tuple[date, date]:
	"""The plan month `today` is in: from the plan's start day each month (31 Jan → 28/29 Feb), to the day before the next.
	Before the start: the first month."""
	if today < start:
		return start, _add_months(start, 1) - timedelta(days=1)
	n = (today.year - start.year) * 12 + (today.month - start.month)
	begin = _add_months(start, n)
	if begin > today:
		n -= 1
		begin = _add_months(start, n)
	return begin, _add_months(start, n + 1) - timedelta(days=1)


def plan_status(used: dict | None, limits: dict, topups: dict | None = None) -> dict:
	"""The plan's use: {items: [{key, label, unit, period, used, limit, topup, left, near, reached}], near: [keys],
	reached: [keys]}. `limit` includes this month's top-ups; None = unlimited."""
	used, topups = used or {}, topups or {}
	items = []
	for key, label, unit, period in PLAN_ITEMS:
		base = _int(limits.get(key))
		extra = _int(topups.get(key))
		n = _int(used.get(key))
		limit = base + extra if base > 0 else None
		items.append({"key": key, "label": label, "unit": unit, "period": period, "used": n, "limit": limit, "topup": extra,
					  "left": max(0, limit - n) if limit else None, "near": bool(limit) and n >= NEAR * limit and n < limit,
					  "reached": bool(limit) and n >= limit})
	return {"items": items, "near": [i["key"] for i in items if i["near"]], "reached": [i["key"] for i in items if i["reached"]]}


def plan_blocked(key: str, used: int, limits: dict, topups: dict | None = None, adding: int = 1) -> bool:
	"""True when adding `adding` more of `key` would go past the plan's amount (with top-ups) — the top-up sheet shows."""
	if key not in PLAN_KEYS:
		return False
	base = _int(limits.get(key))
	if base <= 0:
		return False
	return _int(used) + max(1, _int(adding)) > base + _int((topups or {}).get(key))


def topups_from(settings: dict | None) -> dict:
	"""The packs with Desk's amounts and prices (topup_<pack>_amount / topup_<pack>_price): pack -> {name, adds, amount, price}."""
	settings = settings or {}
	out = {}
	for pack, (name, adds, amount, price) in TOPUPS.items():
		try:
			p = float(settings.get(f"topup_{pack}_price") or 0)
		except (TypeError, ValueError):
			p = 0
		out[pack] = {"name": name, "adds": adds, "amount": _desk(settings, f"topup_{pack}_amount", amount) or amount,
					 "price": p if p > 0 else price}
	return out


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
