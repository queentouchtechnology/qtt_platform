"""
Website enquiries → Frappe CRM (2026-10-22). One door for every enquiry form of Queen Touch Technology's sites
(queentouchtech.in, .com, qtterp.in, quizmasterplus.in, sathishkumar.pro): each becomes a CRM Lead (source "Website
Form", the site and page in its note) that the team works in Frappe CRM, and QTT's managers get a bell notification. Truth of Bible's forms
are a separate path (its own site). No login. Bot defence in layers (enquiry_rules.py): a hidden trap field, a signed
single-use form ticket that must be 3 s – 2 h old, spam words, a rate limit per address, a repeat from the same email /
phone in a day added to its first lead, and a daily cap for the whole door. Bots are told "ok" and dropped quietly,
so they learn nothing.

  ticket   GET: a signed form ticket (the page asks when the form shows)
  submit   name, email and/or phone, message, site, page, interest, ticket → {ok}
  record   (Python) the lead, the bell and the owner's Telegram — also for forms that come through n8n
           (qtt_services.api.automation.website_enquiry)
"""

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from qtt_platform import enquiry_rules as rules

SOURCE = "Website Form"
SITES = ("queentouchtech.in", "queentouchtech.com", "queentouchtechnology.com", "qtterp.in", "quizmasterplus.in", "sathishkumar.pro")
_MAX = {"name": 120, "email": 140, "phone": 30, "company": 140, "message": 3000, "site": 80, "page": 300, "interest": 120}


def _clean(v, n: int) -> str:
	return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def site_of(site: str, origin: str = "") -> str:
	"""The known site a form came from ('' when it isn't one of QTT's)."""
	for s in (site, origin):
		host = re.sub(r"^https?://", "", str(s or "").lower()).split("/")[0].split(":")[0].removeprefix("www.")
		if host in SITES:
			return host
	return ""


def _secret() -> str:
	from frappe.utils.password import get_encryption_key

	return "qtt-enquiry:" + get_encryption_key()


def _drop(why: str) -> dict:
	"""A bot: logged for the team's numbers, told 'ok' so it learns nothing."""
	try:
		frappe.cache.incrby(f"qtt_enquiry_dropped:{frappe.utils.today()}:{why}", 1)
	except Exception:
		pass
	return {"ok": True}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=40, seconds=3600)
def ticket() -> dict:
	"""A signed form ticket for one enquiry (single use, valid 3 seconds to 2 hours after it's given)."""
	return {"ticket": rules.make_ticket(_secret())}


def _source() -> str:
	if not frappe.db.exists("CRM Lead Source", SOURCE):
		frappe.get_doc({"doctype": "CRM Lead Source", "source_name": SOURCE}).insert(ignore_permissions=True)
	return SOURCE


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=8, seconds=3600)
def submit(name: str = "", email: str = "", phone: str = "", message: str = "", site: str = "", page: str = "", interest: str = "",
		   company: str = "", website: str = "", ticket: str = "") -> dict:
	"""An enquiry from one of QTT's websites → a CRM Lead. `website` is a hidden trap field: people leave it empty;
	`ticket` comes from ticket() when the form showed."""
	if website:
		return _drop("trap")
	bad = rules.check_ticket(ticket, _secret())
	if bad:
		return _drop(bad)
	if frappe.cache.get_value(f"qtt_enquiry_used:{ticket}"):
		return _drop("replay")
	frappe.cache.set_value(f"qtt_enquiry_used:{ticket}", 1, expires_in_sec=rules.MAX_SECONDS + 60)
	name, email, phone = _clean(name, _MAX["name"]), _clean(email, _MAX["email"]).lower(), _clean(phone, _MAX["phone"])
	if not name or not (email or phone):
		frappe.throw(_("Please give your name and an email or phone number."))
	if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
		frappe.throw(_("Please check the email address."))
	from_site = site_of(site, frappe.get_request_header("Origin") or "")
	if not from_site:
		frappe.throw(_("This form isn't from a Queen Touch Technology site."), frappe.PermissionError)
	if rules.spam_reason(name, str(message or ""), str(company or "")):
		return _drop("spam")
	day = f"qtt_enquiry_count:{frappe.utils.today()}"
	if int(frappe.cache.get_value(day) or 0) >= rules.DAILY_CAP:
		frappe.log_error(title="Website enquiries: daily cap reached", message=f"{rules.DAILY_CAP} today — later ones dropped")
		return _drop("cap")
	frappe.cache.set_value(day, int(frappe.cache.get_value(day) or 0) + 1, expires_in_sec=2 * 86400)
	record(name=name, email=email, phone=phone, message=message, site=from_site, page=page, interest=interest, company=company)
	return {"ok": True}


