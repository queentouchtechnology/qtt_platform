"""
Office Pulse Boards (PROJ-0016 D1; rules in planning_rules.py): Kanban boards for the team — lists of cards with
people, labels, due dates, checklists and comments. Ready templates (to do, project, sales pipeline, hiring, content
calendar, customer issues). Team boards are for everyone in the business; members-only boards for the people on them.

  boards / board / save_board / delete_board     the boards this person sees; one with its lists and cards
  save_card / move_card / card / delete_card     cards (moving into the board's done list marks it done)
  comment / check                                a comment on a card; tick a checklist item
  cards_from                                     cards made from a note's action items (planning: meeting notes → board)

People given a card are told on their phones.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime

from qtt_platform import planning_rules as pr

BOARD = "QTT Board"
CARD = "QTT Board Card"


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


def _j(v, default):
	try:
		return json.loads(v) if v else default
	except Exception:
		return default


def _names(ctx) -> dict:
	from qtt_platform.api.team import _names as n

	return n(ctx)


def _board(ctx, name: str):
	b = frappe.get_doc(BOARD, name) if name and frappe.db.exists(BOARD, name) else None
	if not b or b.tenant != ctx.tenant or not pr.board_visible(b.as_dict(), ctx.user, ctx.admin, _j(b.members, [])):
		frappe.throw(_("That board isn't here any more."), frappe.DoesNotExistError)
	return b


def _card(ctx, name: str):
	c = frappe.get_doc(CARD, name) if name and frappe.db.exists(CARD, name) else None
	if not c or c.tenant != ctx.tenant:
		frappe.throw(_("That card isn't here any more."), frappe.DoesNotExistError)
	return c, _board(ctx, c.board)


def _people_ok(ctx, users) -> list[str]:
	from qtt_platform.api.team import _people

	people = _people(ctx.tenant)
	return [u for u in dict.fromkeys(users or []) if u in people]


def _board_out(ctx, b, counts=None) -> dict:
	members = _j(b.members, [])
	names = _names(ctx)
	return {"name": b.name, "title": b.title, "description": b.description or "", "visibility": b.visibility, "color": b.color or "",
			"lists": _j(b.lists, []), "labels": _j(b.labels, []), "done_list": b.done_list or "", "archived": bool(b.archived),
			"members": [{"user": u, "name": names.get(u, u)} for u in members], "made_by": names.get(b.created_by_user, b.created_by_user),
			"can_manage": pr.board_may_manage(b.as_dict(), ctx.user, ctx.admin), **(counts or {})}


def _card_out(ctx, c, names=None, full=False) -> dict:
	names = names or _names(ctx)
	people = _j(c.assignees, [])
	checks = _j(c.checklist, [])
	done, total = pr.progress(checks)
	comments = _j(c.comments, [])
	out = {"name": c.name, "board": c.board, "list": c.list_id, "position": c.position, "title": c.title, "due": str(c.due) if c.due else None,
		   "done": bool(c.done), "labels": _j(c.labels, []), "cover": c.cover or "", "people": [{"user": u, "name": names.get(u, u)} for u in people],
		   "checks": [done, total], "comments": len(comments), "has_description": bool((c.description or "").strip()),
		   "overdue": bool(c.due and not c.done and getdate(c.due) < getdate())}
	if full:
		out.update({"description": c.description or "", "checklist": checks, "source": c.source or "",
					"comment_list": [{**x, "by_name": names.get(x.get("by"), x.get("by"))} for x in comments],
					"made_by": names.get(c.created_by_user, c.created_by_user)})
	return out


@frappe.whitelist(methods=["GET"])
def boards(archived: int = 0) -> dict:
	"""The boards this person sees, with their open and overdue card counts; the ready templates."""
	ctx = _ctx()
	rows = frappe.get_all(BOARD, filters={"tenant": ctx.tenant, "archived": cint(archived)}, fields=["name"], order_by="modified desc", limit=300, pluck="name")
	stats = {r.board: r for r in frappe.db.sql(f"""select board, sum(done = 0) open, sum(done = 0 and due < curdate()) overdue
		from `tab{CARD}` where tenant = %s and archived = 0 group by board""", ctx.tenant, as_dict=True)}
	out = []
	for n in rows:
		b = frappe.get_doc(BOARD, n)
		if pr.board_visible(b.as_dict(), ctx.user, ctx.admin, _j(b.members, [])):
			s = stats.get(n) or {}
			out.append(_board_out(ctx, b, {"open": cint(s.get("open")), "overdue": cint(s.get("overdue"))}))
	return {"boards": out, "templates": [{"key": k, "title": v[0], "lists": v[1]} for k, v in pr.TEMPLATES.items()]}


@frappe.whitelist(methods=["GET"])
def board(name: str, mine: int = 0, label: str = "", q: str = "") -> dict:
	"""A board with its cards by list (positions in order). Filters: only mine, a label, words in the title."""
	ctx = _ctx()
	b = _board(ctx, name)
	names = _names(ctx)
	cards = frappe.get_all(CARD, filters={"board": b.name, "archived": 0}, fields=["*"], order_by="position asc", limit=2000)
	words = [w for w in str(q or "").lower().split() if w]
	out = []
	for c in cards:
		c = frappe._dict(c)
		if cint(mine) and ctx.user not in _j(c.assignees, []):
			continue
		if label and label not in _j(c.labels, []):
			continue
		if words and not all(w in (c.title or "").lower() for w in words):
			continue
		out.append(_card_out(ctx, c, names))
	from qtt_platform.api.team import _people

	people = [{"user": u, "name": p["name"]} for u, p in _people(ctx.tenant).items()]
	return {**_board_out(ctx, b), "cards": out, "people": people}


@frappe.whitelist(methods=["POST"])
def save_board(data=None) -> dict:
	"""Make or change a board. data: {name, title, description, visibility: team | members, members: [logins],
	lists: [{id, title}], labels: [{id, name, color}], done_list, color, template (new boards: a ready one)}.
	Cards on a list that's taken away move to the first list."""
	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	new = not d.get("name")
	if new:
		t = pr.from_template(d.get("template") or "simple")
		b = frappe.get_doc({"doctype": BOARD, "tenant": ctx.tenant, "created_by_user": ctx.user, "template": d.get("template") or "simple",
							"lists": json.dumps(t["lists"]), "labels": json.dumps(t["labels"]), "done_list": t["done_list"], "title": t["title"]})
	else:
		b = _board(ctx, d["name"])
		if not pr.board_may_manage(b.as_dict(), ctx.user, ctx.admin):
			frappe.throw(_("Only who made this board, or an owner or admin, can change it."), frappe.PermissionError)
	try:
		if "lists" in d and not new:
			b.lists = json.dumps(pr.clean_lists(d["lists"]))
		if "labels" in d and not (new and not d["labels"]):
			b.labels = json.dumps(pr.clean_labels(d["labels"]))
	except ValueError as e:
		frappe.throw(_(str(e)))
	title = str(d.get("title") or "").strip()[:140]
	if title:
		b.title = title
	if "description" in d:
		b.description = str(d.get("description") or "").strip()[:1000]
	if "visibility" in d:
		b.visibility = "members" if d.get("visibility") == "members" else "team"
	if "members" in d or new:
		b.members = json.dumps([u for u in _people_ok(ctx, d.get("members") or []) if u != b.created_by_user])
	if d.get("color") is not None:
		b.color = str(d.get("color") or "")[:9]
	list_ids = [x["id"] for x in _j(b.lists, [])]
	if "done_list" in d:
		b.done_list = d["done_list"] if d["done_list"] in list_ids else ""
	elif b.done_list not in list_ids:
		b.done_list = ""
	if "archived" in d:
		b.archived = 1 if cint(d["archived"]) else 0
	b.save(ignore_permissions=True)
	if not new:
		frappe.db.sql(f"update `tab{CARD}` set list_id = %s where board = %s and list_id not in %s", (list_ids[0], b.name, tuple(list_ids)))
	return board(b.name)


