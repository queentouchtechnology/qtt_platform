"""
One-touch sign-in for the QTT app (rules in qtt_platform.quick_login_logic):

  google(id_token)                 Google account → signed in; an email with no
                                   account yet → {"status": "new"} plus a proof
                                   of the email, so signup only asks for the
                                   WhatsApp code
  enable_device(device_name, platform)   (signed in) trust this phone for
                                   fingerprint / Face ID → {device, secret}
  device_login(device, secret)     fingerprint / Face ID sign-in → new secret
  disable_device(device, secret?)  stop trusting a phone (signed in, or with its secret)

Switches: QTT App Settings → One-touch sign-in. Google uses the client ID of
Frappe's Social Login Key "google" (plus any extra IDs listed in settings).
Both sign-ins create an ordinary Frappe session (cookie), like a password login.
"""

import time

import frappe
import requests
from frappe.rate_limiter import rate_limit

from qtt_platform import quick_login_logic as logic
from qtt_platform.errors import fail, ok

DEVICE = "QTT Trusted Device"
SETTINGS = "QTT App Settings"
TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"


def _on(field: str) -> bool:
	value = frappe.get_cached_doc(SETTINGS).get(field)
	return True if value is None else bool(int(value))


def google_client_id() -> str | None:
	if not frappe.db.exists("Social Login Key", "google"):
		return None
	key = frappe.db.get_value("Social Login Key", "google", ["client_id", "enable_social_login"], as_dict=True)
	return key.client_id if key and key.enable_social_login and key.client_id else None


def login_rules() -> dict:
	"""For the app (get_app_config → "login")."""
	client = google_client_id()
	return {
		"google": bool(client) and _on("google_sign_in"),
		"google_client_id": client,
		"biometric": _on("biometric_sign_in"),
	}


def _sign_in(user: str) -> None:
	if not frappe.db.get_value("User", user, "enabled"):
		raise logic.QuickLoginError("USER_DISABLED", "This account is switched off. Contact your business admin.")
	frappe.local.login_manager.login_as(user)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def google(id_token: str) -> dict:
	try:
		if not login_rules()["google"]:
			raise logic.QuickLoginError("GOOGLE_OFF", "Google sign-in is switched off.")
		r = requests.get(TOKENINFO, params={"id_token": id_token or ""}, timeout=10)
		claims = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
		if r.status_code != 200:
			claims = {"error": claims.get("error") or r.status_code}
		allowed = logic.audiences(google_client_id(), frappe.get_cached_doc(SETTINGS).get("google_client_ids"))
		email, name = logic.check_google_claims(claims, allowed, time.time())
		if frappe.db.exists("User", email):
			_sign_in(email)
			return ok({"status": "signed_in", "user": email})
		# New: Google has proven the email — signup skips the email code.
		from qtt_platform.api import verify

		return ok({"status": "new", "email": email, "full_name": name, "email_token": verify.issue_token("signup", "email", email)})
	except logic.QuickLoginError as e:
		return fail(e.code, str(e))
	except requests.RequestException:
		return fail("GOOGLE_UNREACHABLE", "Couldn't reach Google. Check your internet and try again.")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def enable_device(device_name: str | None = None, platform: str | None = None) -> dict:
	if not _on("biometric_sign_in"):
		return fail("BIOMETRIC_OFF", "Fingerprint and Face ID sign-in is switched off.")
	user = frappe.session.user
	secret = logic.new_secret()
	doc = frappe.get_doc({
		"doctype": DEVICE,
		"user": user,
		"device_name": (device_name or "")[:140],
		"platform": (platform or "")[:20],
		"secret_hash": logic.secret_hash(secret),
		"last_used_at": frappe.utils.now_datetime(),
	}).insert(ignore_permissions=True)
	# Keep the newest few per person.
	for old in frappe.get_all(DEVICE, filters={"user": user}, pluck="name", order_by="last_used_at desc")[logic.MAX_DEVICES_PER_USER:]:
		frappe.delete_doc(DEVICE, old, ignore_permissions=True, force=True)
	return ok({"device": doc.name, "secret": secret})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=3600)
def device_login(device: str, secret: str) -> dict:
	try:
		if not _on("biometric_sign_in"):
			raise logic.QuickLoginError("BIOMETRIC_OFF", "Fingerprint and Face ID sign-in is switched off.")
		row = frappe.db.get_value(DEVICE, device or "", ["name", "user", "secret_hash", "last_used_at"], as_dict=True) if device else None
		if not row or not logic.secret_matches(row.secret_hash, secret):
			raise logic.QuickLoginError("DEVICE_UNKNOWN", "Fingerprint sign-in has been turned off for this phone. Sign in with your password.")
		last = frappe.utils.get_datetime(row.last_used_at).timestamp() if row.last_used_at else None
		if logic.idle_too_long(last, time.time()):
			frappe.delete_doc(DEVICE, row.name, ignore_permissions=True, force=True)
			raise logic.QuickLoginError("DEVICE_EXPIRED", "It's been a while — sign in with your password once more.")
		new = logic.new_secret()
		frappe.db.set_value(DEVICE, row.name, {"secret_hash": logic.secret_hash(new), "last_used_at": frappe.utils.now_datetime()},
							update_modified=False)
		_sign_in(row.user)
		return ok({"user": row.user, "secret": new})
	except logic.QuickLoginError as e:
		return fail(e.code, str(e))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def disable_device(device: str, secret: str | None = None) -> dict:
	row = frappe.db.get_value(DEVICE, device or "", ["name", "user", "secret_hash"], as_dict=True) if device else None
	if row and (row.user == frappe.session.user or logic.secret_matches(row.secret_hash, secret)):
		frappe.delete_doc(DEVICE, row.name, ignore_permissions=True, force=True)
	return ok({})


def prune_idle() -> None:
	cutoff = frappe.utils.add_days(frappe.utils.now_datetime(), -logic.DEVICE_IDLE_DAYS)
	frappe.db.delete(DEVICE, {"last_used_at": ["<", cutoff]})
