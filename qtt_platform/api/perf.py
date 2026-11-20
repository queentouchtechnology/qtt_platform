"""
QTT Admin › Servers › Speed: how long the app waits — every API call's time on the server, and how long each app screen
takes until something real shows.

- **Noted on every API call** (hooks before_request / after_request): which call, how long, its status, and whether a
  signed-in person in the app made it ("app") or a server, webhook or robot ("other"). Only that — never the data, the
  person or the business. One Redis write per call, kept 2 days.
- **The app's screens** post their times in small batches (`screens`).
- **Each hour** (`roll_up`) becomes one QTT Perf Hour row per call with a time histogram, so p50 / p95 / p99 over any
  days can be worked out exactly (perf_rules). Rows are kept 90 days.
- **Before and after**: `set_baseline` keeps a stretch of days as the baseline; `report` compares the last days with it.

Rules (pure) in qtt_platform/perf_rules.py.
"""

import json
import time
from datetime import datetime, timedelta

import frappe
from frappe import _

from qtt_platform import perf_rules as rules
from qtt_platform.tenant.guards import require_platform_owner

DT = "QTT Perf Hour"
RAW_KEEP_SECONDS = 2 * 24 * 3600
KEEP_DAYS = 90
BASELINE = "qtt_perf_baseline"


def _raw_key(hour: datetime) -> str:
	return f"qtt_perf|{hour:%Y%m%d%H}"


def _utc_hour(dt: datetime | None = None) -> datetime:
	return (dt or datetime.utcnow()).replace(minute=0, second=0, microsecond=0)


def _push(lines: list[str]) -> None:
	"""Noted times go to this hour's Redis list (one round trip)."""
	cache = frappe.cache()
	key = cache.make_key(_raw_key(_utc_hour()))
	pipe = cache.pipeline(transaction=False)
	pipe.rpush(key, *lines)
	pipe.expire(key, RAW_KEEP_SECONDS)
	pipe.execute()


# --------------------------------------------------------------------------
# hooks: every request
# --------------------------------------------------------------------------
def start() -> None:
	"""before_request: the clock starts."""
	frappe.local.qtt_perf_t0 = time.perf_counter()


def record(response=None, request=None) -> None:
	"""after_request: an API call's time is noted. Never raises — timing must never break a request."""
	t0 = getattr(frappe.local, "qtt_perf_t0", None)
	if t0 is None:
		return
	frappe.local.qtt_perf_t0 = None
	try:
		name = rules.endpoint(getattr(request, "path", None))
		if not name:
			return
		ms = (time.perf_counter() - t0) * 1000
		user = getattr(getattr(frappe.local, "session", None), "user", None)
		agent = request.headers.get("User-Agent") if request is not None else None
		status = getattr(response, "status_code", 0) or 0
		_push([rules.pack(name, ms, status, rules.source(name, user, agent))])
	except Exception:
		pass


# --------------------------------------------------------------------------
# app → server: screen times
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def screens(samples=None) -> dict:
	"""The app's screen times, in batches: [{screen, ms (until something real showed), copy (shown from a saved copy)}].
	Only the screen's name and the time are kept — QTT Admin › Servers › Speed."""
	if frappe.session.user in (None, "Guest"):
		frappe.throw(_("Login required."), frappe.PermissionError)
	clean = rules.clean_screens(samples)
	if clean:
		_push([rules.pack(name, ms, "copy" if copy else "fresh", "screen") for name, ms, copy in clean])
	return {"accepted": len(clean)}


# --------------------------------------------------------------------------
# scheduler
# --------------------------------------------------------------------------
def roll_up() -> None:
	"""Hourly: each finished hour of noted times → QTT Perf Hour rows (one per call, plus "*" for all)."""
	cache = frappe.cache()
	now = _utc_hour()
	for back in range(1, 48):
		hour = now - timedelta(hours=back)
		key = _raw_key(hour)
		if not cache.exists(key):
			continue
		if not frappe.db.exists(DT, {"hour": hour}):
			rows = rules.roll(cache.lrange(key, 0, -1) or [])
			stamp = frappe.utils.now_datetime()
			values = []
			for (src, call), r in rows.items():
				s = rules.summary(r["hist"])
				values.append((frappe.generate_hash(length=12), stamp, stamp, "Administrator", "Administrator", hour, src, call[:140],
							   r["calls"], r["errors"], r["copies"], s["p50"], s["p95"], json.dumps(r["hist"], separators=(",", ":"))))
			if values:
				frappe.db.bulk_insert(DT, ["name", "creation", "modified", "owner", "modified_by", "hour", "source", "call", "calls", "errors",
										   "copies", "p50", "p95", "hist"], values)
			frappe.db.commit()
		cache.delete_value(key)


