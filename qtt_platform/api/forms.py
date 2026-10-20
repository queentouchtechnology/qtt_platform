"""
Office Pulse Forms (PROJ-0016 D4; rules in planning_rules.py): forms and surveys.

  public forms   a link for anyone (app.queentouchtech.in/f/<key>) — enquiries, orders, feedback, registrations.
                 Answers can go straight into the address book (a name / email / phone question gives the contact).
  team surveys   answered in the app by people in the business (anonymous when chosen) — polls, feedback, lunch orders.

  forms / form / save_form / delete_form / new_link    the forms this person made (owners and admins see all)
  responses / summary / export_csv                     answers, a summary per question, a spreadsheet
  to_answer / answer                                   team surveys waiting for this person, and their answer
  public_form / submit / page                          the public page and its calls (no login)

Who made it is told on the phone for each answer (unless switched off).
"""

import hashlib
import json
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, get_url, now_datetime
from werkzeug.wrappers import Response

from qtt_platform import planning_rules as pr

FORM = "QTT Form"
RESP = "QTT Form Response"
ENDED = {"closed": "This form isn't taking answers now.", "ended": "This form has ended.", "full": "This form has all the answers it needs.",
		 "gone": "This form isn't here any more."}


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


def _qs(f) -> list:
	try:
		return json.loads(f.questions or "[]")
	except Exception:
		return []


def _link(f) -> str:
	return get_url(f"/f/{f.key}") if f.audience == "public" and f.key else ""


def _mine(ctx, f) -> bool:
	return f.tenant == ctx.tenant and (f.owner_user == ctx.user or ctx.admin)


def _get(ctx, name: str, manage=True):
	f = frappe.get_doc(FORM, name) if name and frappe.db.exists(FORM, name) else None
	if not f or f.tenant != ctx.tenant or (manage and not _mine(ctx, f)):
		frappe.throw(_("That form isn't here any more."), frappe.DoesNotExistError)
	return f


def _out(ctx, f, names=None, full=False) -> dict:
	from qtt_platform.api.team import _names

	names = names or _names(ctx)
	closed = pr.form_open(f.as_dict(), cint(f.responses), now_datetime())
	o = {"name": f.name, "title": f.title, "description": f.description or "", "audience": f.audience, "anonymous": bool(f.anonymous),
		 "accepting": bool(f.accepting), "responses": cint(f.responses), "link": _link(f), "closed": closed, "by": names.get(f.owner_user, f.owner_user),
		 "closes_at": str(f.closes_at) if f.closes_at else None, "questions_count": len(_qs(f))}
	if full:
		o.update({"questions": _qs(f), "one_each": bool(f.one_each), "max_responses": cint(f.max_responses) or None, "thanks": f.thanks or "",
				  "to_contacts": bool(f.to_contacts), "contact_kind": f.contact_kind or "Customer", "notify": bool(f.notify), "types": pr.QTYPES})
	return o


