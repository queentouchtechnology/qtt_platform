"""
Push device tokens (Firebase Cloud Messaging) for every QTT app user — not
tied to any product. The app calls `register` after each sign-in and when
Firebase rotates the token, and `unregister` on sign-out.

A token belongs to whoever registered it most recently (signing in as
someone else on the same phone moves it). Only a SHA-256 of the token is
indexed; the token itself is kept because sending needs it, and only
System Managers can read the table.

Senders use `tokens_for(users)`; dead tokens reported by FCM are removed
with `forget(tokens)`. Devices not seen for 120 days are pruned daily.
"""

import hashlib

import frappe
from frappe import _

from qtt_platform.tenant.context import resolve_active_tenant

DEVICE = "QTT Push Device"
PLATFORMS = ("android", "ios", "web", "windows", "macos", "linux")
STALE_DAYS = 120


def token_hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def _clean_token(token) -> str:
	token = (token or "").strip()
	if not token or len(token) > 4096:
		frappe.throw(_("Invalid device token."))
	return token


def _require_login() -> str:
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required."), frappe.PermissionError)
	return frappe.session.user


@frappe.whitelist(methods=["POST"])
def register(token: str, platform: str, device_name: str | None = None, app_version: str | None = None) -> dict:
	user = _require_login()
	token = _clean_token(token)
	if platform not in PLATFORMS:
		frappe.throw(_("Invalid platform."))
	h = token_hash(token)
	try:
		tenant = resolve_active_tenant(user)
	except Exception:
		tenant = None
	values = {
		"user": user,
		"token": token,
		"token_hash": h,
		"platform": platform,
		"device_name": (device_name or "")[:140],
		"app_version": (app_version or "")[:40],
		"tenant": tenant,
		"last_seen_at": frappe.utils.now_datetime(),
	}
	name = frappe.db.get_value(DEVICE, {"token_hash": h})
	if name:
		doc = frappe.get_doc(DEVICE, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": DEVICE, **values}).insert(ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def unregister(token: str) -> dict:
	user = _require_login()
	name = frappe.db.get_value(DEVICE, {"token_hash": token_hash((token or "").strip()), "user": user})
	if name:
		frappe.delete_doc(DEVICE, name, ignore_permissions=True, force=True)
	return {"ok": True}


def tokens_for(users: list[str] | str, platforms: tuple[str, ...] = ("android", "ios", "web")) -> list[dict]:
	"""[{user, token, platform}] for sending (FCM reaches android/ios/web only)."""
	users = [users] if isinstance(users, str) else list(users)
	if not users:
		return []
	return frappe.get_all(DEVICE, filters={"user": ["in", users], "platform": ["in", list(platforms)]},
						  fields=["user", "token", "platform"])


def forget(tokens: list[str]) -> None:
	"""Drop tokens FCM says are dead (UNREGISTERED / NOT_FOUND)."""
	for t in tokens:
		name = frappe.db.get_value(DEVICE, {"token_hash": token_hash(t)})
		if name:
			frappe.delete_doc(DEVICE, name, ignore_permissions=True, force=True)


def prune_stale() -> None:
	cutoff = frappe.utils.add_days(frappe.utils.now_datetime(), -STALE_DAYS)
	frappe.db.delete(DEVICE, {"last_seen_at": ["<", cutoff]})