def purge() -> None:
	"""Daily: hours older than 90 days go."""
	frappe.db.delete(DT, {"hour": ["<", datetime.utcnow() - timedelta(days=KEEP_DAYS)]})


# --------------------------------------------------------------------------
# QTT Admin › Servers › Speed
# --------------------------------------------------------------------------
def _window(start: datetime, end: datetime) -> dict[tuple[str, str], dict]:
	"""(source, call) → merged histogram, calls, errors, copies over [start, end)."""
	out: dict[tuple[str, str], dict] = {}
	for r in frappe.get_all(DT, filters=[["hour", ">=", start], ["hour", "<", end]], fields=["source", "call", "calls", "errors", "copies", "hist"],
							limit=0):
		a = out.setdefault((r.source, r.call), {"hists": [], "errors": 0, "copies": 0})
		a["hists"].append(r.hist)
		a["errors"] += r.errors or 0
		a["copies"] += r.copies or 0
	return {k: {**rules.summary(rules.merge(v["hists"])), "errors": v["errors"], "copies": v["copies"]} for k, v in out.items()}


def _baseline() -> tuple[datetime, datetime] | None:
	raw = frappe.db.get_default(BASELINE)
	if not raw:
		return None
	try:
		b = json.loads(raw)
		return datetime.fromisoformat(b["from"]), datetime.fromisoformat(b["to"])
	except (ValueError, KeyError, TypeError):
		return None


def _compare(now: dict, base: dict | None) -> dict:
	return {
		"now": now,
		"before": base,
		"p50_change": rules.change((base or {}).get("p50"), now.get("p50")),
		"p95_change": rules.change((base or {}).get("p95"), now.get("p95")),
	}


@frappe.whitelist(methods=["GET"])
def report(days=1) -> dict:
	"""QTT Admin › Servers › Speed: the last `days` days (hours in UTC) against the baseline — all app calls, app
	screens and each call's p50 / p95 / p99, slowest first. Platform Owners only."""
	require_platform_owner()
	days = max(1, min(int(days or 1), 30))
	end = _utc_hour() + timedelta(hours=1)
	now = _window(end - timedelta(days=days), end)
	b = _baseline()
	base = _window(*b) if b else {}

	def rows(src: str, limit: int) -> list[dict]:
		items = [(call, v) for (s, call), v in now.items() if s == src and call != "*"]
		items.sort(key=lambda x: (x[1]["p95"] or 0) * min(x[1]["calls"], 50), reverse=True)  # what people wait on most
		return [{"name": call, **_compare(v, base.get((src, call)))} for call, v in items[:limit]]

	first = frappe.db.sql(f"select min(hour) from `tab{DT}`")[0][0]
	return {
		"days": days,
		"since": first.isoformat() if first else None,
		"baseline": {"from": b[0].isoformat(), "to": b[1].isoformat()} if b else None,
		"app": _compare(now.get(("app", "*"), rules.summary({})), base.get(("app", "*"))),
		"screens": _compare(now.get(("screen", "*"), rules.summary({})), base.get(("screen", "*"))),
		"calls": rows("app", 40),
		"screen_rows": rows("screen", 40),
		"other": now.get(("other", "*"), rules.summary({})),
	}


@frappe.whitelist(methods=["POST"])
def set_baseline(start: str | None = None, end: str | None = None) -> dict:
	"""Keep a stretch of time as the baseline (default: everything noted so far, up to this hour) — the "before" every
	later report compares with. Platform Owners only."""
	require_platform_owner()
	first = frappe.db.sql(f"select min(hour) from `tab{DT}`")[0][0]
	s = datetime.fromisoformat(start) if start else first
	e = datetime.fromisoformat(end) if end else _utc_hour()
	if not s or e <= s:
		frappe.throw(_("Nothing noted yet — wait an hour or two, then try again."))
	frappe.db.set_default(BASELINE, json.dumps({"from": s.isoformat(), "to": e.isoformat()}))
	frappe.db.commit()
	return {"from": s.isoformat(), "to": e.isoformat()}
