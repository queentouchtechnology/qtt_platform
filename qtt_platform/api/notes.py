"""
Office Pulse Notes (PROJ-0016 D2; rules in planning_rules.py): the business's knowledge — notes in collections
(How we work, Price lists, Recipes …) everyone can read and improve — and each person's own notes. Checklists in the
text ("- [ ]"), pins, meeting notes from a calendar event, and their action items sent to a board as cards.

  notes / note / save_note / delete_note    who sees a note: team (everyone), private (who wrote it), people (and the
                                            people chosen). Everyone who sees a team / people note can change it.
  toggle                                    tick a checkbox in the text
  from_event                                the meeting notes of a calendar event (made the first time)
  to_board                                  the open checkboxes → cards on a board
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from qtt_platform import planning_rules as pr

NOTE = "QTT Note"


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


def _names(ctx) -> dict:
	from qtt_platform.api.team import _names as n

	return n(ctx)


def _people(n) -> list[str]:
	try:
		return json.loads(n.people or "[]")
	except Exception:
		return []


def _sees(ctx, n) -> bool:
	if n.tenant != ctx.tenant:
		return False
	if n.visibility == "team":
		return True
	return n.owner_user == ctx.user or (n.visibility == "people" and ctx.user in _people(n))


def _get(ctx, name: str):
	n = frappe.get_doc(NOTE, name) if name and frappe.db.exists(NOTE, name) else None
	if not n or not _sees(ctx, n):
		frappe.throw(_("That note isn't here any more."), frappe.DoesNotExistError)
	return n


def _out(ctx, n, names, words=None, full=False) -> dict:
	done, total = pr.note_checks(n.body)
	o = {"name": n.name, "title": n.title, "collection": n.collection or "", "visibility": n.visibility, "pinned": bool(n.pinned),
		 "by": names.get(n.owner_user, n.owner_user), "changed_by": names.get(n.updated_by or n.owner_user, n.updated_by), "modified": str(n.modified),
		 "checks": [done, total], "snippet": pr.snippet(n.body, words or [], 120), "event": n.event or "", "mine": n.owner_user == ctx.user}
	if full:
		o.update({"body": n.body or "", "people": [{"user": u, "name": names.get(u, u)} for u in _people(n)],
				  "can_delete": n.owner_user == ctx.user or ctx.admin, "actions": pr.action_items(n.body)})
	return o


@frappe.whitelist(methods=["GET"])
def notes(q: str = "", collection: str = "", show: str = "all") -> dict:
	"""Notes this person sees (pinned first, then the newest changed): search words in the title and text, one
	collection, or show: all | mine | pinned. With the collections and how many notes each has."""
	ctx = _ctx()
	words = [w for w in str(q or "").lower().split() if w][:6]
	cond, args = ["tenant = %(t)s", "archived = 0", "(visibility = 'team' or owner_user = %(u)s or (visibility = 'people' and people like %(ul)s))"], \
		{"t": ctx.tenant, "u": ctx.user, "ul": f'%"{ctx.user}"%'}
	for i, w in enumerate(words):
		cond.append(f"(title like %(w{i})s or body like %(w{i})s)")
		args[f"w{i}"] = f"%{w}%"
	if collection:
		cond.append("collection = %(c)s")
		args["c"] = collection
	if show == "mine":
		cond.append("owner_user = %(u)s")
	elif show == "pinned":
		cond.append("pinned = 1")
	rows = frappe.db.sql(f"select * from `tab{NOTE}` where {' and '.join(cond)} order by pinned desc, modified desc limit 300", args, as_dict=True)
	names = _names(ctx)
	cols = frappe.db.sql(f"""select collection, count(*) n from `tab{NOTE}` where tenant = %(t)s and archived = 0 and ifnull(collection, '') != ''
		and (visibility = 'team' or owner_user = %(u)s or (visibility = 'people' and people like %(ul)s)) group by collection order by collection""", args, as_dict=True)
	return {"notes": [_out(ctx, frappe._dict(r), names, words) for r in rows], "collections": [{"name": c.collection, "count": c.n} for c in cols]}


@frappe.whitelist(methods=["GET"])
def note(name: str) -> dict:
	"""One note with its text, its open action items and who it's shared with."""
	ctx = _ctx()
	return _out(ctx, _get(ctx, name), _names(ctx), full=True)


