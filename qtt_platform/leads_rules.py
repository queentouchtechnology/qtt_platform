"""
Leads in the Content Hub — the rules (pure, tested in tests/test_leads_rules.py). The records are Frappe CRM's own
(CRM Lead → CRM Deal, CRM Task for the next step, FCRM Note for what happened), each with the business's qtt_tenant;
qtt_platform.api.leads reads and writes them.

The owner sees five simple stages:
  New        a CRM Lead nobody has talked to yet (status New)
  Talking    a CRM Lead being talked to (any other open status)
  Quote sent a CRM Deal made when the quote goes (status Proposal/Quotation, or any open deal status)
  Won / Lost the deal closed (status Won / Lost, with Frappe CRM's lost reason)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

STAGES = ("New", "Talking", "Quote sent", "Won", "Lost")

#: Where a lead came from: the app's words → Frappe CRM's lead sources (Phone Call is created when missing).
SOURCES = {"Walk-in": "Walk In", "Phone call": "Phone Call", "WhatsApp": "WhatsApp", "Website": "Website Form", "Referral": "Reference",
		   "Other": None}

#: The owner's words for why it was lost → Frappe CRM's lost reasons.
LOST_REASONS = {
	"Price too high": "Pricing",
	"Went elsewhere": "Competition",
	"Stopped replying": "Unresponsive Prospect",
	"Other": "Other",
}

#: Remind me later: the choices on the sheet → how far ahead.
REMIND = {"2h": "In 2 hours", "tomorrow": "Tomorrow morning", "week": "Next week"}

#: A new lead nobody has called stays on To do for this long.
NEW_ON_TODO = timedelta(days=3)


class LeadError(ValueError):
	"""A message the person can act on."""


def stage(doctype: str, status: str | None) -> str:
	"""The owner's stage for a CRM Lead / CRM Deal status."""
	status = status or ""
	if doctype == "CRM Deal":
		if status == "Won":
			return "Won"
		if status == "Lost":
			return "Lost"
		return "Quote sent"
	if status == "New":
		return "New"
	if status in ("Junk", "Unqualified"):
		return "Lost"
	return "Talking"


def is_open(stage_name: str) -> bool:
	return stage_name in ("New", "Talking", "Quote sent")


def on_todo(stage_name: str, created: datetime, next_at: datetime | None, now: datetime) -> bool:
	"""To do: an open lead whose next step is due by the end of today, or a new one from the last three days with no
	next step yet (say hello)."""
	if not is_open(stage_name):
		return False
	end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=0)
	if next_at is not None:
		return next_at <= end_of_today
	return stage_name == "New" and now - created <= NEW_ON_TODO


def next_line(stage_name: str, task_title: str | None, next_at: datetime | None, now: datetime, source: str | None) -> tuple[str, bool]:
	"""The one line under a lead's name: its next step (and whether it's overdue), else what to do now."""
	if task_title:
		overdue = next_at is not None and next_at < now
		return task_title, overdue
	if stage_name == "New":
		return ("Say hello · came on {source}" if source else "Say hello"), False
	if stage_name == "Quote sent":
		return "Ask if the quote is OK", False
	if stage_name == "Talking":
		return "Plan the next step", False
	return "", False


def remind_at(choice: str, now: datetime, day: datetime | None = None) -> datetime:
	"""When a 'Remind me later' choice falls due: in 2 hours, tomorrow 9:00, next Monday 9:00, or a day picked (9:00)."""
	if choice == "2h":
		return (now + timedelta(hours=2)).replace(second=0, microsecond=0)
	if choice == "tomorrow":
		return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
	if choice == "week":
		days = 7 - now.weekday()  # next Monday
		return (now + timedelta(days=days)).replace(hour=9, minute=0, second=0, microsecond=0)
	if choice == "day":
		if day is None:
			raise LeadError("Pick a day.")
		at = day.replace(hour=9, minute=0, second=0, microsecond=0) if (day.hour, day.minute) == (0, 0) else day
		if at <= now:
			raise LeadError("Pick a day after today.")
		return at
	raise LeadError("Choose when to remind you.")


