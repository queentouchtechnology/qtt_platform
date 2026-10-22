"""
Bot defence for the website enquiry door (api/enquiry.py). Pure: no Frappe; tests/test_enquiry_rules.py.

Layers, cheapest first — a person filling the form passes all of them without noticing:
  1. a hidden trap field (people leave it empty; form-filling bots don't)
  2. a signed form ticket: the page asks for one when the form shows (`ticket`), it must come back with the
     answer, be ours (HMAC with the site's secret), at least MIN_SECONDS old (nobody types an enquiry in 3 seconds)
     and at most MAX_SECONDS old, and works once — so a bot can't post straight to the door or replay one answer
  3. the words: too many links, link markup, or the same text in every field is spam
  4. limits: per address (rate limit on the door), per email / phone a day (a repeat adds to the first lead
     instead of a new one), and a daily cap for the whole door (a flood stops at the cap; the team is told)
"""

import hashlib
import hmac
import re
import time

MIN_SECONDS = 3
MAX_SECONDS = 2 * 3600
DAILY_CAP = 150
_LINK = re.compile(r"(https?://|www\.)\S+", re.I)
_MARKUP = re.compile(r"\[url=|<a\s+href|\[link=", re.I)


def make_ticket(secret: str, now: float | None = None) -> str:
	ts = str(int(now if now is not None else time.time()))
	sig = hmac.new(secret.encode(), ts.encode(), hashlib.sha256).hexdigest()[:24]
	return f"{ts}.{sig}"


def check_ticket(ticket: str, secret: str, now: float | None = None) -> str | None:
	"""None when the ticket is good, else why it isn't ('missing', 'forged', 'too_fast', 'expired')."""
	ts, _dot, sig = str(ticket or "").partition(".")
	if not ts.isdigit() or not sig:
		return "missing"
	want = hmac.new(secret.encode(), ts.encode(), hashlib.sha256).hexdigest()[:24]
	if not hmac.compare_digest(want, sig):
		return "forged"
	age = (now if now is not None else time.time()) - int(ts)
	if age < MIN_SECONDS:
		return "too_fast"
	if age > MAX_SECONDS:
		return "expired"
	return None


def spam_reason(name: str, message: str, company: str = "") -> str | None:
	"""Why these words look like spam, or None."""
	text = f"{name} {company} {message}"
	if _MARKUP.search(text):
		return "markup"
	if len(_LINK.findall(text)) > 2:
		return "links"
	if _LINK.search(name or "") or _LINK.search(company or ""):
		return "link_in_name"
	if message and name and message.strip().lower() == name.strip().lower():
		return "same_text"
	return None
