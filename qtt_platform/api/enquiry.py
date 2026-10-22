"""
Website enquiries → Frappe CRM (2026-10-22). One door for every enquiry form of Queen Touch Technology's sites
(queentouchtech.in, .com, qtterp.in, quizmasterplus.in, sathishkumar.pro): each becomes a CRM Lead (source "Website
Form", the site and page in its note) that the team works in Frappe CRM, and QTT's managers get a bell notification. Truth of Bible's forms
are a separate path (its own site). No login; rate-limited; a hidden "website" field filled in = a bot, quietly dropped.

  submit   name, email and/or phone, message, site, page, interest (what they asked about) → {ok}
"""

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

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


def _source() -> str:
	if not frappe.db.exists("CRM Lead Source", SOURCE):
		frappe.get_doc({"doctype": "CRM Lead Source", "source_name": SOURCE}).insert(ignore_permissions=True)
	return SOURCE


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=8, seconds=3600)
def submit(name: str = "", email: str = "", phone: str = "", message: str = "", site: str = "", page: str = "", interest: str = "",
		   company: str = "", website: str = "") -> dict:
	"""An enquiry from one of QTT's websites → a CRM Lead. `website` is a hidden trap field: people leave it empty."""
	if website:
		return {"ok": True}  # a bot filled the hidden field
	name, email, phone = _clean(name, _MAX["name"]), _clean(email, _MAX["email"]).lower(), _clean(phone, _MAX["phone"])
	if not name or not (email or phone):
		frappe.throw(_("Please give your name and an email or phone number."))
	if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
		frappe.throw(_("Please check the email address."))
	from_site = site_of(site, frappe.get_request_header("Origin") or "")
	if not from_site:
		frappe.throw(_("This form isn't from a Queen Touch Technology site."), frappe.PermissionError)
	first, _sp, last = name.partition(" ")
	lead = frappe.get_doc({
		"doctype": "CRM Lead", "first_name": first, "last_name": last, "email": email or None, "mobile_no": phone or None,
		"organization": _clean(company, _MAX["company"]) or None, "website": from_site, "source": _source(), "status": "New",
	}).insert(ignore_permissions=True)
	note = "\n".join(x for x in (
		f"Website enquiry from {from_site}" + (f" — {_clean(page, _MAX['page'])}" if page else ""),
		f"About: {_clean(interest, _MAX['interest'])}" if interest else "",
		"", str(message or "")[:_MAX["message"]].strip()) if x is not None)
	lead.add_comment("Comment", frappe.utils.escape_html(note).replace("\n", "<br>"))
	try:  # the bell in Desk / CRM for QTT's managers
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		users = [u for u in frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent", distinct=True)
				 if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]
		enqueue_create_notification(users, {"type": "Alert", "document_type": "CRM Lead", "document_name": lead.name,
											 "subject": f"New enquiry from {from_site}: {frappe.utils.escape_html(name)}",
											 "email_content": frappe.utils.escape_html(_clean(message, 300))})
	except Exception:
		frappe.log_error(title="Website enquiry: team not told")
	return {"ok": True}