def record(*, name: str, email: str, phone: str, message: str = "", site: str, page: str = "", interest: str = "", company: str = "",
		   extra: str = "") -> str:
	"""A checked enquiry → its CRM Lead (the same person again today: a note on their first lead), the bell for QTT's
	managers and the owner's Telegram at once. Also used by forms that come through n8n (qtt_services automation key).
	→ the lead's name."""
	since = frappe.utils.add_days(frappe.utils.now_datetime(), -1)
	again = frappe.db.get_value("CRM Lead", {"source": SOURCE, "creation": [">", since], **({"email": email} if email else {"mobile_no": phone})}, "name")
	if again:
		frappe.get_doc("CRM Lead", again).add_comment("Comment", frappe.utils.escape_html(
			f"Another message from {site}" + (f" — {_clean(interest, _MAX['interest'])}" if interest else "") + "\n\n"
			+ str(message or "")[:_MAX["message"]].strip()).replace("\n", "<br>"))
		return again
	first, _sp, last = name.partition(" ")
	lead = frappe.get_doc({
		"doctype": "CRM Lead", "first_name": first, "last_name": last, "email": email or None, "mobile_no": phone or None,
		"organization": _clean(company, _MAX["company"]) or None, "website": site, "source": _source(), "status": "New",
	}).insert(ignore_permissions=True)
	note = "\n".join(x for x in (
		f"Website enquiry from {site}" + (f" — {_clean(page, _MAX['page'])}" if page else ""),
		f"About: {_clean(interest, _MAX['interest'])}" if interest else "", extra,
		"", str(message or "")[:_MAX["message"]].strip()) if x is not None)
	lead.add_comment("Comment", frappe.utils.escape_html(note).replace("\n", "<br>"))
	try:  # the bell in Desk / CRM for QTT's managers
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		users = [u for u in frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent", distinct=True)
				 if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]
		enqueue_create_notification(users, {"type": "Alert", "document_type": "CRM Lead", "document_name": lead.name,
											 "subject": f"New enquiry from {site}: {frappe.utils.escape_html(name)}",
											 "email_content": frappe.utils.escape_html(_clean(message, 300))})
	except Exception:
		frappe.log_error(title="Website enquiry: team not told")
	_telegram(lead.name, name=name, company=company, site=site, page=page, interest=interest, email=email, phone=phone, extra=extra)
	return lead.name


def _telegram(lead: str, **e) -> None:
	"""The owner's private Telegram (site_config qtt_owner_telegram_chat, the ops bot) — never the public channel:
	an enquiry waited a week in Slack once (24 Oct 2026)."""
	chat = frappe.conf.get("qtt_owner_telegram_chat")
	token = frappe.get_cached_doc("QTT Ops Settings").get_password("telegram_bot_token", raise_exception=False)
	if not chat or not token:
		return
	text = "\n".join(x for x in (
		f"New enquiry — {e.get('site')}" + (f" {e.get('page')}" if e.get("page") and e.get("page") not in e.get("site", "") else ""),
		f"{e.get('name')}" + (f" · {e.get('company')}" if e.get("company") else ""),
		f"About: {e.get('interest')}" if e.get("interest") else "", e.get("extra") or "",
		" · ".join(x for x in (e.get("phone"), e.get("email")) if x),
		f"CRM: {frappe.utils.get_url(f'/crm/leads/{lead}')}") if x)
	try:
		import requests

		requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"}, timeout=15)
	except Exception:
		frappe.log_error(title="Website enquiry: Telegram not sent")
