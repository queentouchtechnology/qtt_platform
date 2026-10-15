"""
Deleting your own QTT OS account — the rules (pure: no frappe; tested without a bench).

Asked in the app (Account › Delete my account) or on the web (/delete_account, confirmed by an
email link). It waits GRACE_DAYS so the person can change their mind ("Keep my account"); then the
daily job (api/account_deletion.run_due) closes any business they own alone and anonymises them
with Frappe's Personal Data Deletion Request — every record keeps working, with their name and
email gone.
"""

from datetime import datetime, timedelta

GRACE_DAYS = 7

# Their phones, sign-ins and usage go entirely (the rest is anonymised where it stands).
DELETE_ROWS = ("QTT Push Device", "QTT Trusted Device", "QTT App Event", "QTT Assistant Answer")


def delete_on(confirmed_at: datetime) -> datetime:
	return confirmed_at + timedelta(days=GRACE_DAYS)


def is_due(confirmed_at: datetime | None, now: datetime) -> bool:
	return bool(confirmed_at) and now >= delete_on(confirmed_at)


def blockers(owned: list[dict]) -> list[str]:
	"""Businesses that stop the deletion: ones they own where other people still work.
	owned: [{"name": "Acme Bakery", "others": 3}, …] → ["Acme Bakery"]."""
	return [b["name"] for b in owned if (b.get("others") or 0) > 0]


def closes(owned: list[dict]) -> list[str]:
	"""Businesses that close with the account: ones they own alone (no one else would be left)."""
	return [b["tenant"] for b in owned if not (b.get("others") or 0)]