@frappe.whitelist(methods=["GET"])
def forms() -> dict:
	"""The forms this person made (owners and admins: all the business's), the newest first; team surveys waiting for
	their answer; the kinds of questions."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	f = {"tenant": ctx.tenant, "archived": 0}
	if not ctx.admin:
		f["owner_user"] = ctx.user
	names = _names(ctx)
	rows = [_out(ctx, frappe.get_doc(FORM, n), names) for n in frappe.get_all(FORM, filters=f, order_by="modified desc", limit=300, pluck="name")]
	return {"forms": rows, "to_answer": to_answer()["surveys"], "types": pr.QTYPES}


@frappe.whitelist(methods=["GET"])
def form(name: str) -> dict:
	"""One form with its questions and settings (who made it, owners and admins)."""
	ctx = _ctx()
	return _out(ctx, _get(ctx, name), full=True)


@frappe.whitelist(methods=["POST"])
def save_form(data=None) -> dict:
	"""Make or change a form. data: {name, title, description, questions: [{id, type, label, help, required, options}],
	audience: public | team, anonymous, one_each, accepting, closes_at, max_responses, thanks, to_contacts,
	contact_kind, notify}. Questions with answers already keep their ids, so the answers still line up."""
	from qtt_platform.api.customers import KINDS

	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	new = not d.get("name")
	f = frappe.get_doc({"doctype": FORM, "tenant": ctx.tenant, "owner_user": ctx.user, "key": secrets.token_urlsafe(12), "accepting": 1, "notify": 1}) \
		if new else _get(ctx, d["name"])
	title = str(d.get("title") or "").strip()[:140]
	if not title:
		frappe.throw(_("Give the form a title."))
	try:
		f.questions = json.dumps(pr.clean_questions(d.get("questions")), ensure_ascii=False)
	except ValueError as e:
		frappe.throw(_(str(e)))
	f.title = title
	f.description = str(d.get("description") or "").strip()[:2000]
	if new or "audience" in d:
		if not new and cint(f.responses) and d.get("audience") != f.audience:
			frappe.throw(_("This form already has answers — make a new form to ask other people."))
		f.audience = "team" if d.get("audience") == "team" else "public"
	if new or "anonymous" in d:
		if not new and cint(f.responses) and bool(cint(d.get("anonymous"))) != bool(f.anonymous):
			frappe.throw(_("This form already has answers, so whether it's anonymous can't change."))
		f.anonymous = 1 if f.audience == "team" and cint(d.get("anonymous")) else 0
	for k in ("one_each", "accepting", "to_contacts", "notify"):
		if k in d:
			f.set(k, 1 if cint(d[k]) else 0)
	f.closes_at = get_datetime(d["closes_at"]) if d.get("closes_at") else None
	f.max_responses = cint(d.get("max_responses")) or None
	f.thanks = str(d.get("thanks") or "").strip()[:500]
	f.contact_kind = d.get("contact_kind") if d.get("contact_kind") in KINDS else "Customer"
	if f.audience == "team":
		f.to_contacts = 0
	f.save(ignore_permissions=True)
	return _out(ctx, f, full=True)


@frappe.whitelist(methods=["POST"])
def delete_form(name: str) -> dict:
	"""Delete a form and its answers."""
	ctx = _ctx()
	f = _get(ctx, name)
	frappe.db.delete(RESP, {"form": f.name})
	frappe.delete_doc(FORM, f.name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def new_link(name: str) -> dict:
	"""A new public link — the old one stops working."""
	ctx = _ctx()
	f = _get(ctx, name)
	f.key = secrets.token_urlsafe(12)
	f.save(ignore_permissions=True)
	return _out(ctx, f, full=True)


def _rows(f, start=0, limit=None):
	return frappe.get_all(RESP, filters={"form": f.name}, fields=["name", "answers", "user", "email", "respondent_name", "submitted_at", "contact"],
						  order_by="submitted_at desc", start=start, limit=limit or 0)


def _answers(r) -> dict:
	try:
		return json.loads(r.answers or "{}")
	except Exception:
		return {}


@frappe.whitelist(methods=["GET"])
def responses(name: str, start: int = 0) -> dict:
	"""A page of answers, the newest first (anonymous surveys: no names)."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	f = _get(ctx, name)
	names = _names(ctx)
	rows = _rows(f, cint(start), 51)
	return {"responses": [{"name": r.name, "at": str(r.submitted_at)[:16], "who": "" if f.anonymous else (names.get(r.user) or r.respondent_name or r.email or ""),
						   "answers": _answers(r), "contact": r.contact or ""} for r in rows[:50]],
			"has_more": len(rows) > 50, "questions": _qs(f)}


@frappe.whitelist(methods=["GET"])
def summary(name: str) -> dict:
	"""How people answered each question (counts, averages, the latest written answers)."""
	ctx = _ctx()
	f = _get(ctx, name)
	return {"title": f.title, "responses": cint(f.responses), "summary": pr.summary(_qs(f), [_answers(r) for r in _rows(f, limit=20000)])}


