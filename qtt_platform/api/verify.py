"""
Proving an email address or WhatsApp number with a one-time code — used by
self-service signup (api/saas.signup) so every new account has a real email
and a real WhatsApp number behind it.

  send_code(channel, target)         email → Frappe's outgoing mail (Brevo);
                                     whatsapp → QTT's WhatsApp number through
                                     Chatwoot, as the approved template set in
                                     QTT App Settings (default "reference_number")
  verify_code(channel, target, code) → {"token": ...} for signup to consume

Which checks signup demands is set in QTT App Settings → Sign-up security.
Codes and tokens live only in Redis (short-lived); only an HMAC of a code is
stored. Rules (expiry, tries, resend wait) are in qtt_platform.otp_logic.

The WhatsApp sender comes from whichever app owns QTT's WhatsApp connection
(hook `qtt_whatsapp_sender`, today qtt_services.api.messaging.send_whatsapp),
so qtt_platform never names a product.
"""

import json
import time

import frappe
from frappe.rate_limiter import rate_limit

from qtt_platform import otp_logic as logic
from qtt_platform.errors import fail, ok

PURPOSES = ("signup", "file_link")  # file_link: a guest proving their email to open a Files share link
SETTINGS = "QTT App Settings"


def _secret() -> str:
	from frappe.utils.password import get_encryption_key

	return get_encryption_key()


def _key(kind: str, purpose: str, channel: str, target: str) -> str:
	return f"qtt_otp:{kind}:{purpose}:{channel}:{target}"


def _load(key: str) -> dict | None:
	raw = frappe.cache.get_value(key)
	if not raw:
		return None
	return raw if isinstance(raw, dict) else json.loads(raw)


def _store(key: str, value: dict, ttl: int) -> None:
	frappe.cache.set_value(key, json.dumps(value), expires_in_sec=ttl)


def signup_rules() -> dict:
	"""What signup demands (QTT App Settings → Sign-up security); on unless switched off."""
	s = frappe.get_cached_doc(SETTINGS)

	def on(field):
		value = s.get(field)
		return True if value is None else bool(int(value))

	return {"verify_email": on("signup_verify_email"), "verify_whatsapp": on("signup_verify_whatsapp")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=12, seconds=3600)
def send_code(channel: str, target: str, purpose: str = "signup", name: str | None = None) -> dict:
	try:
		if purpose not in PURPOSES:
			raise logic.OtpError("INVALID_PURPOSE", "Unknown purpose.")
		target = logic.normalize_target(channel, target)
		if purpose == "signup" and channel == "email" and frappe.db.exists("User", target):
			raise logic.OtpError("DUPLICATE_EMAIL", "An account with this email already exists. Sign in instead.")
		key = _key("code", purpose, channel, target)
		now = time.time()
		code, state = logic.issue(_secret(), purpose, channel, target, _load(key), now)
		_deliver(channel, target, code, name)
		_store(key, state, 3600)
		return ok({"sent_to": logic.mask(channel, target), "expires_in": logic.CODE_TTL, "resend_in": logic.RESEND_AFTER})
	except logic.OtpError as e:
		return fail(e.code, str(e).format(e.extra.get("wait", ""), e.extra.get("left", "")))
	except Exception:
		frappe.log_error(title=f"qtt verify: {channel} code not sent", message=frappe.get_traceback())
		where = "WhatsApp" if channel == "whatsapp" else "email"
		return fail("SEND_FAILED", f"We couldn't send the code by {where} just now. Please try again in a minute.")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=40, seconds=3600)
def verify_code(channel: str, target: str, code: str, purpose: str = "signup") -> dict:
	try:
		target = logic.normalize_target(channel, target)
		key = _key("code", purpose, channel, target)
		state = _load(key)
		try:
			state = logic.verify(_secret(), purpose, channel, target, code, state, time.time())
		except logic.OtpError as e:
			if "state" in e.extra:
				_store(key, e.extra["state"], 3600)
			raise
		_store(key, state, 3600)
		token = logic.new_token()
		_store(_key("token", purpose, channel, token), {"target": target}, logic.TOKEN_TTL)
		return ok({"token": token, "verified": target})
	except logic.OtpError as e:
		return fail(e.code, str(e).format(e.extra.get("left", "")))


def issue_token(purpose: str, channel: str, target: str) -> str:
	"""A proof for `target` obtained another way (e.g. Google has verified the email)."""
	token = logic.new_token()
	_store(_key("token", purpose, channel, token), {"target": logic.normalize_target(channel, target)}, logic.TOKEN_TTL)
	return token


def check_token(purpose: str, channel: str, token: str | None, target: str) -> bool:
	"""True when `token` proves `target` (normalised) for this purpose."""
	if not token:
		return False
	state = _load(_key("token", purpose, channel, token))
	return bool(state) and state.get("target") == logic.normalize_target(channel, target)


def consume_token(purpose: str, channel: str, token: str | None) -> None:
	if token:
		frappe.cache.delete_value(_key("token", purpose, channel, token))


# ---------------------------------------------------------------- delivery


def _brand() -> str:
	return "Queen Touch Technology"


def _deliver(channel: str, target: str, code: str, name: str | None) -> None:
	if channel == "email":
		brand = _brand()
		frappe.sendmail(
			recipients=[target],
			subject=f"{code} is your {brand} verification code",
			message=_email_html(code, brand),
			now=True,
		)
		return
	senders = frappe.get_hooks("qtt_whatsapp_sender") or []
	if not senders:
		raise RuntimeError("No WhatsApp sender app is installed (hook qtt_whatsapp_sender).")
	s = frappe.get_cached_doc(SETTINGS)
	frappe.get_attr(senders[-1])(
		to=target,
		text=f"Your verification code is {code}",
		template=s.get("whatsapp_otp_template") or "reference_number",
		language=s.get("whatsapp_otp_language") or "en",
		params=[code],
		name=name,
		# What staff see in the Onbox conversation — never the code itself.
		display="Sign-up verification code sent (hidden).",
	)


def _email_html(code: str, brand: str) -> str:
	spaced = " ".join(code)
	return f"""
<div style="font-family:Poppins,Segoe UI,Arial,sans-serif;background:#F7F8FA;padding:32px 12px">
  <div style="max-width:440px;margin:0 auto;background:#FFFFFF;border:1px solid #E7E9EE;border-radius:14px;overflow:hidden">
    <div style="background:#0B0D12;color:#FFFFFF;padding:18px 24px;font-weight:600;font-size:16px">{frappe.utils.escape_html(brand)}</div>
    <div style="height:3px;background:#3B5CFF"></div>
    <div style="padding:28px 24px;color:#0B0D12">
      <div style="font-size:15px;margin-bottom:14px">Your verification code is</div>
      <div style="font-size:32px;font-weight:700;letter-spacing:6px;color:#3B5CFF;background:#EEF1FF;border-radius:10px;padding:14px 0;text-align:center">{spaced}</div>
      <div style="font-size:13px;color:#5B6372;margin-top:18px;line-height:1.6">
        It expires in {logic.CODE_TTL // 60} minutes. Never share this code with anyone — {frappe.utils.escape_html(brand)} will never ask for it.
        If you didn't ask for it, you can ignore this email.
      </div>
    </div>
  </div>
</div>"""
