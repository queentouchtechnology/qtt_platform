"""
One-touch sign-in rules (pure — no frappe; qtt_platform.api.quick_login does
storage, Google's check and the session).

Google: the app sends the ID token Google gave it; Google's tokeninfo endpoint
checks the signature and we check the claims here — it must be for one of
QTT's own client IDs, from Google, unexpired, with a verified email.

Fingerprint / Face ID: after one normal sign-in the phone enrols as a trusted
device and gets a random 256-bit secret, kept in the phone's Keystore /
Keychain and only released after the biometric check. The server keeps only
a SHA-256 of it and replaces the secret on every use, so a copied secret
stops working the next time the real phone signs in.
"""

import hashlib
import hmac
import secrets

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
DEVICE_IDLE_DAYS = 90
MAX_DEVICES_PER_USER = 10


class QuickLoginError(Exception):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code


def check_google_claims(claims: dict, allowed_audiences: list[str], now: float) -> tuple[str, str]:
	"""-> (email, full name) from verified tokeninfo claims, or raises."""
	if not claims or claims.get("error") or claims.get("error_description"):
		raise QuickLoginError("GOOGLE_INVALID", "Google sign-in didn't work. Please try again.")
	if claims.get("aud") not in [a for a in allowed_audiences if a]:
		raise QuickLoginError("GOOGLE_INVALID", "This Google sign-in isn't for this app.")
	if claims.get("iss") not in GOOGLE_ISSUERS:
		raise QuickLoginError("GOOGLE_INVALID", "Google sign-in didn't work. Please try again.")
	try:
		expired = int(claims.get("exp") or 0) < now
	except (TypeError, ValueError):
		expired = True
	if expired:
		raise QuickLoginError("GOOGLE_EXPIRED", "Google sign-in timed out. Please try again.")
	email = (claims.get("email") or "").strip().lower()
	if not email or str(claims.get("email_verified")).lower() != "true":
		raise QuickLoginError("GOOGLE_UNVERIFIED", "This Google account's email isn't verified.")
	name = (claims.get("name") or " ".join(x for x in (claims.get("given_name"), claims.get("family_name")) if x) or "").strip()
	return email, name


def audiences(primary: str | None, extra: str | None) -> list[str]:
	"""The Frappe Google key's client ID plus any listed in QTT App Settings (one per line or comma)."""
	out = [primary.strip()] if primary and primary.strip() else []
	for part in (extra or "").replace(",", "\n").splitlines():
		if part.strip() and part.strip() not in out:
			out.append(part.strip())
	return out


def new_secret() -> str:
	return secrets.token_urlsafe(32)


def secret_hash(secret: str) -> str:
	return hashlib.sha256((secret or "").encode()).hexdigest()


def secret_matches(stored_hash: str | None, secret: str | None) -> bool:
	return bool(stored_hash and secret) and hmac.compare_digest(stored_hash, secret_hash(secret))


def idle_too_long(last_used_ts: float | None, now: float) -> bool:
	return last_used_ts is not None and now - last_used_ts > DEVICE_IDLE_DAYS * 86400
