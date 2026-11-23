"""
Internship applications from queentouchtech.in/internship/ (owner, 23 Nov 2026) → Desk › QTT Internship Application.
No login. The same bot defence as the website's enquiry door (api/enquiry.py): a hidden trap field, a signed single-use
form ticket (enquiry.ticket), a rate limit per address and a daily cap; bots are told "ok" and dropped quietly.
The applicant gets an email ("QTT · Internship application received"); the team an email (Desk › QTT App Settings ›
Internship applications, else info@queentouchtech.com)
("QTT · New internship application" — every detail, the documents attached, replies go to the applicant) and a Telegram. The same email again within
7 days updates that application instead of making a second one.

  submit   multipart: the form's fields (internship_rules.clean — the team's WhatsApp message in full), the documents
           (resume and college ID card needed, request letter if there is one: PDF, Word or a photo, 5 MB each, kept
           private), site, page, ticket, website (the trap) → {ok}
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from qtt_platform import internship_rules as rules
from qtt_platform.api import enquiry

DOC = "QTT Internship Application"
DAILY_CAP = 60


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=3600)
def submit(**form) -> dict:
	"""One internship application from queentouchtech.in (see the module note) → {ok}. A sentence to fix when needed."""
	if form.get("website"):
		return enquiry._drop("trap")
	ticket = str(form.get("ticket") or "")
	bad = enquiry.rules.check_ticket(ticket, enquiry._secret())
	if bad:
		return enquiry._drop(bad)
	if frappe.cache.get_value(f"qtt_internship_used:{ticket}"):
		return enquiry._drop("replay")
	site = enquiry.site_of(str(form.get("site") or ""), frappe.get_request_header("Origin") or "")
	if not site:
		frappe.throw(_("This form isn't from a Queen Touch Technology site."), frappe.PermissionError)
	try:
		data = rules.clean(form, frappe.utils.getdate())
	except rules.AppError as exc:
		frappe.throw(_(str(exc)))
	if enquiry.rules.spam_reason(data["applicant_name"], data["projects"] or data["why"], data["college"]):
		return enquiry._drop("spam")
	files = {}
	for key, label, _needed in rules.DOCUMENTS:
		f = frappe.request.files.get(key) if frappe.request and frappe.request.files else None
		if f and f.filename:
			content = f.stream.read()
			problem = rules.file_problem(label, f.filename, len(content))
			if problem:
				frappe.throw(_(problem))
			if f.filename.lower().endswith(".pdf"):  # Frappe refuses a broken PDF or one with scripts: say so in words
				from frappe.utils.pdf import pdf_contains_js

				try:
					scripted = pdf_contains_js(content)
				except Exception:
					frappe.throw(_("{0}: that PDF can't be opened. Please save it again (or send a photo) and try.").format(label))
				if scripted:
					frappe.throw(_("{0}: that PDF can't be accepted. Please save it again as a plain PDF.").format(label))
			files[key] = (f.filename, content)
	day = f"qtt_internship_count:{frappe.utils.today()}"
	if int(frappe.cache.get_value(day) or 0) >= DAILY_CAP:
		frappe.log_error(title="Internship applications: daily cap reached", message=f"{DAILY_CAP} today — later ones dropped")
		return enquiry._drop("cap")
	frappe.cache.set_value(day, int(frappe.cache.get_value(day) or 0) + 1, expires_in_sec=2 * 86400)
	frappe.cache.set_value(f"qtt_internship_used:{ticket}", 1, expires_in_sec=enquiry.rules.MAX_SECONDS + 60)

	since = frappe.utils.add_days(frappe.utils.now_datetime(), -7)
	name = frappe.db.get_value(DOC, {"email": data["email"], "creation": [">", since]}, "name")
	have = set(files) | ({k for k, _l, _n in rules.DOCUMENTS if frappe.db.get_value(DOC, name, k)} if name else set())
	missing = rules.missing_documents(have)
	if missing:
		frappe.throw(_(missing))
	values = {**data, "site": site, "page": enquiry._clean(form.get("page"), 300)}
	if name:  # the same person again this week: their application, updated
		doc = frappe.get_doc(DOC, name)
		doc.update({k: v for k, v in values.items() if v})
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": DOC, "status": "New", **values}).insert(ignore_permissions=True)
	for key, (filename, content) in files.items():  # private: only the QTT team opens them in Desk
		f = frappe.get_doc({"doctype": "File", "file_name": f"{key}-{doc.name}-{filename[-60:]}", "content": content, "is_private": 1,
							"attached_to_doctype": DOC, "attached_to_name": doc.name, "attached_to_field": key}).insert(ignore_permissions=True)
		doc.db_set(key, f.file_url)
	frappe.db.commit()
	_tell(doc, again=bool(name), files=files)
	return {"ok": True}


TEAM_EMAIL = "info@queentouchtech.com"  # when Desk › QTT App Settings › Internship applications is empty


def _team_addresses() -> list[str]:
	"""Desk › QTT App Settings › Internship applications › Send applications to (commas between), else TEAM_EMAIL."""
	try:
		raw = frappe.db.get_single_value("QTT App Settings", "internship_email") or ""
	except Exception:
		raw = ""
	out = [a.strip() for a in raw.replace(";", ",").split(",") if frappe.utils.validate_email_address(a.strip())]
	return out or [TEAM_EMAIL]


def _tell(doc, again: bool, files: dict | None = None) -> None:
	"""The applicant's email, the team's email (every detail, the documents attached; reply goes to the applicant) and the
	owner's Telegram — none of them ever stops the application being saved."""
	_team_email(doc, again, files or {})
	try:
		from qtt_platform import emails

		emails.send("QTT · Internship application received", [doc.email],
					{"name": doc.applicant_name.split(" ")[0], "area": doc.area, "preheader": "We have your application"},
					reference_doctype=DOC, reference_name=doc.name)
	except Exception:
		frappe.log_error(title="Internship application: email not sent")
	_telegram(doc, again)


