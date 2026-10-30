"""
Every email QTT OS sends is a Frappe Email Template (Desk › Email Template — the wording is edited there) in one
professional layout (templates/emails/qtt_layout.html: the QTT OS logo and colours, a clear footer).

  send(name, recipients, context, **kw)  the template's subject and body with `context`, sent with frappe.sendmail
  render(name, context)                  → (subject, html)
  sync()                                 after migrate: each app's email_templates/*.html that Desk doesn't have yet is
                                         added (one changed in Desk is kept); Frappe's welcome and password emails use ours

A template file (<app>/email_templates/<slug>.html) starts with <!-- name: QTT · … --> and <!-- subject: … -->, then
{% extends "templates/emails/qtt_layout.html" %}{% block body %}…{% endblock %}. Context for the layout: preheader,
brand, sent_for, reason (see the layout). Text from people is escaped; pass QTT's own HTML in `html=("key",)`.
"""

import os

import frappe

from qtt_platform import email_rules as rules

TEMPLATE = "Email Template"
WELCOME = "QTT · Welcome"
PASSWORD = "QTT · Set your password"


def render(name: str, context: dict | None = None, html: tuple = ()) -> tuple[str, str]:
	t = frappe.get_cached_doc(TEMPLATE, name)
	raw = {"site_url": frappe.utils.get_url(), **(context or {})}
	subject = frappe.render_template(t.subject or "", raw)  # a subject is plain text: not escaped
	body = frappe.render_template(t.response_html or t.response or "", {**rules.escape(raw, set(html)), "subject": rules.escape(subject)})
	return " ".join(subject.split()), body


def send(name: str, recipients, context: dict | None = None, html: tuple = (), **kw) -> None:
	"""frappe.sendmail with the template; kw as frappe.sendmail (reply_to, attachments, reference_doctype, now…)."""
	subject, body = render(name, context, html)
	frappe.sendmail(recipients=recipients, subject=subject, message=body, **kw)


def sync() -> dict:
	"""after_migrate: add the missing templates; never overwrite one already in Desk."""
	added = []
	for app in frappe.get_installed_apps():
		folder = frappe.get_app_path(app, "email_templates")
		if not os.path.isdir(folder):
			continue
		for f in sorted(os.listdir(folder)):
			if not f.endswith(".html"):
				continue
			try:
				t = rules.parse_file(open(os.path.join(folder, f), encoding="utf-8").read())
				if frappe.db.exists(TEMPLATE, t["name"]):
					continue
				frappe.get_doc({"doctype": TEMPLATE, "__newname": t["name"], "subject": t["subject"], "use_html": 1,
								"response_html": t["body"]}).insert(ignore_permissions=True)
				added.append(t["name"])
			except Exception:
				frappe.log_error(title=f"Email template {app}/{f} not added")
	# Frappe's own account emails (a new person's welcome, password reset) in the same look; the plain footer
	# ("Sent via Frappe") is replaced by ours.
	for field, name in (("welcome_email_template", WELCOME), ("reset_password_template", PASSWORD)):
		if frappe.db.exists(TEMPLATE, name) and not frappe.db.get_single_value("System Settings", field):
			frappe.db.set_single_value("System Settings", field, name)
	if not frappe.db.get_default("disable_standard_email_footer"):
		frappe.db.set_default("disable_standard_email_footer", 1)
	frappe.db.commit()
	return {"added": added}
