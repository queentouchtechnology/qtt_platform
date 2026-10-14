"""
Push notifications from the platform itself (e.g. "a LinkedIn post is waiting for your
approval"), to every phone a user signed in on (QTT Push Device, registered by the app).

Firebase Cloud Messaging HTTP v1 with QTT's own Firebase project. Credentials: a Google
service-account JSON file whose path is in site_config.json as `qtt_fcm_service_account`
(or Onbox's `qtt_onbox_fcm_service_account` — the same project). None configured = push is
quietly off; senders always have another way to reach the person (email, the app).
"""

import json
import time

import frappe
import requests

_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_CACHE_KEY = "qtt_platform_fcm_access_token"
_DEAD = ("UNREGISTERED", "NOT_FOUND", "INVALID_ARGUMENT")


def enabled() -> bool:
	return bool(_service_account())


def notify(users: list[str] | str, *, title: str, body: str, data: dict | None = None, collapse_key: str | None = None) -> int:
	"""Sends to each of the users' phones; returns how many got it. Never raises."""
	from qtt_platform.api.devices import forget, tokens_for

	account = _service_account()
	if not account:
		return 0
	try:
		devices = tokens_for(users)
		if not devices:
			return 0
		token = _access_token(account)
		sent, dead = 0, []
		for d in devices:
			result = _send(account["project_id"], token, message(d.token, title=title, body=body, data=data or {}, collapse_key=collapse_key))
			sent += result == "ok"
			if result == "dead":
				dead.append(d.token)
		if dead:
			forget(dead)
		return sent
	except Exception:
		frappe.log_error(title="qtt_platform push failed")
		return 0


def message(device_token: str, *, title: str, body: str, data: dict, collapse_key: str | None = None) -> dict:
	"""FCM v1 message (data values must be strings). Pure."""
	m = {
		"token": device_token,
		"notification": {"title": title[:120], "body": body[:240]},
		"data": {str(k): "" if v is None else str(v) for k, v in data.items()},
		"android": {"priority": "high"},
		"apns": {"payload": {"aps": {"sound": "default"}}},
		"webpush": {"headers": {"Urgency": "high"}},
	}
	if collapse_key:
		m["android"]["collapse_key"] = collapse_key
	return {"message": m}


def _send(project_id: str, access_token: str, payload: dict) -> str:
	try:
		r = requests.post(_SEND_URL.format(project_id=project_id), json=payload, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
	except requests.RequestException:
		return "error"
	if r.status_code == 200:
		return "ok"
	try:
		status = (r.json().get("error") or {}).get("status")
	except ValueError:
		status = None
	return "dead" if r.status_code in (400, 404) and status in _DEAD else "error"


def _service_account() -> dict | None:
	path = frappe.conf.get("qtt_fcm_service_account") or frappe.conf.get("qtt_onbox_fcm_service_account")
	if not path:
		return None
	cached = getattr(frappe.local, "qtt_platform_fcm_account", None)
	if cached:
		return cached
	try:
		with open(path, encoding="utf-8") as fh:
			data = json.load(fh)
	except (OSError, ValueError):
		frappe.log_error(title="qtt_platform: FCM service account unreadable")
		return None
	frappe.local.qtt_platform_fcm_account = data
	return data


def _access_token(account: dict) -> str:
	cached = frappe.cache().get_value(_TOKEN_CACHE_KEY)
	if cached:
		return cached
	import jwt

	now = int(time.time())
	uri = account.get("token_uri") or "https://oauth2.googleapis.com/token"
	assertion = jwt.encode({"iss": account["client_email"], "scope": _SCOPE, "aud": uri, "iat": now, "exp": now + 3600},
						   account["private_key"], algorithm="RS256")
	r = requests.post(uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, timeout=10)
	r.raise_for_status()
	token = r.json()["access_token"]
	frappe.cache().set_value(_TOKEN_CACHE_KEY, token, expires_in_sec=50 * 60)
	return token
