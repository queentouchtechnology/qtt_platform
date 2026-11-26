"""
Checking a GSTIN, PAN, bank account or company CIN against government records — one place for QTT OS (Business ›
Profile › Verify your business) and Edenza (seller onboarding). Desk › QTT Verification Settings holds the service keys,
the monthly limit and the name-match level; Desk › QTT Verification Check keeps every check (PAN and account masked).

The service is never named outside Desk. Rules: verification_rules.py.

  check(kind, number, ifsc=, name=, source=, tenant=, subject=)  → {check, result, record_name, details, name_score,
                                                                     name_match, summary, cached}
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, get_first_day, now_datetime, today

from qtt_platform import verification_rules as rules

SETTINGS = "QTT Verification Settings"
CHECK = "QTT Verification Check"
BASE = "https://apisathi.in/gw/v1"


class VerificationUnavailable(frappe.ValidationError):
	pass


def settings():
	return frappe.get_cached_doc(SETTINGS)


def _key(s) -> tuple[str | None, bool]:
	test = bool(s.get("use_test_key"))
	return s.get_password("test_key" if test else "live_key", raise_exception=False), test


def spent_this_month() -> int:
	return int(frappe.db.sql(f"select coalesce(sum(cost_paise), 0) from `tab{CHECK}` where creation >= %s and test = 0",
							 get_first_day(today()))[0][0] or 0)


def _cached(fp: str, test: bool):
	return frappe.db.get_value(CHECK, {"fingerprint": fp, "test": 1 if test else 0, "result": ["in", ["verified", "not_found", "inactive"]],
									   "creation": [">", add_days(now_datetime(), -rules.CACHE_DAYS)]},
							   ["name", "result", "record_name", "details"], as_dict=True, order_by="creation desc")


def check(kind: str, number: str, *, ifsc: str | None = None, name: str | list | None = None, source: str, tenant: str | None = None,
		  subject: str | None = None) -> dict:
	s = settings()
	if not s.get("enabled"):
		raise VerificationUnavailable(_("Verification isn't switched on yet."))
	try:
		n, i = rules.clean(kind, number, ifsc)
	except rules.VerifyError as e:
		frappe.throw(_(str(e)))
	key, test = _key(s)
	if not key:
		raise VerificationUnavailable(_("Verification isn't set up yet."))
	threshold = int(s.get("match_threshold") or 80)
	fp = rules.fingerprint(kind, n, i)
	hit = _cached(fp, test)
	cached = bool(hit)
	if hit:
		result, record_name, details, cost, call_id = hit.result, hit.record_name or "", json.loads(hit.details or "{}"), 0, None
	else:
		if not test and spent_this_month() + rules.COST[kind] > int(float(s.get("monthly_limit") or 0) * 100):
			_tell_owner("Verification stopped: this month's limit is reached. Raise it in Desk › QTT Verification Settings.")
			raise VerificationUnavailable(_("Verification is paused for now. Please try again later."))
		status, body, call_id = _call(key, *rules.request_for(kind, n, i))
		got = rules.read(kind, status, body)
		if got["result"] == "failed":
			if got["reason"] in ("wallet", "setup"):
				_tell_owner("Verification can't run: " + ("the service's wallet is empty — recharge it." if got["reason"] == "wallet"
															  else "the service key isn't accepted — check Desk › QTT Verification Settings."))
			raise VerificationUnavailable(_("Couldn't check right now. Please try again in a few minutes."))
		result, record_name, details = got["result"], got["record_name"], got["details"]
		cost = 0 if test or result == "invalid" else rules.COST[kind]
	# The business, its legal name or its owner (a sole proprietor's PAN and GST are in the owner's name); the GST trade
	# name counts too. The best match is kept, with the name it matched.
	names = [x for x in ([name] if isinstance(name, str) else (name or [])) if x and str(x).strip()]
	on_record = [x for x in (record_name, details.get("trade_name")) if x]
	pairs = [(rules.name_score(r, n), n) for r in on_record for n in names]
	score, name = max(pairs) if pairs else (None, names[0] if names else None)
	doc = frappe.get_doc({"doctype": CHECK, "kind": kind, "number": rules.mask(kind, n), "fingerprint": fp, "source": source, "tenant": tenant,
						  "subject": (subject or "")[:140], "result": result, "record_name": record_name, "given_name": (name or "")[:140],
						  "name_score": score or 0, "name_match": 1 if score is not None and score >= threshold else 0,
						  "details": json.dumps(details), "cost_paise": cost, "test": 1 if test else 0, "cached": 1 if cached else 0,
						  "call_id": call_id}).insert(ignore_permissions=True)
	return {"check": doc.name, "kind": kind, "number": doc.number, "result": result, "record_name": record_name, "details": details,
			"name_score": score, "name_match": bool(doc.name_match), "cached": cached, "test": test,
			"summary": rules.summary(kind, result, record_name, details, name, score, threshold)}


def _call(key: str, path: str, body: dict) -> tuple[int | None, dict | None, str | None]:
	import requests

	try:
		r = requests.post(BASE + path, json=body, timeout=60, headers={"X-API-Key": key, "Content-Type": "application/json", "Accept": "application/json"})
	except Exception:
		frappe.log_error(title="Verification service not reached")
		return None, None, None
	try:
		data = r.json()
	except ValueError:
		data = None
	if r.status_code >= 400 and r.status_code not in (400, 422):
		frappe.log_error(title=f"Verification service answered {r.status_code}", message=r.text[:500])
	return r.status_code, data, r.headers.get("X-Call-Id")


def _tell_owner(text: str) -> None:
	"""The owner's private Telegram, at most once a day per message."""
	key = f"qtt_verify_alert:{hash(text)}:{today()}"
	if frappe.cache().get_value(key):
		return
	frappe.cache().set_value(key, 1, expires_in_sec=86400)
	try:
		import requests

		from qtt_platform.api.enquiry import owner_telegram_chat

		chat = owner_telegram_chat()
		token = frappe.get_cached_doc("QTT Ops Settings").get_password("telegram_bot_token", raise_exception=False)
		if chat and token:
			requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": f"🔎 {text}"}, timeout=15)
	except Exception:
		pass
