"""How long things take — the pure rules (QTT Admin › Servers › Speed; qtt_platform.api.perf).

Every API call's time is noted (no data, only: which call, how long, its status, from the app or not). Each hour is
kept as a small histogram per call, so p50 / p95 / p99 for any stretch of time can be worked out exactly (to about 10%)
by adding hours together — percentiles of hours can't be averaged, histograms can.
"""

import json
import math
import re
from urllib.parse import unquote

# Bucket i holds times up to FIRST_MS × RATIO^i (5 ms … about 2 minutes, each bucket 20% wider than the one before).
FIRST_MS = 5.0
RATIO = 1.2
BUCKETS = 56

# Not people waiting on a screen: servers, webhooks and robots reporting in.
_NOT_APP_ENDPOINTS = re.compile(r"(\.ingest$|webhook|\.shots_due$|\.site_shots_due$|^ping$|\.screens$)")
_ROBOT_AGENTS = re.compile(r"(n8n|curl|python|requests|axios|node-fetch|go-http|wget|uptime|kuma|bot|spider|crawl|httpx|java/)", re.I)


def endpoint(path: str | None) -> str | None:
	"""/api/method/x.y → "x.y"; /api/resource/CRM%20Lead/… → "resource:CRM Lead"; anything not an API call → None."""
	path = unquote(str(path or "")).split("?", 1)[0]
	m = re.match(r"^/api/(?:v\d+/)?method/([\w.]+)", path)
	if m:
		return m.group(1)[:140]
	m = re.match(r"^/api/(?:v\d+/)?(resource|document|doctype)/([^/]+)", path)
	if m:
		return f"resource:{m.group(2)}"[:140]
	return None


def source(name: str, user: str | None, agent: str | None) -> str:
	""""app" — a signed-in person in the app or Desk; "other" — servers, webhooks, robots, signed-out calls."""
	if _NOT_APP_ENDPOINTS.search(name or ""):
		return "other"
	if not user or user == "Guest":
		return "other"
	if _ROBOT_AGENTS.search(agent or ""):
		return "other"
	return "app"


def bucket(ms: float) -> int:
	"""The histogram bucket for a time in milliseconds."""
	if ms <= FIRST_MS:
		return 0
	return min(BUCKETS - 1, math.ceil(math.log(ms / FIRST_MS, RATIO)))


def bucket_ms(i: int) -> int:
	"""The upper edge of bucket i — what a percentile in that bucket is reported as (never flattering)."""
	return int(round(FIRST_MS * RATIO**i))


def pack(name: str, ms: float, status: int | str, src: str) -> str:
	"""One noted call, as kept in Redis until its hour is rolled up."""
	return f"{src}\t{name}\t{int(round(ms))}\t{status}"


def unpack(line) -> tuple[str, str, int, str] | None:
	if isinstance(line, bytes):
		line = line.decode("utf-8", "replace")
	parts = str(line).split("\t")
	if len(parts) != 4:
		return None
	try:
		return parts[0], parts[1], int(parts[2]), parts[3]
	except ValueError:
		return None


def is_error(status: str) -> bool:
	return str(status)[:1] == "5"


def roll(lines) -> dict[tuple[str, str], dict]:
	"""An hour of noted calls → {(source, call): {"calls", "errors", "hist"}}, plus ("app"/"other"/"screen", "*") for all."""
	out: dict[tuple[str, str], dict] = {}
	for raw in lines:
		row = unpack(raw)
		if not row:
			continue
		src, name, ms, status = row
		for key in ((src, name), (src, "*")):
			r = out.setdefault(key, {"calls": 0, "errors": 0, "copies": 0, "hist": {}})
			r["calls"] += 1
			if is_error(status):
				r["errors"] += 1
			if status == "copy":
				r["copies"] += 1
			b = bucket(ms)
			r["hist"][b] = r["hist"].get(b, 0) + 1
	return out


def merge(hists) -> dict[int, int]:
	"""Hours added together."""
	total: dict[int, int] = {}
	for h in hists:
		if isinstance(h, str):
			h = json.loads(h or "{}")
		for k, v in (h or {}).items():
			total[int(k)] = total.get(int(k), 0) + int(v)
	return total


def percentile(hist: dict, p: float) -> int | None:
	"""The p-th percentile (0–100) of a histogram, in ms; None when empty."""
	n = sum(hist.values())
	if not n:
		return None
	rank = max(1, math.ceil(n * p / 100))
	seen = 0
	for i in sorted(hist):
		seen += hist[i]
		if seen >= rank:
			return bucket_ms(i)
	return bucket_ms(max(hist))


def summary(hist: dict) -> dict:
	return {"calls": sum(hist.values()), "p50": percentile(hist, 50), "p95": percentile(hist, 95), "p99": percentile(hist, 99)}


def change(before: int | None, after: int | None) -> int | None:
	"""Percent faster (+) or slower (−) after; None when either side has nothing."""
	if not before or after is None:
		return None
	return int(round((before - after) * 100 / before))


def clean_screens(samples, limit: int = 50) -> list[tuple[str, int, bool]]:
	"""The app's screen times → (screen, ms until something real showed, from a saved copy). Junk is dropped."""
	if isinstance(samples, str):
		try:
			samples = json.loads(samples or "[]")
		except ValueError:
			return []
	out = []
	for s in (samples or [])[:limit]:
		if not isinstance(s, dict):
			continue
		name = re.sub(r"[^\w.:-]", "", str(s.get("screen") or ""))[:100]
		try:
			ms = int(s.get("ms"))
		except (TypeError, ValueError):
			continue
		if not name or ms < 0 or ms > 600_000:
			continue
		out.append((name, ms, bool(s.get("copy"))))
	return out
