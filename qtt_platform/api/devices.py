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


@frappe.whitelist(methods=["POST"])
def send_test() -> dict:
	"""A test notification to the caller's own phones and browsers (Account › Notifications › Send me a test).
	Tapping it opens Account. → {sent, devices, ready}: ready false = push isn't set up on the server yet."""
	from qtt_platform import push

	user = _require_login()
	devices = len(tokens_for(user))
	if not push.enabled():
		return {"sent": 0, "devices": devices, "ready": False}
	sent = push.notify(user, title=_("QTT OS notifications work"), body=_("Tap to open your account."), screen="account",
					   data={"kind": "test"})
	return {"sent": sent, "devices": devices, "ready": True}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def push_worker_config():
	"""For the web app's notification worker (website/static/firebase-messaging-sw.js, at the site's root): a script
	setting `self.QTT_PUSH` to the Firebase web values from QTT App Settings (public), or null when not set."""
	import json

	from werkzeug.wrappers import Response

	from qtt_platform import app_config_logic

	c = app_config_logic.push_config(frappe.get_cached_doc("QTT App Settings").as_dict()) or {}
	web = c.get("web")
	cfg = {"apiKey": web["api_key"], "appId": web["app_id"], "projectId": c["project_id"], "messagingSenderId": c["sender_id"]} if web else None
	return Response(f"self.QTT_PUSH = {json.dumps(cfg)};\n", mimetype="application/javascript", headers={"Cache-Control": "public, max-age=300"})
