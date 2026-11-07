"""Website watch (pure rules, no Frappe): which addresses QTT watches and when a change deserves an alert.

QTT Ops Settings › Website watch lists one site per line — "Label | https://address" or just the address. Every
5 minutes servers.check_sites() fetches each; a site counts as down only after DOWN_AFTER failed checks in a row (one
slow answer is not an outage), and the ops Telegram hears once when it goes down and once when it is back.
"""

DOWN_AFTER = 2


def parse_sites(text: str | None) -> list[dict]:
	"""[{label, url}] from the settings text; blank lines and lines starting with # are skipped, duplicates dropped."""
	out, seen = [], set()
	for raw in (text or "").splitlines():
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		label, _, url = line.rpartition("|") if "|" in line else ("", "", line)
		url, label = url.strip(), label.strip()
		if not url.startswith(("http://", "https://")) or url in seen:
			continue
		seen.add(url)
		out.append({"label": label or _host(url), "url": url})
	return out


def _host(url: str) -> str:
	return url.split("://", 1)[1].split("/", 1)[0]


def step(prev: dict | None, *, ok: bool, problem: str | None, label: str, down_after: int = DOWN_AFTER) -> tuple[dict, str | None]:
	"""The site's new state and the alert to send (None = say nothing). State: {fails, down, problem}."""
	prev = prev or {}
	was_down = bool(prev.get("down"))
	if ok:
		state = {"fails": 0, "down": False, "problem": None}
		return state, (f"{label} is back up." if was_down else None)
	fails = int(prev.get("fails") or 0) + 1
	down = was_down or fails >= down_after
	state = {"fails": fails, "down": down, "problem": problem}
	if down and not was_down:
		return state, f"{label} is down — {problem or 'no answer'}."
	return state, None


def describe(status_code: int | None, error: str | None) -> tuple[bool, str | None]:
	"""(ok, problem) from one check: only an HTTP 200 counts as up."""
	if error:
		return False, error
	if status_code == 200:
		return True, None
	return False, f"HTTP {status_code}"


def down_sites(sites: list[dict], states: dict) -> list[dict]:
	"""For QTT Admin's Needs attention — shaped like a server item so the app shows it without an update."""
	out = []
	for s in sites:
		st = states.get(s["url"]) or {}
		if st.get("down"):
			out.append({"key": None, "title": s["label"], "status": "offline", "problems": st.get("problem") or "no answer"})
	return out
