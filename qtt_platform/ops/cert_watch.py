"""
QTT Admin › certificate watch: the HTTPS certificates of QTT's live hosts (QTT Ops Settings › Certificates to watch,
one host per line). api/servers.check_certs reads each certificate every 6 hours; this decides what that means.

Added 12 Nov 2026. Renewal usually works on its own; this is for when it quietly doesn't (certbot on the n8n server
had been failing every day for months on old names — nobody would have noticed a live one failing among them).
Telegram as the expiry gets close (at the warning, 7, 3, 1 days and expired) — not every check — and once for a
certificate that can't be read twice in a row; "fine again" when it's renewed or fixed.

Pure (no frappe).
"""

from __future__ import annotations

import re

STEPS = (7, 3, 1, 0)  # days left at which a reminder goes out after the first warning
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def parse_hosts(text: str | None) -> list[str]:
	"""One host per line; 'https://x/…' and '# notes' are fine; duplicates and junk dropped."""
	out = []
	for line in (text or "").splitlines():
		h = line.split("#", 1)[0].strip().lower()
		h = re.sub(r"^https?://", "", h).split("/", 1)[0].split(":", 1)[0]
		if h and HOST_RE.match(h) and h not in out:
			out.append(h)
	return out[:200]


def level(days: int | None, error: str | None, fails: int, warn_days: int) -> str:
	"""ok | warning | critical for one host."""
	if error:
		return "critical" if fails >= 2 else "ok"  # one failed read can be the network
	if days is None:
		return "ok"
	if days <= 3:
		return "critical"
	return "warning" if days <= warn_days else "ok"


def _bucket(days: int, warn_days: int) -> int | None:
	"""Which reminder step `days` is in (None = not close yet)."""
	if days > warn_days:
		return None
	if days < 0:
		return -1
	steps = [s for s in STEPS if days <= s]
	return min(steps) if steps else warn_days


def step(prev: dict | None, *, host: str, days: int | None, error: str | None, warn_days: int) -> tuple[dict, str | None]:
	"""(new state, Telegram text or None) after one check of `host`."""
	prev = prev or {}
	if error:
		fails = int(prev.get("fails") or 0) + 1
		state = {**prev, "fails": fails, "error": error[:160]}
		alert = f"🔴 Certificate problem: {host} — {error[:160]}. Browsers will show a warning." if fails == 2 else None
		return state, alert
	was_failing = int(prev.get("fails") or 0) >= 2
	bucket = _bucket(days, warn_days) if days is not None else None
	state = {"days": days, "fails": 0, "error": None, "bucket": bucket}
	if bucket is None:
		was_bad = was_failing or prev.get("bucket") is not None
		return state, (f"✅ Certificate fine again: {host} ({days} days left)." if was_bad else None)
	if bucket == prev.get("bucket") and not was_failing:
		return state, None
	if days < 0:
		return state, f"🔴 Certificate EXPIRED: {host} — browsers block the site. Renew it now."
	icon = "🔴" if days <= 3 else "🟠"
	return state, f"{icon} Certificate for {host} expires in {days} day{'s' if days != 1 else ''} and hasn't renewed yet."


def problems(hosts: list[str], states: dict, warn_days: int) -> list[dict]:
	"""For QTT Admin's Needs attention — shaped like a server item so the app shows it without an update."""
	out = []
	for h in hosts:
		st = states.get(h) or {}
		lvl = level(st.get("days"), st.get("error"), int(st.get("fails") or 0), warn_days)
		if lvl == "ok":
			continue
		detail = (f"Certificate can't be read: {st['error']}" if st.get("error")
				  else "Certificate expired." if st["days"] < 0 else f"Certificate expires in {st['days']} days.")
		out.append({"key": None, "title": h, "status": lvl, "problems": detail})
	return out