def _text(v, limit: int) -> str:
	return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def clean_phone(v) -> str | None:
	digits = re.sub(r"[^\d+]", "", str(v or ""))
	if not digits:
		return None
	if len(re.sub(r"\D", "", digits)) < 7:
		raise LeadError("Check the phone number.")
	return digits


def clean_email(v) -> str | None:
	v = str(v or "").strip().lower()
	if not v:
		return None
	if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
		raise LeadError("Check the email address.")
	return v


def clean_lead(data: dict) -> dict:
	"""A new lead from the app: a name and a phone or email; what they want, its value and where it came from optional."""
	name = _text(data.get("name"), 140)
	if not name:
		raise LeadError("Enter their name.")
	phone = clean_phone(data.get("phone"))
	email = clean_email(data.get("email"))
	if not phone and not email:
		raise LeadError("Add a phone number or an email, so you can reach them.")
	first, _, last = name.partition(" ")
	value = data.get("value")
	try:
		value = round(float(value), 2) if value not in (None, "") else None
	except (TypeError, ValueError):
		raise LeadError("Enter the value as a number.")
	if value is not None and value < 0:
		raise LeadError("Enter the value as a number.")
	source = SOURCES.get(data.get("source") or "")
	return {"first_name": first, "last_name": last or None, "mobile_no": phone, "email": email,
			"qtt_need": _text(data.get("need"), 140) or None, "annual_revenue": value, "source": source}


def clean_quote(lines, gst) -> dict:
	"""The quote's lines (name, qty, rate) and GST % → rows and totals."""
	rows = []
	for line in lines or []:
		name = _text((line or {}).get("name"), 140)
		if not name:
			continue
		try:
			qty = float((line or {}).get("qty") or 0)
			rate = float((line or {}).get("rate") or 0)
		except (TypeError, ValueError):
			raise LeadError("Enter quantity and price as numbers.")
		if qty <= 0 or rate < 0:
			raise LeadError("Enter a quantity above 0 and a price for {name}.".replace("{name}", name))
		rows.append({"name": name, "qty": qty, "rate": round(rate, 2), "amount": round(qty * rate, 2)})
	if not rows:
		raise LeadError("Add at least one thing they're buying.")
	try:
		gst = float(gst or 0)
	except (TypeError, ValueError):
		raise LeadError("Choose the GST rate.")
	if gst < 0 or gst > 28:
		raise LeadError("Choose the GST rate.")
	net = round(sum(r["amount"] for r in rows), 2)
	tax = round(net * gst / 100, 2)
	return {"rows": rows, "gst": gst, "net": net, "tax": tax, "total": round(net + tax, 2)}


def money(v: float, currency: str = "INR") -> str:
	"""₹2,10,000 (Indian grouping) / AED 1,200 — for the WhatsApp message."""
	v = round(float(v or 0), 2)
	whole, frac = f"{v:.2f}".split(".")
	neg = whole.startswith("-")
	whole = whole.lstrip("-")
	if currency == "INR" and len(whole) > 3:
		head, tail = whole[:-3], whole[-3:]
		pairs = []
		while len(head) > 2:  # lakhs and crores: pairs of digits from the right
			pairs.insert(0, head[-2:])
			head = head[:-2]
		if head:
			pairs.insert(0, head)
		whole = ",".join(pairs + [tail])
	elif len(whole) > 3:
		whole = f"{int(whole):,}"
	sign = "-" if neg else ""
	symbol = "₹" if currency == "INR" else f"{currency} "
	return f"{sign}{symbol}{whole}" + (f".{frac}" if frac != "00" else "")


def quote_message(customer: str, business: str, quote: dict, currency: str = "INR") -> str:
	"""The short WhatsApp message that carries the quote."""
	lines = [f"Hello {customer}, here is our quote:", ""]
	for r in quote["rows"]:
		qty = int(r["qty"]) if float(r["qty"]).is_integer() else r["qty"]
		lines.append(f"• {r['name']} × {qty} — {money(r['amount'], currency)}")
	if quote["tax"]:
		gst = int(quote["gst"]) if float(quote["gst"]).is_integer() else quote["gst"]
		lines.append(f"• GST {gst}% — {money(quote['tax'], currency)}")
	lines += ["", f"Total: {money(quote['total'], currency)}", "", f"Thank you — {business}"]
	return "\n".join(lines)
