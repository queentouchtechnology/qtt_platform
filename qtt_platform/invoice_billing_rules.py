"""
Apps QTT Admin assigns to a paying business, billed by invoice — the rules (pure; tested without a bench).

Access starts at once; each period is an invoice due in DUE_DAYS, paid with Pay now. The next
invoice comes RENEW_DAYS before the paid time runs out; unpaid GRACE_DAYS after it, the app is
suspended — and paying turns it straight back on. (Managed services follow the same pattern:
qtt_services/selfserve_rules.next_step.)
"""

import calendar
from datetime import date, timedelta

DUE_DAYS = 7
RENEW_DAYS = 3
GRACE_DAYS = 7
MONTHS = {"monthly": 1, "yearly": 12}


def months_for(billing_period: str | None) -> int:
	return MONTHS.get((billing_period or "monthly").lower(), 1)


def add_months(d: date, months: int) -> date:
	m = d.month - 1 + months
	y, m = d.year + m // 12, m % 12 + 1
	return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def paid_through(paid_until: date | None, today: date, months: int) -> date:
	"""After a payment: the paid time continues from where it ended (or from today if it had run out)."""
	start = max(today, paid_until) if paid_until else today
	return add_months(start, months)


def next_step(*, status: str, price: float, paid_until: date | None, has_open_invoice: bool,
			  cancelling: bool, today: date) -> str | None:
	"""One of 'invoice', 'suspend', or None (nothing to do today)."""
	if status not in ("trialing", "active", "past_due", "suspended") or not paid_until or not price or price <= 0:
		return None
	if status != "suspended" and has_open_invoice and today > paid_until + timedelta(days=GRACE_DAYS):
		return "suspend"
	if not has_open_invoice and not cancelling and today >= paid_until - timedelta(days=RENEW_DAYS):
		return "invoice"
	return None


def line(product: str, plan: str, start: date, months: int, price: float) -> dict:
	end = add_months(start, months) - timedelta(days=1)
	return {"description": f"{product} — {plan}, {start:%d %b %Y} to {end:%d %b %Y}", "amount": float(price)}