@frappe.whitelist(methods=["POST"])
def save_note(data=None) -> dict:
	"""Make or change a note. data: {name, title, body, collection, visibility: team | private | people, people: [logins],
	pinned, base: the `modified` it was opened at}. When someone else changed it since `base` →
	{conflict: true, theirs: their note} and nothing is saved (unless force)."""
	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	new = not d.get("name")
	n = frappe.get_doc({"doctype": NOTE, "tenant": ctx.tenant, "owner_user": ctx.user}) if new else _get(ctx, d["name"])
	if not new and d.get("base") and not cint(d.get("force")) and get_datetime(d["base"]) < get_datetime(n.modified) and n.updated_by != ctx.user:
		return {"conflict": True, "theirs": _out(ctx, n, _names(ctx), full=True)}
	title = str(d.get("title") or "").strip()[:140]
	body = str(d.get("body") if d.get("body") is not None else (n.body or ""))[:200000]
	if not title:
		title = (body.strip().split("\n", 1)[0].lstrip("# ").strip() or _("Untitled"))[:140]
	n.title, n.body = title, body
	if "collection" in d:
		n.collection = pr.clean_collection(d.get("collection"))
	if "visibility" in d or new:
		if not new and n.owner_user != ctx.user and d.get("visibility", n.visibility) != n.visibility:
			frappe.throw(_("Only who wrote this note can change who sees it."), frappe.PermissionError)
		n.visibility = d.get("visibility") if d.get("visibility") in ("team", "private", "people") else "team"
	if "people" in d and (new or n.owner_user == ctx.user):
		from qtt_platform.api.team import _people as ppl

		everyone = ppl(ctx.tenant)
		n.people = json.dumps([u for u in dict.fromkeys(d.get("people") or []) if u in everyone and u != n.owner_user])
	if "pinned" in d:
		n.pinned = 1 if cint(d["pinned"]) else 0
	if d.get("event"):
		n.event = str(d["event"])[:140]
	n.updated_by = ctx.user
	n.save(ignore_permissions=True)
	return _out(ctx, n, _names(ctx), full=True)


@frappe.whitelist(methods=["POST"])
def delete_note(name: str) -> dict:
	"""Delete a note (who wrote it, owners and admins)."""
	ctx = _ctx()
	n = _get(ctx, name)
	if n.owner_user != ctx.user and not ctx.admin:
		frappe.throw(_("Only who wrote this note, or an owner or admin, can delete it."), frappe.PermissionError)
	frappe.delete_doc(NOTE, n.name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def toggle(name: str, index: int) -> dict:
	"""Tick or untick the index-th checkbox in the note's text."""
	ctx = _ctx()
	n = _get(ctx, name)
	try:
		n.body = pr.toggle_check(n.body, cint(index))
	except ValueError as e:
		frappe.throw(_(str(e)))
	n.updated_by = ctx.user
	n.save(ignore_permissions=True)
	return _out(ctx, n, _names(ctx), full=True)


@frappe.whitelist(methods=["POST"])
def from_event(event: str) -> dict:
	"""The meeting notes of a calendar event: who's invited, the agenda, notes, decisions and action items. Made the first
	time (shared like the event: a team event → a team note, a private one → the people invited); opened after that."""
	from qtt_platform.api import team_calendar as tc

	ctx = _ctx()
	ev = tc._get(ctx, event)
	have = frappe.db.get_value(NOTE, {"tenant": ctx.tenant, "event": ev.name}, "name")
	if have and _sees(ctx, frappe.get_doc(NOTE, have)):
		return note(have)
	names = _names(ctx)
	people = [names.get(ev.organizer, ev.organizer)] + [names.get(a.user, a.user) if a.user else (a.guest_name or a.email) for a in ev.attendees
														 if a.response != "no"]
	title, body = pr.meeting_notes(ev.title, tc._when_text(ev), ev.location or ev.meeting_url or "", list(dict.fromkeys(people)))
	team = ev.visibility == "team"
	return save_note({"title": title, "body": body, "collection": _("Meeting notes"), "visibility": "team" if team else "people",
					  "people": [] if team else [ev.organizer] + [a.user for a in ev.attendees if a.user], "event": ev.name})


@frappe.whitelist(methods=["POST"])
def to_board(name: str, board: str, list: str | None = None) -> dict:
	"""The note's open checkboxes become cards on a board (on a list; the first when none)."""
	from qtt_platform.api import boards

	ctx = _ctx()
	n = _get(ctx, name)
	items = pr.action_items(n.body)
	if not items:
		frappe.throw(_("This note has no open checkboxes to send."))
	return boards.cards_from(board, items, list, source=f"note:{n.name}")