@frappe.whitelist(methods=["POST"])
def delete_board(name: str) -> dict:
	"""Delete a board and its cards (who made it, owners and admins)."""
	ctx = _ctx()
	b = _board(ctx, name)
	if not pr.board_may_manage(b.as_dict(), ctx.user, ctx.admin):
		frappe.throw(_("Only who made this board, or an owner or admin, can delete it."), frappe.PermissionError)
	frappe.db.delete(CARD, {"board": b.name})
	frappe.delete_doc(BOARD, b.name, ignore_permissions=True, force=True)
	return {"ok": True}


def _end_position(board: str, list_id: str) -> float:
	last = frappe.db.sql(f"select max(position) from `tab{CARD}` where board = %s and list_id = %s and archived = 0", (board, list_id))[0][0]
	return pr.between(last, None) if last is not None else pr.between(None, None)


def _tell(ctx, c, users, title: str) -> None:
	users = [u for u in users if u != ctx.user]
	if not users:
		return
	try:
		from qtt_platform import push

		push.notify(users, title=title, body=c.title[:140], data={"kind": "board_card", "tenant": ctx.tenant, "board": c.board, "card": c.name},
					collapse_key=f"card-{c.name}")
	except Exception:
		frappe.log_error(title="Boards: push failed")


def _set_done(c, b, done: bool) -> None:
	c.done = 1 if done else 0
	c.done_at = now_datetime() if done else None