def _team_email(doc, again: bool, files: dict) -> None:
	rows = [("Contact number", doc.phone), ("Email", doc.email), ("College / university", doc.college),
			("Department / specialization", doc.course), ("Current year", doc.year_of_study), ("Duration", doc.duration),
			("Start → end", " → ".join(str(x) for x in (doc.start_date, doc.end_date) if x)), ("Mode", doc.mode),
			("Mandatory as per curriculum", doc.mandatory), ("Request letter available", doc.has_request_letter),
			("Programming languages", doc.languages), ("Tools / technologies", doc.tools), ("Previous projects", doc.projects),
			("Previous internship", doc.previous_internship), ("Portfolio", doc.portfolio), ("Project report needed", doc.needs_report),
			("Completion certificate needed", doc.needs_certificate), ("Progress reports needed", doc.needs_progress_reports),
			("College guidelines", doc.college_guidelines)]
	attachments = [{"fname": f"{label} — {doc.applicant_name} — {files[key][0][-60:]}", "fcontent": files[key][1]}
				   for key, label, _n in rules.DOCUMENTS if key in files]
	try:
		from qtt_platform import emails

		emails.send("QTT · New internship application", _team_addresses(),
					{"name": doc.applicant_name, "area": doc.area, "mode": doc.mode, "college": doc.college, "again": again,
					 "rows": [[label, str(value)] for label, value in rows if value], "documents": ", ".join(a["fname"].split(" — ")[0] for a in attachments),
					 "link": frappe.utils.get_url(f"/app/qtt-internship-application/{doc.name}"),
					 "preheader": f"{doc.applicant_name} · {doc.area}"},
					reply_to=doc.email, attachments=attachments, reference_doctype=DOC, reference_name=doc.name)
	except Exception:
		frappe.log_error(title="Internship application: team email not sent")


def _telegram(doc, again: bool) -> None:
	chat = enquiry.owner_telegram_chat()
	try:
		token = frappe.get_cached_doc("QTT Ops Settings").get_password("telegram_bot_token", raise_exception=False)
	except Exception:
		token = None
	if not chat or not token:
		return
	text = "\n".join(x for x in (
		("Internship application updated" if again else "New internship application") + f" — {doc.site}",
		f"{doc.applicant_name} · {doc.area}" + (f" · {doc.mode}" if doc.mode else ""),
		" · ".join(x for x in (doc.college, doc.course, doc.year_of_study) if x),
		" · ".join(x for x in (doc.phone, doc.email) if x),
		" · ".join(x for x in (f"{doc.duration}" if doc.duration else "", f"{doc.start_date} → {doc.end_date}" if doc.start_date and doc.end_date else "",
							   "mandatory" if doc.mandatory == "Yes" else "", "certificate" if doc.needs_certificate == "Yes" else "") if x),
		" · ".join(label for key, label, _n in rules.DOCUMENTS if doc.get(key)),
		frappe.utils.get_url(f"/app/qtt-internship-application/{doc.name}")) if x)
	try:
		import requests

		requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"},
					  timeout=15)
	except Exception:
		frappe.log_error(title="Internship application: Telegram not sent")