@frappe.whitelist(methods=["GET"])
def export_csv(name: str):
	"""The answers as a spreadsheet (.csv)."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	f = _get(ctx, name)
	names = _names(ctx)
	rows = [{**_answers(r), "_at": str(r.submitted_at)[:16], "_name": "" if f.anonymous else (names.get(r.user) or r.respondent_name or ""),
			 "_email": "" if f.anonymous else (r.email or (r.user if r.user else ""))} for r in reversed(_rows(f, limit=20000))]
	frappe.local.response.filename = f"{frappe.scrub(f.title)[:40] or 'form'}-answers.csv"
	frappe.local.response.filecontent = ("﻿" + pr.to_csv(_qs(f), rows)).encode("utf-8")
	frappe.local.response.type = "download"


# ---- answering ---------------------------------------------------------------------------------------------------------
def _seal(form: str, who: str) -> str:
	"""Who answered, kept so they answer once — not who they are (anonymous surveys)."""
	return hashlib.sha256(f"{form}|{who}|{frappe.local.conf.get('secret') or frappe.local.site}".encode()).hexdigest()[:40]


def _record(f, answers: dict, *, user=None, ip=None) -> dict:
	"""Check and keep an answer → {ok, thanks} or {errors}."""
	closed = pr.form_open(f.as_dict(), cint(f.responses), now_datetime())
	if closed:
		return {"closed": closed, "message": _(ENDED[closed])}
	qs = _qs(f)
	clean, errors = pr.check_answers(qs, answers if isinstance(answers, dict) else {})
	if errors:
		return {"errors": {k: _(v) for k, v in errors.items()}}
	contact = pr.contact_from(qs, clean)
	email = (contact or {}).get("email") or ""
	seal = _seal(f.name, user or email or ip or "")
	if cint(f.one_each) and (user or email or ip) and frappe.db.exists(RESP, {"form": f.name, "ip_hash": seal}):
		return {"closed": "answered", "message": _("You've already answered this form — thank you.")}
	r = frappe.get_doc({"doctype": RESP, "tenant": f.tenant, "form": f.name, "answers": json.dumps(clean, ensure_ascii=False), "submitted_at": now_datetime(),
						"user": None if f.anonymous else user, "email": "" if f.anonymous else email,
						"respondent_name": "" if f.anonymous else ((contact or {}).get("name") or ""), "ip_hash": seal}).insert(ignore_permissions=True)
	frappe.db.sql(f"update `tab{FORM}` set responses = ifnull(responses, 0) + 1 where name = %s", f.name)
	if cint(f.to_contacts) and contact:
		r.db_set("contact", _to_contacts(f, contact) or "", update_modified=False)
	if cint(f.notify) and f.owner_user != user:
		try:
			from qtt_platform import push

			who = "" if f.anonymous else ((contact or {}).get("name") or (frappe.db.get_value("User", user, "full_name") if user else ""))
			push.notify([f.owner_user], title=_("New answer: {0}").format(f.title), body=who or _("Someone answered your form"),
						data={"kind": "form_response", "tenant": f.tenant, "form": f.name}, collapse_key=f"form-{f.name}")
		except Exception:
			frappe.log_error(title="Forms: push failed")
	return {"ok": True, "thanks": f.thanks or _("Thank you — your answer was sent.")}


def _to_contacts(f, contact: dict) -> str | None:
	"""The person into the address book (unless they're there already by phone or email) → its name."""
	from qtt_platform.api.customers import clean_customer

	DT = "QTT Customer"
	for k in ("phone", "email"):
		if contact.get(k):
			have = frappe.db.get_value(DT, {"tenant": f.tenant, k: contact[k]}, "name")
			if have:
				return have
	try:
		country = frappe.db.get_value("QTT Tenant", f.tenant, "country")
		values = clean_customer({"customer_name": contact["name"], "phone": contact.get("phone"), "email": contact.get("email"),
								 "notes": _("From the form “{0}”").format(f.title)}, country)
		return frappe.get_doc({"doctype": DT, "tenant": f.tenant, "status": "Active", "source": "Form", "kind": f.contact_kind or "Customer", **values}
							  ).insert(ignore_permissions=True).name
	except Exception:
		frappe.log_error(title="Forms: contact not added")
		return None


@frappe.whitelist(methods=["GET"])
def to_answer() -> dict:
	"""Team surveys taking answers that this person hasn't answered yet."""
	ctx = _ctx()
	out = []
	for f in frappe.get_all(FORM, filters={"tenant": ctx.tenant, "audience": "team", "accepting": 1, "archived": 0}, fields=["*"], order_by="creation desc", limit=50):
		f = frappe._dict(f)
		if pr.form_open(f, cint(f.responses), now_datetime()):
			continue
		if frappe.db.exists(RESP, {"form": f.name, "ip_hash": _seal(f.name, ctx.user)}):
			continue
		out.append({"name": f.name, "title": f.title, "description": f.description or "", "anonymous": bool(f.anonymous),
					"closes_at": str(f.closes_at) if f.closes_at else None})
	return {"surveys": out}


@frappe.whitelist(methods=["GET"])
def survey(name: str) -> dict:
	"""A team survey to answer: its questions."""
	ctx = _ctx()
	f = _get(ctx, name, manage=False)
	if f.audience != "team":
		frappe.throw(_("That form isn't here any more."), frappe.DoesNotExistError)
	return {"name": f.name, "title": f.title, "description": f.description or "", "anonymous": bool(f.anonymous), "questions": _qs(f),
			"closed": pr.form_open(f.as_dict(), cint(f.responses), now_datetime())}


@frappe.whitelist(methods=["POST"])
def answer(name: str, answers=None) -> dict:
	"""This person's answer to a team survey (once each — anonymous surveys keep only that they answered)."""
	ctx = _ctx()
	f = _get(ctx, name, manage=False)
	if f.audience != "team":
		frappe.throw(_("That form isn't here any more."), frappe.DoesNotExistError)
	f.one_each = 1  # a team survey is always once each
	return _record(f, frappe.parse_json(answers) if isinstance(answers, str) else (answers or {}), user=ctx.user)


# ---- the public page ---------------------------------------------------------------------------------------------------
def _public(k: str):
	name = frappe.db.get_value(FORM, {"key": k, "audience": "public", "archived": 0}, "name") if k else None
	return frappe.get_doc(FORM, name) if name else None


@frappe.whitelist(allow_guest=True, methods=["GET"])
def public_form(k: str = "") -> dict:
	"""The form for the public page: title, the business's name, questions — or why it's closed."""
	f = _public(k)
	if not f:
		return {"closed": "gone", "message": _(ENDED["gone"])}
	closed = pr.form_open(f.as_dict(), cint(f.responses), now_datetime())
	biz = frappe.db.get_value("QTT Tenant", f.tenant, "tenant_name") or ""
	return {"title": f.title, "description": f.description or "", "business": biz, "questions": [] if closed else _qs(f), "closed": closed,
			"message": _(ENDED[closed]) if closed else ""}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=600)
def submit(k: str = "", answers: str = "{}", website: str = "") -> dict:
	"""An answer from the public page. `website` is a trap field people never fill in (robots do)."""
	f = _public(k)
	if not f:
		return {"closed": "gone", "message": _(ENDED["gone"])}
	if website:
		return {"ok": True, "thanks": f.thanks or _("Thank you — your answer was sent.")}
	try:
		data = json.loads(answers) if isinstance(answers, str) else answers
	except Exception:
		data = {}
	ip = getattr(frappe.local, "request_ip", "") or ""
	out = _record(f, data, ip=ip)
	frappe.db.commit()
	return out


@frappe.whitelist(allow_guest=True, methods=["GET"])
def page(k: str = ""):
	"""The public form page (app.queentouchtech.in/f/<key>)."""
	from qtt_platform.forms_page import html

	r = Response(html(k), mimetype="text/html")
	r.headers["Cache-Control"] = "no-store"
	r.headers["Referrer-Policy"] = "no-referrer"
	return r