@frappe.whitelist(methods=["POST"])
def save_card(data=None) -> dict:
	"""Make or change a card. data: {name, board, list, title, description, people: [logins], labels: [label ids], due,
	done, checklist: [{text, done}], cover}. New people on it are told."""
	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	new = not d.get("name")
	if new:
		b = _board(ctx, d.get("board"))
		lists = [x["id"] for x in _j(b.lists, [])]
		list_id = d.get("list") if d.get("list") in lists else lists[0]
		c = frappe.get_doc({"doctype": CARD, "tenant": ctx.tenant, "board": b.name, "list_id": list_id, "created_by_user": ctx.user,
							"position": _end_position(b.name, list_id), "source": str(d.get("source") or "")[:140]})
		if list_id == b.done_list:
			_set_done(c, b, True)
	else:
		c, b = _card(ctx, d["name"])
	if "title" in d or new:
		title = str(d.get("title") or "").strip()[:140]
		if not title:
			frappe.throw(_("Say what the card is about."))
		c.title = title
	before = set(_j(c.assignees, []))
	if "description" in d:
		c.description = str(d.get("description") or "").strip()[:10000]
	if "people" in d:
		c.assignees = json.dumps(_people_ok(ctx, d.get("people")))
	if "labels" in d:
		ok = {x["id"] for x in _j(b.labels, [])}
		c.labels = json.dumps([x for x in dict.fromkeys(d.get("labels") or []) if x in ok])
	if "due" in d:
		c.due = getdate(d["due"]) if d.get("due") else None
	if "checklist" in d:
		c.checklist = json.dumps(pr.clean_checklist(d.get("checklist")))
	if "cover" in d:
		c.cover = str(d.get("cover") or "")[:9]
	if "done" in d:
		_set_done(c, b, bool(cint(d["done"])))
	c.save(ignore_permissions=True)
	added = [u for u in _j(c.assignees, []) if u not in before]
	_tell(ctx, c, added, _("{0} gave you a card on {1}").format(_names(ctx).get(ctx.user, ctx.user), b.title))
	return card(c.name)


@frappe.whitelist(methods=["GET"])
def card(name: str) -> dict:
	"""One card with its description, checklist and comments."""
	ctx = _ctx()
	c, b = _card(ctx, name)
	return {**_card_out(ctx, c, full=True), "board_title": b.title, "lists": _j(b.lists, []), "board_labels": _j(b.labels, [])}


