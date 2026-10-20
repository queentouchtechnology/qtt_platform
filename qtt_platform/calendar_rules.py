"""
Office Pulse Calendar (PROJ-0016 C1) — the rules, pure (no Frappe; tests/test_calendar.py): repeating events, who sees
an event, reminders, and calendar files (.ics) for invitations and the subscription feed.
"""

import re
from datetime import date, datetime, timedelta

REPEATS = ("", "daily", "weekdays", "weekly", "monthly", "yearly")
RESPONSES = ("needs", "yes", "no", "maybe")
MAX_OCCURRENCES = 500


def _add_months(d: datetime, n: int) -> datetime | None:
	y, m = divmod(d.month - 1 + n, 12)
	try:
		return d.replace(year=d.year + y, month=m + 1)
	except ValueError:
		return None  # e.g. the 31st in a shorter month: that month has no occurrence


def occurrences(start: datetime, end: datetime, repeat: str, until: date | None, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]]:
	"""The event's occurrences that overlap [frm, to): (start, end) pairs."""
	length = max(end - start, timedelta(0))
	out, i, k = [], 0, 0
	last = datetime.combine(until, datetime.max.time()) if until else None
	cur = start
	while cur is not None and k < 5000 and len(out) < MAX_OCCURRENCES:
		k += 1
		if cur >= to or (last and cur > last):
			break
		if cur + length > frm or (length == timedelta(0) and cur >= frm):
			if not (repeat == "weekdays" and cur.weekday() >= 5):
				out.append((cur, cur + length))
		if not repeat:
			break
		i += 1
		if repeat in ("daily", "weekdays"):
			cur = start + timedelta(days=i)
		elif repeat == "weekly":
			cur = start + timedelta(weeks=i)
		elif repeat == "monthly":
			nxt = None
			while nxt is None and i < 1200:
				nxt = _add_months(start, i)
				if nxt is None:
					i += 1
			cur = nxt
		elif repeat == "yearly":
			nxt = None
			while nxt is None and i < 400:
				try:
					nxt = start.replace(year=start.year + i)
				except ValueError:  # 29 February
					i += 1
			cur = nxt
		else:
			break
	return out


def visible(event: dict, user: str, attendees: list[str]) -> bool:
	"""Team events: everyone in the business; private ones: the organiser and the people invited."""
	return event.get("visibility") == "team" or event.get("organizer") == user or user in attendees


def due_reminders(occ_start: datetime, remind_minutes: int, now: datetime, window_minutes: int = 5) -> bool:
	"""Is it time to remind for an occurrence (checked every few minutes)?"""
	if remind_minutes is None or remind_minutes < 0:
		return False
	at = occ_start - timedelta(minutes=remind_minutes)
	return at <= now < at + timedelta(minutes=window_minutes)


# ---- calendar files ----------------------------------------------------------------------------------------------------
def _esc(t) -> str:
	return re.sub(r"([,;\\])", r"\\\1", str(t or "")).replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
	out, b = [], line.encode("utf-8")
	while len(b) > 74:
		cut = 74
		while cut > 0 and (b[cut] & 0xC0) == 0x80:  # never split a character
			cut -= 1
		out.append(b[:cut].decode("utf-8"))
		b = b" " + b[cut:]
	out.append(b.decode("utf-8"))
	return "\r\n".join(out)


def _dt(d: datetime, all_day: bool) -> str:
	return d.strftime("%Y%m%d") if all_day else d.strftime("%Y%m%dT%H%M%S")


RRULE = {"daily": "FREQ=DAILY", "weekdays": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "weekly": "FREQ=WEEKLY", "monthly": "FREQ=MONTHLY", "yearly": "FREQ=YEARLY"}


def ics_event(*, uid: str, title: str, start: datetime, end: datetime, all_day: bool = False, location: str = "", notes: str = "",
			  url: str = "", repeat: str = "", until: date | None = None, organizer: tuple[str, str] | None = None,
			  attendees: list[tuple[str, str, str]] | None = None, tz: str = "Asia/Kolkata", sequence: int = 0, stamp: datetime | None = None,
			  cancelled: bool = False) -> list[str]:
	"""One VEVENT (lines). attendees: (email, name, response)."""
	part = {"yes": "ACCEPTED", "no": "DECLINED", "maybe": "TENTATIVE"}
	tzp = "" if all_day else f";TZID={tz}"
	val = ";VALUE=DATE" if all_day else ""
	end = end if not all_day else (end if end.date() > start.date() else start + timedelta(days=1))
	lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{(stamp or datetime.utcnow()).strftime('%Y%m%dT%H%M%SZ')}", f"SEQUENCE:{sequence}",
			 f"DTSTART{tzp}{val}:{_dt(start, all_day)}", f"DTEND{tzp}{val}:{_dt(end, all_day)}", f"SUMMARY:{_esc(title)}"]
	if repeat in RRULE:
		lines.append("RRULE:" + RRULE[repeat] + (f";UNTIL={until.strftime('%Y%m%d')}T235959Z" if until else ""))
	if location:
		lines.append(f"LOCATION:{_esc(location)}")
	if notes or url:
		lines.append(f"DESCRIPTION:{_esc((notes or '') + (chr(10) + url if url else ''))}")
	if url:
		lines.append(f"URL:{url}")
	if organizer:
		lines.append(f"ORGANIZER;CN={_esc(organizer[1])}:mailto:{organizer[0]}")
	for email, name, resp in attendees or []:
		lines.append(f"ATTENDEE;CN={_esc(name)};ROLE=REQ-PARTICIPANT;PARTSTAT={part.get(resp, 'NEEDS-ACTION')};RSVP=TRUE:mailto:{email}")
	if cancelled:
		lines.append("STATUS:CANCELLED")
	lines.append("END:VEVENT")
	return lines


def ics_calendar(events: list[list[str]], *, name: str = "QTT OS", method: str = "PUBLISH", tz: str = "Asia/Kolkata") -> str:
	lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Queen Touch Technology//QTT OS//EN", "CALSCALE:GREGORIAN", f"METHOD:{method}",
			 f"X-WR-CALNAME:{_esc(name)}", f"X-WR-TIMEZONE:{tz}"]
	for e in events:
		lines += e
	lines.append("END:VCALENDAR")
	return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def parse_when(text: str | None) -> datetime | None:
	"""'2026-10-21 10:30' / '2026-10-21T10:30:00' / '2026-10-21' → datetime (None when empty or wrong)."""
	t = str(text or "").strip().replace("T", " ")
	for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
		try:
			return datetime.strptime(t[: len(datetime(2000, 1, 1).strftime(fmt))], fmt)
		except ValueError:
			continue
	return None
