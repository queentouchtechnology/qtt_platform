"""
One-time codes for proving an email address or WhatsApp number (pure — no
frappe; qtt_platform.api.verify does the storage and sending).

Security choices:
  - 6 random digits from `secrets`; only an HMAC of the code is stored, keyed
    by the site's secret and bound to purpose + channel + target, so a code for
    one number can't be replayed for another.
  - A code lives 10 minutes and allows 5 wrong tries, then it is burned.
  - Resend waits 60 seconds; at most 5 codes per target per hour.
  - A correct code yields a one-time verification token (30 minutes) that
    signup consumes — the code itself never reaches the signup call.
"""

import hashlib
import hmac
import re
import secrets

CODE_LENGTH = 6
CODE_TTL = 600
MAX_ATTEMPTS = 5
RESEND_AFTER = 60
MAX_SENDS_PER_HOUR = 5
TOKEN_TTL = 1800
CHANNELS = ("email", "whatsapp")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OtpError(Exception):
	def __init__(self, code: str, message: str, **extra):
		super().__init__(message)
		self.code = code
		self.extra = extra


def new_code() -> str:
	return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def new_token() -> str:
	return secrets.token_urlsafe(32)


def normalize_phone(value: str | None) -> str:
	"""E.164 digits with a leading +; a bare 10-digit number is taken as Indian."""
	digits = re.sub(r"[^0-9]", "", str(value or ""))
	if len(digits) == 10:
		digits = "91" + digits
	return "+" + digits if 11 <= len(digits) <= 15 else ""


def normalize_target(channel: str, target: str | None) -> str:
	if channel not in CHANNELS:
		raise OtpError("INVALID_CHANNEL", "Choose email or WhatsApp.")
	if channel == "email":
		t = (target or "").strip().lower()
		if not _EMAIL_RE.match(t) or len(t) > 140:
			raise OtpError("INVALID_EMAIL", "Enter a valid email address.")
		return t
	t = normalize_phone(target)
	if not t:
		raise OtpError("INVALID_PHONE", "Enter a valid WhatsApp number with country code.")
	return t


def digest(secret: str, purpose: str, channel: str, target: str, code: str) -> str:
	msg = f"{purpose}|{channel}|{target}|{code}".encode()
	return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def mask(channel: str, target: str) -> str:
	if channel == "email":
		user, _, domain = target.partition("@")
		return (user[:2] + "•" * max(1, len(user) - 2)) + "@" + domain
	return target[:3] + "•" * max(0, len(target) - 7) + target[-4:]


def check_can_send(state: dict | None, now: float) -> list[float]:
	"""Raises when the target must wait; returns the send history to keep (last hour)."""
	state = state or {}
	recent = [t for t in state.get("sends") or [] if now - t < 3600]
	if recent and now - recent[-1] < RESEND_AFTER:
		wait = int(RESEND_AFTER - (now - recent[-1])) + 1
		raise OtpError("TOO_SOON", "Please wait {0} seconds before asking for a new code.", wait=wait)
	if len(recent) >= MAX_SENDS_PER_HOUR:
		raise OtpError("TOO_MANY", "Too many codes asked for. Try again in an hour.")
	return recent


def issue(secret: str, purpose: str, channel: str, target: str, state: dict | None, now: float, code: str | None = None):
	"""-> (code to send, new state to store)."""
	sends = check_can_send(state, now)
	code = code or new_code()
	return code, {
		"hash": digest(secret, purpose, channel, target, code),
		"expires": now + CODE_TTL,
		"attempts": 0,
		"sends": sends + [now],
	}


def verify(secret: str, purpose: str, channel: str, target: str, code: str, state: dict | None, now: float) -> dict:
	"""-> new state (code burned on success). Raises OtpError when wrong/expired."""
	if not state or not state.get("hash"):
		raise OtpError("NO_CODE", "Ask for a code first.")
	if now > state.get("expires", 0):
		raise OtpError("EXPIRED", "This code has expired. Ask for a new one.")
	if state.get("attempts", 0) >= MAX_ATTEMPTS:
		raise OtpError("LOCKED", "Too many wrong tries. Ask for a new code.")
	code = re.sub(r"\s", "", str(code or ""))
	ok = len(code) == CODE_LENGTH and hmac.compare_digest(state["hash"], digest(secret, purpose, channel, target, code))
	state = dict(state)
	if not ok:
		state["attempts"] = state.get("attempts", 0) + 1
		left = MAX_ATTEMPTS - state["attempts"]
		raise OtpError("WRONG_CODE", "That code is not right. {0} tries left.", left=left, state=state)
	state["hash"] = None
	return state
