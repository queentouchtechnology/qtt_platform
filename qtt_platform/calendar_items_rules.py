"""
The one Calendar (every role) — the rules, pure (no Frappe; tests/test_calendar_items.py). The API is api/calendar.py.

Every app adds its own dated things through the hook `qtt_calendar_sources` (a function (who, frm, to) → items) and
decides there what this person may see — the platform never names a product. One item:

  {key, layer, title, start, end?, all_day?, subtitle?, status?, tone?, icon?, color?, screen?, event?}

  layer    events (meetings) · posts (social, articles, newsletters) · reminders (renewals, expiries) · people (leave,
           holidays, birthdays)
  screen   the app screen that opens it (an assistant screen id); event = a team calendar event (opens the event)
  tone     info · success · warning · danger — the status's colour

An app may add layers of its own (hook `qtt_calendar_layers`: a function → {key: {label, color, icon}}); they come
after the built-in ones and can never replace one (merge_layers).
"""

from datetime import date, datetime, timedelta

LAYERS = {
	"events": {"label": "Events", "color": "#1A55F0", "icon": "event"},
	"posts": {"label": "Posts", "color": "#7C3AED", "icon": "campaign"},
	"reminders": {"label": "Reminders", "color": "#F59E0B", "icon": "alarm"},
	"people": {"label": "People", "color": "#16A34A", "icon": "people"},
}
TONES = ("info", "success", "warning", "danger")
MAX_DAYS = 100


def _iso(v) -> str | None:
	if v is None or v == "":
		return None
	if isinstance(v, datetime):
		return v.strftime("%Y-%m-%d %H:%M:%S")
	if isinstance(v, date):
		return v.strftime("%Y-%m-%d")
	return str(v).replace("T", " ")[:19]


def merge_layers(extra: list[dict] | None) -> dict:
	"""The built-in layers plus each app's own: a key must be a short lower-case word, never a built-in one, with a label."""
	out = dict(LAYERS)
	for group in extra or ():
		for key, v in (group or {}).items():
			if not isinstance(v, dict) or key in out or not str(key).replace("_", "").isalpha() or not str(key).islower():
				continue
			label = str(v.get("label") or "").strip()
			if not label:
				continue
			out[key] = {"label": label[:40], "color": str(v.get("color") or "#64748B")[:20], "icon": str(v.get("icon") or "event")[:40]}
	return out


def clean(item: dict, layers: dict | None = None) -> dict | None:
	"""One source's item checked and filled in; None when it can't be shown (no title, start or known layer)."""
	layers = layers or LAYERS
	if not isinstance(item, dict):
		return None
	layer, start, title = item.get("layer"), _iso(item.get("start")), str(item.get("title") or "").strip()
	if layer not in layers or not start or not title:
		return None
	all_day = bool(item.get("all_day")) or len(start) == 10
	end = _iso(item.get("end"))
	out = {
		"key": str(item.get("key") or f"{layer}:{title}:{start}"), "layer": layer, "title": title[:140],
		"start": start if not all_day else start[:10], "end": (end[:10] if all_day else end) if end else None, "all_day": all_day,
		"subtitle": str(item.get("subtitle") or "")[:200] or None, "status": str(item.get("status") or "")[:40] or None,
		"tone": item.get("tone") if item.get("tone") in TONES else None, "icon": str(item.get("icon") or layers[layer]["icon"])[:40],
		"color": item.get("color") or layers[layer]["color"], "screen": item.get("screen") or None, "event": item.get("event") or None,
	}
	for k in ("location", "meeting_url", "response", "organizer"):
		if item.get(k):
			out[k] = item[k]
	return out


def sort_key(item: dict):
	# a day's all-day things first, then by time, then by title
	return (item["start"][:10], 0 if item["all_day"] else 1, item["start"], item["title"].lower())


def layer_summary(items: list[dict], available: set[str] | None = None, layers: dict | None = None) -> list[dict]:
	"""The layer chips: each layer this person has (its sources answered), with how many items it has now."""
	have = set(available or ()) | {i["layer"] for i in items}
	return [{"key": k, **v, "count": sum(1 for i in items if i["layer"] == k)} for k, v in (layers or LAYERS).items() if k in have]


def window(frm: datetime | None, to: datetime | None) -> tuple[datetime, datetime]:
	"""The asked dates, checked: start before end, at most MAX_DAYS."""
	if not frm or not to or to <= frm:
		raise ValueError("Choose a start and an end date.")
	if to - frm > timedelta(days=MAX_DAYS):
		raise ValueError(f"Choose dates up to {MAX_DAYS} days apart.")
	return frm, to


def birthdays(people: list[tuple[str, date]], frm: date, to: date) -> list[tuple[str, date]]:
	"""(name, date of birth) → (name, this window's birthday) — 29 February is the 28th in other years."""
	out = []
	for name, dob in people:
		if not dob:
			continue
		for year in range(frm.year, to.year + 1):
			try:
				d = dob.replace(year=year)
			except ValueError:
				d = date(year, 2, 28)
			if frm <= d <= to:
				out.append((name, d))
	return out
