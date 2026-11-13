"""
The main dashboard's two server-built parts (pure rules — tested in tests/test_home_tiles.py):

  tiles    "Your apps": one tile per thing the business uses — each app adds its own with the hook
           `qtt_home_tiles` (user, tenant) -> [{key, label, icon, open: {kind, target}, status?, badge?, order?}].
           A business suite can add several (Website, Store, WhatsApp, Social media, Articles).
  numbers  "Today so far": a few live numbers — hook `qtt_home_numbers` (user, tenant) ->
           [{key, value, label, trend?, order?}].

An app returns [] when the person can't use it (never raises for "no access"), so a tile is never a dead end.
"""

MAX_NUMBERS = 4
OPEN_KINDS = ("product", "screen", "section", "url")


def _int(v) -> int:
	try:
		return max(0, int(v or 0))
	except (TypeError, ValueError):
		return 0


def tiles(items: list) -> list[dict]:
	"""Valid tiles only, one per key (the first wins), by order then label."""
	seen, out = set(), []
	for t in items or []:
		if not isinstance(t, dict):
			continue
		key, label = str(t.get("key") or "").strip(), str(t.get("label") or "").strip()
		o = t.get("open") if isinstance(t.get("open"), dict) else {}
		if not key or not label or key in seen or o.get("kind") not in OPEN_KINDS or not o.get("target"):
			continue
		seen.add(key)
		out.append({"key": key, "label": label, "icon": str(t.get("icon") or "apps"),
					"open": {"kind": o["kind"], "target": str(o["target"])},
					"status": str(t.get("status") or "")[:40] or None, "args": t.get("args") if isinstance(t.get("args"), dict) else {},
					"badge": _int(t.get("badge")), "tone": t.get("tone") if t.get("tone") in ("info", "warning", "danger", "success") else "info",
					"order": _int(t.get("order")) or 50})
	out.sort(key=lambda t: (t["order"], t["label"].lower()))
	return out


def numbers(items: list) -> list[dict]:
	"""At most MAX_NUMBERS numbers that have a value, by order."""
	out, seen = [], set()
	for n in items or []:
		if not isinstance(n, dict) or n.get("value") in (None, "") or not n.get("label") or n.get("key") in seen:
			continue
		seen.add(n.get("key"))
		out.append({"key": str(n.get("key")), "value": str(n["value"]), "label": str(n["label"]),
					"trend": n.get("trend") if isinstance(n.get("trend"), (int, float)) else None, "order": _int(n.get("order")) or 50})
	out.sort(key=lambda n: n["order"])
	return out[:MAX_NUMBERS]


def money_short(amount: float, symbol: str = "₹") -> str:
	"""₹950 · ₹18.4K · ₹2.3L · ₹1.2Cr (Indian short form)."""
	a = float(amount or 0)
	for size, suffix in ((1e7, "Cr"), (1e5, "L"), (1e3, "K")):
		if abs(a) >= size:
			v = f"{a / size:.1f}".rstrip("0").rstrip(".")
			return f"{symbol}{v}{suffix}"
	return f"{symbol}{a:.0f}"


def trend(today: float, before: float) -> int | None:
	"""Percent change against the same time before (None when there's nothing to compare)."""
	if not before:
		return None
	return round((today - before) * 100 / before)
