"""
Office Pulse Calendar (PROJ-0016 C1; rules in calendar_rules.py): the business's team calendar and each person's own
events, with invitations, answers, reminders and a subscription link for other calendar apps.

  events / event               what this person sees between two dates (repeats expanded): team events, their own,
                               the ones they're invited to
  save_event / delete_event    the organiser (and owners / admins for team events); people in the business are told
                               on their phones, people outside get an email invitation (.ics) — and updates / cancellations
  respond                      yes / no / maybe
  feed_link / feed             a private link (with a key) other calendar apps subscribe to; new_feed_link changes the key
  remind                       every 5 minutes: reminders on the phone before events (organiser and everyone not saying no)
"""

import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_url, getdate, now_datetime
from werkzeug.wrappers import Response

from qtt_platform import calendar_rules as cr

EVENT = "QTT Calendar Event"
COLORS = ("#2f7bff", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#64748b")


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


def _attendee_users(doc) -> list[str]:
	return [a.user for a in doc.attendees if a.user]


def _may_edit(ctx, doc) -> bool:
	return doc.organizer == ctx.user or (doc.visibility == "team" and ctx.admin)


def _get(ctx, name: str):
	doc = frappe.get_doc(EVENT, name) if frappe.db.exists(EVENT, name) else None
	if not doc or doc.tenant != ctx.tenant or not cr.visible(doc.as_dict(), ctx.user, _attendee_users(doc)):
		frappe.throw(_("That event isn't here any more."), frappe.DoesNotExistError)
	return doc


def _occ_out(ctx, ev, s, e, names: dict, mine_resp: str | None) -> dict:
	return {"name": ev.name, "title": ev.title, "start": str(s), "end": str(e), "all_day": bool(ev.all_day), "location": ev.location or "",
			"color": ev.color or COLORS[0], "visibility": ev.visibility, "organizer": names.get(ev.organizer, ev.organizer), "mine": ev.organizer == ctx.user,
			"response": mine_resp, "repeat": ev.repeat or "", "meeting_url": ev.meeting_url or ""}


@frappe.whitelist(methods=["GET"])
def events(start: str, end: str) -> dict:
	"""What this person sees from start to end (dates or date-times): team events, their own and those they're invited to,
	each repeat as its own occurrence."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	frm, to = cr.parse_when(start), cr.parse_when(end)
	if not frm or not to or to <= frm or (to - frm).days > 400:
		frappe.throw(_("Choose dates up to a year apart."))
	rows = frappe.db.sql(f"""select distinct e.name from `tab{EVENT}` e left join `tabQTT Calendar Attendee` a on a.parent = e.name and a.parenttype = %s
		where e.tenant = %s and e.starts_at < %s and (ifnull(e.`repeat`, '') != '' or e.ends_at > %s)
		and (e.visibility = 'team' or e.organizer = %s or a.user = %s)""", (EVENT, ctx.tenant, to, frm, ctx.user, ctx.user), pluck="name")
	names = _names(ctx)
	out = []
	for n in rows:
		ev = frappe.get_doc(EVENT, n)
		resp = next((a.response for a in ev.attendees if a.user == ctx.user), None)
		for s, e in cr.occurrences(get_datetime(ev.starts_at), get_datetime(ev.ends_at), ev.repeat or "", getdate(ev.repeat_until) if ev.repeat_until else None, frm, to):
			out.append(_occ_out(ctx, ev, s, e, names, resp))
	out.sort(key=lambda o: (o["start"], o["title"]))
	return {"events": out, "colors": list(COLORS)}


@frappe.whitelist(methods=["GET"])
def event(name: str) -> dict:
	"""One event with everyone invited and their answers; whether this person may change it."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	doc = _get(ctx, name)
	names = _names(ctx)
	return {"name": doc.name, "title": doc.title, "start": str(doc.starts_at), "end": str(doc.ends_at), "all_day": bool(doc.all_day), "visibility": doc.visibility,
			"location": doc.location or "", "meeting_url": doc.meeting_url or "", "notes": doc.notes or "", "color": doc.color or COLORS[0],
			"repeat": doc.repeat or "", "repeat_until": str(doc.repeat_until or ""), "remind_minutes": doc.remind_minutes if doc.remind_minutes is not None else 15,
			"organizer": names.get(doc.organizer, doc.organizer), "organizer_user": doc.organizer, "can_edit": _may_edit(ctx, doc),
			"attendees": [{"user": a.user, "email": a.email, "title": names.get(a.user, a.user) if a.user else (a.guest_name or a.email), "response": a.response}
						  for a in doc.attendees],
			"response": next((a.response for a in doc.attendees if a.user == ctx.user), None)}


def _people_ok(ctx, users: list[str]) -> list[str]:
	from qtt_platform.api.team import _people

	people = _people(ctx.tenant)
	return [u for u in dict.fromkeys(users) if u in people]


@frappe.whitelist(methods=["POST"])
def save_event(data=None) -> dict:
	"""Make or change an event. data: {name, title, start, end, all_day, visibility: team | private, location, meeting_url,
	notes, color, repeat: "" | daily | weekdays | weekly | monthly | yearly, repeat_until, remind_minutes, people: [logins],
	guests: [emails]}. New people are told; outside guests get an email invitation (and an update when it changes)."""
	from qtt_platform import files_rules as fr

	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	start, end = cr.parse_when(d.get("start")), cr.parse_when(d.get("end"))
	if not str(d.get("title") or "").strip():
		frappe.throw(_("Give the event a title."))
	if not start:
		frappe.throw(_("Choose when it starts."))
	all_day = bool(d.get("all_day"))
	if all_day:
		start = start.replace(hour=0, minute=0, second=0)
		end = (end or start).replace(hour=23, minute=59, second=0)
	end = end or start + timedelta(hours=1)
	if end < start:
		frappe.throw(_("It can't end before it starts."))
	if d.get("repeat", "") not in cr.REPEATS:
		frappe.throw(_("Choose how it repeats."))
	new = not d.get("name")
	doc = frappe.get_doc({"doctype": EVENT, "tenant": ctx.tenant, "organizer": ctx.user}) if new else _get(ctx, d["name"])
	if not new and not _may_edit(ctx, doc):
		frappe.throw(_("Only the organiser can change this event."), frappe.PermissionError)
	before = {(a.user or a.email) for a in doc.attendees}
	changed_time = (not new) and (get_datetime(doc.starts_at) != start or get_datetime(doc.ends_at) != end or (doc.repeat or "") != d.get("repeat", ""))
	doc.title = str(d["title"]).strip()[:140]
	doc.starts_at, doc.ends_at, doc.all_day = start, end, 1 if all_day else 0
	doc.visibility = "private" if d.get("visibility") == "private" else "team"
	for f, n in (("location", 200), ("meeting_url", 500), ("notes", 4000)):
		doc.set(f, str(d.get(f) or "").strip()[:n])
	doc.color = d.get("color") if d.get("color") in COLORS else (doc.color or COLORS[0])
	doc.repeat = d.get("repeat") or ""
	doc.repeat_until = getdate(d["repeat_until"]) if d.get("repeat_until") and doc.repeat else None
	doc.remind_minutes = int(d["remind_minutes"]) if str(d.get("remind_minutes", "")).lstrip("-").isdigit() else 15
	users = [u for u in _people_ok(ctx, d.get("people") or []) if u != doc.organizer]
	guests = fr.emails(", ".join(d.get("guests") or []) if isinstance(d.get("guests"), list) else d.get("guests"))
	keep = {(a.user or a.email): a for a in doc.attendees}
	doc.set("attendees", [])
	for u in users:
		doc.append("attendees", {"user": u, "response": keep[u].response if u in keep else "needs"})
	for e in guests:
		doc.append("attendees", {"email": e, "guest_name": keep[e].guest_name if e in keep else "", "response": keep[e].response if e in keep else "needs"})
	if changed_time:
		doc.sequence = (doc.sequence or 0) + 1  # calendar apps take the newest version
	doc.save(ignore_permissions=True)
	added = [a for a in doc.attendees if (a.user or a.email) not in before]
	_tell(ctx, doc, added, "invite")
	if changed_time:
		_tell(ctx, doc, [a for a in doc.attendees if (a.user or a.email) in before], "update")
	removed = before - {(a.user or a.email) for a in doc.attendees}
	if removed:
		_cancel_for(ctx, doc, removed)
	return event(doc.name)


@frappe.whitelist(methods=["POST"])
def delete_event(name: str) -> dict:
	"""Delete an event (the organiser; owners / admins for team events). Everyone invited is told."""
	ctx = _ctx()
	doc = _get(ctx, name)
	if not _may_edit(ctx, doc):
		frappe.throw(_("Only the organiser can delete this event."), frappe.PermissionError)
	_cancel_for(ctx, doc, {(a.user or a.email) for a in doc.attendees})
	frappe.delete_doc(EVENT, doc.name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def respond(name: str, answer: str) -> dict:
	"""Your answer to an invitation: yes, no or maybe (the organiser is told)."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	if answer not in ("yes", "no", "maybe"):
		frappe.throw(_("Answer yes, no or maybe."))
	doc = _get(ctx, name)
	row = next((a for a in doc.attendees if a.user == ctx.user), None)
	if not row:
		if doc.visibility != "team":
			frappe.throw(_("You aren't invited to this event."), frappe.PermissionError)
		row = doc.append("attendees", {"user": ctx.user})
	row.response = answer
	doc.save(ignore_permissions=True)
	me = _names(ctx).get(ctx.user, ctx.user)
	word = {"yes": _("is coming to"), "no": _("can't come to"), "maybe": _("might come to")}[answer]
	_push([doc.organizer], f"{me} {word} {doc.title}", _when_text(doc), doc)
	return event(name)


# ---- telling people ----------------------------------------------------------------------------------------------------
def _when_text(doc) -> str:
	s = get_datetime(doc.starts_at)
	return s.strftime("%a %d %b") + ("" if doc.all_day else s.strftime(", %I:%M %p").replace(" 0", " "))


def _push(users: list[str], title: str, body: str, doc) -> None:
	try:
		from qtt_platform.push import notify

		notify([u for u in users if u], title=title, body=body, data={"kind": "calendar", "tenant": doc.tenant, "event": doc.name})
	except Exception:
		pass


def _ics(doc, *, cancelled: bool = False) -> str:
	from qtt_platform.api.team import _names_of

	names = _names_of([doc.organizer] + [a.user for a in doc.attendees if a.user])
	org_mail = frappe.db.get_value("User", doc.organizer, "email") or doc.organizer
	att = [(frappe.db.get_value("User", a.user, "email") or a.user, names.get(a.user, a.user), a.response) if a.user else (a.email, a.guest_name or a.email, a.response)
		   for a in doc.attendees]
	ev = cr.ics_event(uid=f"{doc.name}@queentouchtech.in", title=doc.title, start=get_datetime(doc.starts_at), end=get_datetime(doc.ends_at),
					  all_day=bool(doc.all_day), location=doc.location or "", notes=doc.notes or "", url=doc.meeting_url or "", repeat=doc.repeat or "",
					  until=getdate(doc.repeat_until) if doc.repeat_until else None, organizer=(org_mail, names.get(doc.organizer, doc.organizer)),
					  attendees=att, sequence=doc.sequence or 0, cancelled=cancelled)
	return cr.ics_calendar([ev], method="CANCEL" if cancelled else "REQUEST")


def _mail_guests(doc, emails: list[str], kind: str) -> None:
	if not emails:
		return
	try:
		org = frappe.db.get_value("User", doc.organizer, "full_name") or doc.organizer
		business = frappe.db.get_value("QTT Tenant", doc.tenant, "tenant_name") or "QTT OS"
		head = {"invite": _("{0} invited you"), "update": _("{0} changed the time"), "cancel": _("{0} cancelled")}[kind].format(org)
		body = (f"<p>{frappe.utils.escape_html(head)}: <b>{frappe.utils.escape_html(doc.title)}</b></p><p>{frappe.utils.escape_html(_when_text(doc))}"
				f"{(' · ' + frappe.utils.escape_html(doc.location)) if doc.location else ''}</p>"
				+ (f"<p><a href='{frappe.utils.escape_html(doc.meeting_url)}'>{frappe.utils.escape_html(doc.meeting_url)}</a></p>" if doc.meeting_url else "")
				+ f"<p style='color:#6b7280'>{frappe.utils.escape_html(business)} · QTT OS</p>")
		frappe.sendmail(recipients=emails, subject=f"{head}: {doc.title} — {_when_text(doc)}", message=body,
						attachments=[{"fname": "invite.ics", "fcontent": _ics(doc, cancelled=kind == "cancel")}], reply_to=frappe.db.get_value("User", doc.organizer, "email"))
	except Exception:
		frappe.log_error(title="Calendar: invitation email not sent")


def _tell(ctx, doc, rows, kind: str) -> None:
	from qtt_platform.api.team import _names

	if not rows:
		return
	me = _names(ctx).get(ctx.user, ctx.user)
	users = [a.user for a in rows if a.user and a.user != ctx.user]
	title = (_("{0} invited you: {1}") if kind == "invite" else _("{0} changed {1}")).format(me, doc.title)
	_push(users, title, _when_text(doc), doc)
	_mail_guests(doc, [a.email for a in rows if a.email], kind)


def _cancel_for(ctx, doc, who: set) -> None:
	"""Tell people taken off an event (or everyone, when it's deleted): people in the business on their phones, guests
	by email with a cancellation for their calendar."""
	members = {w for w in who if w and frappe.db.exists("QTT Tenant Membership", {"tenant": doc.tenant, "user": w})}
	_push([u for u in members if u != ctx.user], _("Cancelled: {0}").format(doc.title), _when_text(doc), doc)
	_mail_guests(doc, sorted(w for w in who if w and w not in members), "cancel")


# ---- the subscription link ---------------------------------------------------------------------------------------------
def _feed_secret() -> str:
	from frappe.utils.password import get_encryption_key

	return "qtt-calendar-feed|" + get_encryption_key()


def _feed_key(user: str, tenant: str, rotate: bool = False) -> str:
	k = f"qtt_cal_feed|{tenant}|{user}"
	v = frappe.db.get_default(k)
	if rotate or not v:
		v = secrets.token_hex(8)
		frappe.db.set_default(k, v)
	return v


@frappe.whitelist(methods=["GET"])
def feed_link() -> dict:
	"""A private link for Google Calendar, Outlook or a phone's calendar to subscribe to (your events and the team's).
	Anyone with it can read them — change it with new_feed_link."""
	from qtt_platform import workplace_rules as wr

	ctx = _ctx()
	t = wr.jwt_hs256({"u": ctx.user, "t": ctx.tenant, "k": _feed_key(ctx.user, ctx.tenant)}, _feed_secret())
	url = get_url(f"/api/method/qtt_platform.api.team_calendar.feed?t={t}")
	return {"url": url, "webcal": url.replace("https://", "webcal://", 1)}


@frappe.whitelist(methods=["POST"])
def new_feed_link() -> dict:
	"""A new subscription link — the old one stops working."""
	ctx = _ctx()
	_feed_key(ctx.user, ctx.tenant, rotate=True)
	return feed_link()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def feed(t: str = ""):
	"""The calendar file other calendar apps read (a link from feed_link)."""
	from qtt_platform import workplace_rules as wr

	c = wr.jwt_verify(t, _feed_secret())
	if not c or c.get("k") != frappe.db.get_default(f"qtt_cal_feed|{c.get('t')}|{c.get('u')}") or not frappe.db.exists(
			"QTT Tenant Membership", {"tenant": c.get("t"), "user": c.get("u"), "status": "active"}):
		return Response("This calendar link has ended.", status=410)
	since = add_to_date(now_datetime(), days=-90)
	rows = frappe.db.sql(f"""select distinct e.name from `tab{EVENT}` e left join `tabQTT Calendar Attendee` a on a.parent = e.name and a.parenttype = %s
		where e.tenant = %s and (ifnull(e.`repeat`, '') != '' or e.ends_at > %s) and (e.visibility = 'team' or e.organizer = %s or a.user = %s)""",
						 (EVENT, c["t"], since, c["u"], c["u"]), pluck="name")
	business = frappe.db.get_value("QTT Tenant", c["t"], "tenant_name") or "QTT OS"
	evs = []
	for n in rows[:1000]:
		doc = frappe.get_doc(EVENT, n)
		evs.append(cr.ics_event(uid=f"{doc.name}@queentouchtech.in", title=doc.title, start=get_datetime(doc.starts_at), end=get_datetime(doc.ends_at),
								all_day=bool(doc.all_day), location=doc.location or "", notes=doc.notes or "", url=doc.meeting_url or "",
								repeat=doc.repeat or "", until=getdate(doc.repeat_until) if doc.repeat_until else None, sequence=doc.sequence or 0))
	r = Response(cr.ics_calendar(evs, name=f"{business} · QTT OS"), mimetype="text/calendar")
	r.headers["Cache-Control"] = "no-store"
	return r


# ---- reminders ---------------------------------------------------------------------------------------------------------
def remind() -> None:
	"""Scheduler (every 5 minutes): a reminder on the phone before each event (up to a day before)."""
	now = now_datetime()
	ahead = now + timedelta(days=1, minutes=10)
	try:
		rows = frappe.db.sql(f"""select name from `tab{EVENT}` where ifnull(remind_minutes, 0) >= 0 and starts_at < %s
			and (ifnull(`repeat`, '') != '' or starts_at > %s)""", (ahead, now), pluck="name")
		for n in rows:
			doc = frappe.get_doc(EVENT, n)
			for s, _e in cr.occurrences(get_datetime(doc.starts_at), get_datetime(doc.ends_at), doc.repeat or "",
										getdate(doc.repeat_until) if doc.repeat_until else None, now, ahead):
				if not cr.due_reminders(s, int(doc.remind_minutes or 0), now):
					continue
				key = f"qtt_cal_reminded|{doc.name}|{s.isoformat()}"
				if frappe.cache().get_value(key):
					continue
				frappe.cache().set_value(key, 1, expires_in_sec=2 * 86400)
				users = [doc.organizer] + [a.user for a in doc.attendees if a.user and a.response != "no"]
				when = _("now") if int(doc.remind_minutes or 0) == 0 else _("in {0} min").format(doc.remind_minutes) if doc.remind_minutes < 60 else s.strftime("%I:%M %p")
				_push(list(dict.fromkeys(users)), f"{doc.title} — {when}", doc.location or _("Calendar"), doc)
	except Exception:
		frappe.log_error(title="Calendar: reminders failed")