@frappe.whitelist(methods=["POST"])
def move_card(name: str, list: str, before: str | None = None, after: str | None = None) -> dict:
	"""Move a card to a list, between two cards (their names; none = the end). Into the done list = done; out of it = open."""
	ctx = _ctx()
	c, b = _card(ctx, name)
	lists = [x["id"] for x in _j(b.lists, [])]
	if list not in lists:
		frappe.throw(_("That list isn't on the board any more."))
	pos = lambda n: frappe.db.get_value(CARD, {"name": n, "board": b.name}, "position") if n else None
	p_before, p_after = pos(before), pos(after)
	if before and after is None and p_before is not None:
		p_after = frappe.db.sql(f"select min(position) from `tab{CARD}` where board = %s and list_id = %s and position > %s and name != %s and archived = 0",
								(b.name, list, p_before, c.name))[0][0]
	c.list_id = list
	c.position = pr.between(p_before, p_after) if (before or after) else _end_position(b.name, list)
	if b.done_list:
		if list == b.done_list and not c.done:
			_set_done(c, b, True)
		elif list != b.done_list and c.done:
			_set_done(c, b, False)
	c.save(ignore_permissions=True)
	ps = frappe.get_all(CARD, filters={"board": b.name, "list_id": list, "archived": 0}, fields=["name", "position"], order_by="position asc")
	if pr.needs_renumber([x.position for x in ps]):
		for x, p in zip(ps, pr.renumber(len(ps))):
			frappe.db.set_value(CARD, x.name, "position", p, update_modified=False)
	return _card_out(ctx, frappe.get_doc(CARD, c.name))


@frappe.whitelist(methods=["POST"])
def delete_card(name: str, archive: int = 0) -> dict:
	"""Delete a card, or archive it (kept, out of the board)."""
	ctx = _ctx()
	c, _b = _card(ctx, name)
	if cint(archive):
		c.archived = 1
		c.save(ignore_permissions=True)
	else:
		frappe.delete_doc(CARD, c.name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def comment(name: str, text: str) -> dict:
	"""A comment on a card — the people on it are told."""
	ctx = _ctx()
	c, b = _card(ctx, name)
	text = str(text or "").strip()[:2000]
	if not text:
		frappe.throw(_("Write the comment."))
	cs = _j(c.comments, [])
	cs.append({"by": ctx.user, "at": str(now_datetime())[:19], "text": text})
	c.comments = json.dumps(cs[-300:])
	c.save(ignore_permissions=True)
	_tell(ctx, c, _j(c.assignees, []) + [c.created_by_user], _("{0} commented on a card").format(_names(ctx).get(ctx.user, ctx.user)))
	return card(c.name)


@frappe.whitelist(methods=["POST"])
def check(name: str, index: int, done: int = 1) -> dict:
	"""Tick (or untick) one checklist item."""
	ctx = _ctx()
	c, _b = _card(ctx, name)
	items = _j(c.checklist, [])
	i = cint(index)
	if not 0 <= i < len(items):
		frappe.throw(_("That item isn't on the checklist any more."))
	items[i]["done"] = bool(cint(done))
	c.checklist = json.dumps(items)
	c.save(ignore_permissions=True)
	return card(c.name)


@frappe.whitelist(methods=["POST"])
def cards_from(board: str, items=None, list: str | None = None, source: str = "", people=None, due: str | None = None) -> dict:
	"""Several cards at once (a note's action items, a meeting's to-dos) on a board's list."""
	_ctx()  # in the business, with Office Pulse
	items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
	people = frappe.parse_json(people) if isinstance(people, str) else (people or [])
	made = []
	for t in [str(x).strip() for x in items if str(x).strip()][:50]:
		made.append(save_card({"board": board, "list": list, "title": t, "source": source, "people": people, "due": due})["name"])
	if not made:
		frappe.throw(_("There's nothing to add."))
	return {"made": len(made), "board": board}


# ---- for My work ---------------------------------------------------------------------------------------------------------
def my_cards(ctx) -> list[dict]:
	"""Open cards given to this person on boards they still see."""
	rows = frappe.db.sql(f"""select c.name, c.board, c.title, c.due, c.list_id, b.title board_title, b.lists, b.visibility, b.members, b.created_by_user
		from `tab{CARD}` c join `tab{BOARD}` b on b.name = c.board
		where c.tenant = %s and c.done = 0 and c.archived = 0 and b.archived = 0 and c.assignees like %s""",
						 (ctx.tenant, f'%"{ctx.user}"%'), as_dict=True)
	out = []
	for r in rows:
		if not pr.board_visible(r, ctx.user, ctx.admin, _j(r.members, [])):
			continue
		lst = next((x["title"] for x in _j(r.lists, []) if x["id"] == r.list_id), "")
		out.append({"kind": "card", "name": r.name, "title": r.title, "due": r.due, "board": r.board, "where": f"{r.board_title} · {lst}"})
	return out
