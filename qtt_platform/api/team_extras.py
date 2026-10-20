"""
Team — the extras around the chats (PROJ-0014). The checks are api/team.py's: the business, the membership, who can
see which chat.

  search         messages in every chat you can see in this business: words (all of them), from someone, in a chat,
                 with files / photos / links
  activity       what needs you: @mentions, replies in your threads, reactions to your messages (newest first)
  activity_read  mark them read
  save           save a message for later, with an optional reminder (a phone notification at that time)
  saved          your saved messages; unsave / done
  ping           "I'm here" every minute while the app is open (online / away / offline for others)
  set_status     your status (emoji + words, until when) and Do not disturb (no phone notifications until then)
  typing         "… is typing" to the others in the chat (the app sends it at most every 3 seconds)
  make_task      a task from a message (assign to someone in the business, a due date) — a Frappe ToDo
  tasks          your tasks: assigned to you, or by you; task_done
  task_suggest   ✨ the task worked out from the message by AI (1 AI credit)
  catch_up       ✨ a summary of a chat's new messages by AI (1 AI credit): key points, decisions, asks, to-dos

The AI extras use the business's AI credits (the app's wallet with the most credits; QTT's own business doesn't
pay). Team itself is free.
"""

import json
import time
import uuid

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime, nowdate

from qtt_platform import team_rules as rules
from qtt_platform.api import team

PROFILE = "QTT Team Profile"
SAVED = "QTT Team Saved"
SEEN_KEY = "qtt_team_seen"


# ---- presence and status ---------------------------------------------------------------------------------------------
def touch(user: str) -> None:
	try:
		frappe.cache().hset(SEEN_KEY, user, time.time())
	except Exception:
		pass


def _on_leave_today(users: list[str]) -> set[str]:
	"""People on approved leave today (Office Pulse / HRMS), for the automatic "On leave" status."""
	if not users or not frappe.db.exists("DocType", "Leave Application"):
		return set()
	try:
		rows = frappe.db.sql("""select e.user_id from `tabLeave Application` l join `tabEmployee` e on e.name = l.employee
			where l.docstatus = 1 and l.status = 'Approved' and %s between l.from_date and l.to_date and e.user_id in %s""",
							 (nowdate(), tuple(users)))
		return {r[0] for r in rows}
	except Exception:
		return set()


def presence_of(users: list[str], tenant: str | None = None) -> dict[str, dict]:
	"""{user: {presence: online | away | offline, last_seen, status: {emoji, text, until} | None, dnd}}."""
	users = [u for u in users if u]
	if not users:
		return {}
	now, now_dt = time.time(), now_datetime()
	try:
		everyone = frappe.cache().hgetall(SEEN_KEY) or {}
		seen = [everyone.get(u) or everyone.get(u.encode()) for u in users]
	except Exception:
		seen = [None] * len(users)
	profiles = {p.name: p for p in frappe.get_all(PROFILE, filters={"name": ["in", users]},
												  fields=["name", "status_emoji", "status_text", "status_until", "dnd_until"])}
	leave = _on_leave_today(users)
	out = {}
	for user, ts in zip(users, seen):
		ts = float(ts) if ts else None
		p = profiles.get(user)
		status = None
		if p and (p.status_text or p.status_emoji) and rules.status_live(p.status_until, now_dt):
			status = {"emoji": p.status_emoji or "", "text": p.status_text or "", "until": str(p.status_until) if p.status_until else None}
		elif user in leave:
			status = {"emoji": "🌴", "text": "On leave today", "until": None, "auto": True}
		out[user] = {"presence": rules.presence(ts, now), "last_seen": ts,
					 "status": status, "dnd": bool(p and p.dnd_until and p.dnd_until > now_dt)}
	return out


def my_status(user: str) -> dict:
	return presence_of([user]).get(user, {})


def dnd_users(users: list[str]) -> set[str]:
	if not users:
		return set()
	return set(frappe.get_all(PROFILE, filters={"name": ["in", list(set(users))], "dnd_until": [">", now_datetime()]}, pluck="name"))


def _profile(user: str):
	if not frappe.db.exists(PROFILE, user):
		frappe.get_doc({"doctype": PROFILE, "user": user}).insert(ignore_permissions=True)
	return frappe.get_doc(PROFILE, user)


@frappe.whitelist(methods=["POST"])
def ping() -> dict:
	"""I'm here (the app calls it every minute while it's open)."""
	if frappe.session.user == "Guest":
		return {"ok": False}
	touch(frappe.session.user)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def set_status(emoji: str | None = None, text: str | None = None, until: str | None = None, dnd: str | None = None) -> dict:
	"""Your status, seen next to your name in Team: emoji + words (empty clears it), and for how long (30m, 1h, 2h, 4h,
	today, tomorrow, week, or empty = until you change it). dnd: Do not disturb for (30m … week), "off" to end it, or
	empty to leave it as it is."""
	team._ctx()
	user = frappe.session.user
	p = _profile(user)
	now = now_datetime()
	if emoji is not None or text is not None:
		p.status_emoji = str(emoji or "").strip()[:8]
		p.status_text = str(text or "").strip()[:100]
		p.status_until = rules.until_from(until, now) if (p.status_emoji or p.status_text) else None
	if dnd:
		p.dnd_until = None if dnd == "off" else (rules.until_from(dnd, now) or rules.until_from("today", now))
	p.save(ignore_permissions=True)
	return my_status(user)


@frappe.whitelist(methods=["POST"])
def typing(channel: str) -> dict:
	""""… is typing" to the others in the chat (not saved)."""
	ctx = team._ctx()
	team._channel(ctx, channel)
	touch(ctx.user)
	name = team._names(ctx).get(ctx.user, ctx.user)
	for user in frappe.get_all(team.MEM, filters={"channel_id": channel, "user_id": ["!=", ctx.user]}, pluck="user_id"):
		frappe.publish_realtime("qtt_team:typing", {"channel": channel, "user": ctx.user, "name": name}, user=user)
	return {"ok": True}


# ---- search ----------------------------------------------------------------------------------------------------------
def _visible_chats(ctx) -> dict[str, frappe._dict]:
	"""Every chat this person can read in this business: {id: chat} — channels (open or theirs), their direct messages,
	and the threads of those."""
	mine = set(frappe.get_all(team.MEM, filters={"user_id": ctx.user}, pluck="channel_id"))
	people = team._people(ctx.tenant)
	chats = {}
	for c in frappe.get_all(team.CH, filters={"workspace": ctx.ws, "is_thread": 0, "is_direct_message": 0},
							fields=["name", "channel_name", "type", "is_archived", "is_thread", "is_direct_message"]):
		if rules.can_see(c, c.name in mine):
			chats[c.name] = c
	for c in frappe.get_all(team.CH, filters={"is_direct_message": 1, "is_self_message": 0, "name": ["in", list(mine) or [""]]},
							fields=["name", "channel_name", "type", "is_direct_message"]):
		if rules.dm_peer(c.channel_name, ctx.user) in people:
			chats[c.name] = c
	if chats:
		for t in frappe.db.sql(f"""select c.name, m.channel_id parent from `tab{team.CH}` c join `tab{team.MSG}` m on m.name = c.name
			where c.is_thread = 1 and m.channel_id in %s""", (tuple(chats),), as_dict=True):
			chats[t.name] = frappe._dict(name=t.name, parent=t.parent, is_thread=1)
	return chats


def _chat_title(ctx, chats: dict, cid: str) -> str:
	c = chats.get(cid)
	if not c:
		return ""
	if c.get("is_thread"):
		return _chat_title(ctx, chats, c.parent)
	if c.is_direct_message:
		peer = rules.dm_peer(c.channel_name, ctx.user)
		return team._names(ctx).get(peer, peer)
	return f"#{c.channel_name}"


@frappe.whitelist(methods=["GET"])
def search(q: str = "", channel: str | None = None, person: str | None = None, has: str | None = None, start: int = 0) -> dict:
	"""Messages in the chats you can see in this business, newest first, 20 at a time. Every word must be in the
	message. channel: only that chat (and its threads); person: only their messages; has: file | photo | link | voice.
	{results: [{message, chat_id, chat, thread_of, snippet}], more}."""
	ctx = team._ctx()
	words = rules.search_words(q)
	if not words and not person and not has:
		return {"results": [], "more": False}
	chats = _visible_chats(ctx)
	ids = list(chats)
	if channel:
		ids = [i for i in ids if i == channel or chats[i].get("parent") == channel]
	if not ids:
		return {"results": [], "more": False}
	cond, args = ["channel_id in %(ids)s", "message_type != 'System'"], {"ids": tuple(ids), "start": cint(start)}
	for i, w in enumerate(words):
		cond.append(f"(content like %(w{i})s or file like %(w{i})s)")
		args[f"w{i}"] = f"%{w}%"
	if person:
		cond.append("owner = %(person)s")
		args["person"] = person
	match has:
		case "photo":
			cond.append("message_type = 'Image'")
		case "file":
			cond.append("message_type = 'File' and file not like '%%/voice-%%'")
		case "voice":
			cond.append("message_type = 'File' and file like '%%/voice-%%'")
		case "link":
			cond.append("links is not null and links != ''")
	rows = frappe.db.sql(f"""select {", ".join(team.MSG_FIELDS)} from `tab{team.MSG}` where {" and ".join(cond)}
		order by creation desc limit 21 offset %(start)s""", args, as_dict=True)
	more = len(rows) > 20
	rows = rows[:20]
	out = team._out_many(ctx, rows)
	return {"results": [{"message": o, "chat_id": chats[r.channel_id].get("parent") or r.channel_id, "chat": _chat_title(ctx, chats, r.channel_id),
						 "thread_of": r.channel_id if chats[r.channel_id].get("is_thread") else None,
						 "snippet": rules.snippet(o["text"], words) if words else rules.preview(r.message_type, r.content, r.file)}
						for r, o in zip(rows, out)], "more": more}


# ---- activity ----------------------------------------------------------------------------------------------------------
def _activity_rows(ctx, since=None, limit: int = 60) -> list[dict]:
	"""@mentions of you, replies in threads you're in, reactions to your messages — in chats you can see, last 30 days."""
	chats = _visible_chats(ctx)
	if not chats:
		return []
	since = since or frappe.utils.add_days(now_datetime(), -30)
	ids = tuple(chats)
	items = []
	for r in frappe.db.sql(f"""select m.name, m.channel_id, m.owner, m.creation from `tab{team.MSG}` m
		join `tabRaven Mention` x on x.parent = m.name and x.parenttype = %s
		where x.user = %s and m.owner != %s and m.channel_id in %s and m.creation > %s order by m.creation desc limit %s""",
						   (team.MSG, ctx.user, ctx.user, ids, since, limit), as_dict=True):
		items.append({"kind": "mention", "message": r.name, "chat_id": r.channel_id, "by": r.owner, "at": r.creation})
	threads = [i for i in ids if chats[i].get("is_thread")]
	if threads:
		mine = set(frappe.get_all(team.MEM, filters={"user_id": ctx.user, "channel_id": ["in", threads]}, pluck="channel_id"))
		if mine:
			for r in frappe.db.sql(f"""select name, channel_id, owner, creation from `tab{team.MSG}` where channel_id in %s
				and owner != %s and message_type != 'System' and creation > %s order by creation desc limit %s""",
								   (tuple(mine), ctx.user, since, limit), as_dict=True):
				items.append({"kind": "reply", "message": r.name, "chat_id": r.channel_id, "by": r.owner, "at": r.creation})
	for r in frappe.db.sql(f"""select x.message, x.channel_id, x.owner, x.reaction, x.creation from `tab{team.REACTION}` x
		join `tab{team.MSG}` m on m.name = x.message where m.owner = %s and x.owner != %s and x.channel_id in %s and x.creation > %s
		order by x.creation desc limit %s""", (ctx.user, ctx.user, ids, since, limit), as_dict=True):
		items.append({"kind": "reaction", "message": r.message, "chat_id": r.channel_id, "by": r.owner, "at": r.creation, "emoji": r.reaction})
	items.sort(key=lambda i: i["at"], reverse=True)
	for i in items:
		i["chat"] = _chat_title(ctx, chats, i["chat_id"])
		c = chats.get(i["chat_id"])
		i["thread_of"] = i["chat_id"] if c and c.get("is_thread") else None
		i["open_chat"] = c.get("parent") if c and c.get("is_thread") else i["chat_id"]
	return items[:limit]


def activity_unread(ctx) -> int:
	seen = frappe.db.get_value(PROFILE, ctx.user, "activity_seen_at")
	try:
		return len(_activity_rows(ctx, since=seen, limit=99))
	except Exception:
		return 0


@frappe.whitelist(methods=["GET"])
def activity() -> dict:
	"""What needs you, newest first: @mentions, replies in your threads, reactions to your messages (last 30 days).
	{items: [{kind, message (as in a chat), by, chat, open_chat, thread_of, emoji, at, new}]}"""
	ctx = team._ctx()
	seen = frappe.db.get_value(PROFILE, ctx.user, "activity_seen_at")
	items = _activity_rows(ctx)
	msgs = {}
	names = list({i["message"] for i in items})
	if names:
		rows = frappe.get_all(team.MSG, filters={"name": ["in", names]}, fields=team.MSG_FIELDS)
		msgs = {o["id"]: o for o in team._out_many(ctx, rows)}
	people = team._names(ctx)
	return {"items": [{**i, "at": str(i["at"]), "message": msgs.get(i["message"]), "by_name": people.get(i["by"], i["by"]),
					   "new": not seen or get_datetime(i["at"]) > get_datetime(seen)} for i in items if i["message"] in msgs]}


@frappe.whitelist(methods=["POST"])
def activity_read() -> dict:
	"""Mark your Activity read (the count on Activity goes back to none)."""
	team._ctx()
	p = _profile(frappe.session.user)
	p.activity_seen_at = now_datetime()
	p.save(ignore_permissions=True)
	return {"ok": True}


# ---- saved for later -----------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def save(message: str, remind: str | None = None) -> dict:
	"""Save a message for later. remind: 20m, 1h, 3h, tonight, tomorrow, next_week (a phone notification then), or
	empty. Saving it again changes the reminder."""
	ctx = team._ctx()
	m, _c = team._message(ctx, message)
	name = frappe.db.get_value(SAVED, {"user": ctx.user, "message": message, "done": 0})
	doc = frappe.get_doc(SAVED, name) if name else frappe.get_doc({"doctype": SAVED, "user": ctx.user, "tenant": ctx.tenant, "message": message,
																	 "channel": m.channel_id})
	doc.remind_at = rules.remind_at(remind, now_datetime()) if remind else None
	doc.reminded = 0
	doc.save(ignore_permissions=True)
	return {"saved": True, "remind_at": str(doc.remind_at) if doc.remind_at else None}


@frappe.whitelist(methods=["POST"])
def unsave(message: str, done: int = 0) -> dict:
	"""Take a message out of Saved (done = mark it done instead, kept in Done)."""
	ctx = team._ctx()
	for name in frappe.get_all(SAVED, filters={"user": ctx.user, "message": message, "done": 0}, pluck="name"):
		if cint(done):
			frappe.db.set_value(SAVED, name, "done", 1)
		else:
			frappe.delete_doc(SAVED, name, ignore_permissions=True)
	return {"saved": False}


def saved_due(ctx) -> int:
	return frappe.db.count(SAVED, {"user": ctx.user, "tenant": ctx.tenant, "done": 0, "remind_at": ["<=", now_datetime()]})


@frappe.whitelist(methods=["GET"])
def saved(done: int = 0) -> dict:
	"""Your saved messages in this business (reminders due first). {items: [{message, chat, open_chat, thread_of, remind_at, due}]}"""
	ctx = team._ctx()
	rows = frappe.get_all(SAVED, filters={"user": ctx.user, "tenant": ctx.tenant, "done": cint(done)},
						  fields=["name", "message", "channel", "remind_at", "creation"], order_by="creation desc", limit=200)
	chats = _visible_chats(ctx)
	msgs = frappe.get_all(team.MSG, filters={"name": ["in", [r.message for r in rows] or [""]]}, fields=team.MSG_FIELDS)
	outs = {o["id"]: (o, m.channel_id) for o, m in zip(team._out_many(ctx, msgs), msgs)}
	now = now_datetime()
	items = []
	for r in rows:
		if r.message not in outs or outs[r.message][1] not in chats:
			continue
		o, cid = outs[r.message]
		c = chats[cid]
		items.append({"message": o, "chat": _chat_title(ctx, chats, cid), "open_chat": c.get("parent") or cid,
					  "thread_of": cid if c.get("is_thread") else None, "remind_at": str(r.remind_at) if r.remind_at else None,
					  "due": bool(r.remind_at and r.remind_at <= now), "saved_at": str(r.creation)})
	items.sort(key=lambda i: (not i["due"], i["remind_at"] or "9999", ), reverse=False)
	return {"items": items}


def remind_due() -> None:
	"""Every 5 minutes: phone notifications for saved messages whose reminder time has come."""
	for r in frappe.get_all(SAVED, filters={"done": 0, "reminded": 0, "remind_at": ["<=", now_datetime()]},
							fields=["name", "user", "tenant", "message", "channel"], limit=500):
		try:
			m = frappe.db.get_value(team.MSG, r.message, ["message_type", "content", "text", "file", "channel_id"], as_dict=True)
			frappe.db.set_value(SAVED, r.name, "reminded", 1, update_modified=False)
			if not m:
				continue
			from qtt_platform.team_events import _business_channel, send_push

			c = _business_channel(m.channel_id)
			send_push([r.user], "⏰ Reminder", rules.preview(m.message_type, m.text or m.content, m.file),
					  {"kind": "team", "tenant": r.tenant, "channel": c.parent.name if c and c.get("parent") else m.channel_id,
					   "message": r.message, "thread_of": m.channel_id if c and c.get("parent") else ""})
		except Exception:
			frappe.log_error(title="Team chat: reminder failed")
	frappe.db.commit()


# ---- tasks ---------------------------------------------------------------------------------------------------------------
def _task_out(t, ctx, names) -> dict:
	return {"id": t.name, "title": t.description, "status": t.status, "due": str(t.date) if t.date else None,
			"assigned_to": t.allocated_to, "assigned_to_name": names.get(t.allocated_to, t.allocated_to),
			"by": t.assigned_by, "by_name": names.get(t.assigned_by, t.assigned_by), "message": t.reference_name,
			"overdue": bool(t.date and t.status == "Open" and getdate(t.date) < getdate(nowdate()))}


@frappe.whitelist(methods=["POST"])
def make_task(message: str, title: str, assign_to: str | None = None, due: str | None = None) -> dict:
	"""A task from a message: what to do, who does it (someone in the business; you by default), by when."""
	ctx = team._ctx()
	m, _c = team._message(ctx, message)
	people = team._people(ctx.tenant)
	assign_to = assign_to or ctx.user
	if assign_to not in people:
		frappe.throw(_("Choose someone in your business."))
	if not str(title or "").strip():
		frappe.throw(_("Say what needs doing."))
	t = frappe.get_doc({"doctype": "ToDo", "description": str(title).strip()[:500], "allocated_to": assign_to, "assigned_by": ctx.user,
						"date": getdate(due) if due else None, "status": "Open", "priority": "Medium",
						"reference_type": team.MSG, "reference_name": message}).insert(ignore_permissions=True)
	if assign_to != ctx.user:
		from qtt_platform.team_events import send_push

		send_push([assign_to], f"✅ New task from {team._names(ctx).get(ctx.user, ctx.user)}", t.description[:140],
				  {"kind": "team_task", "tenant": ctx.tenant, "task": t.name, "channel": m.channel_id})
	team.changed(m.channel_id, message)
	return _task_out(t, ctx, team._names(ctx))


@frappe.whitelist(methods=["GET"])
def tasks(show: str = "mine") -> dict:
	"""Tasks made from Team messages in this business. show: mine (assigned to you), given (you gave others), done.
	Open ones by due date first."""
	ctx = team._ctx()
	filters = {"reference_type": team.MSG}
	if show == "given":
		filters.update({"assigned_by": ctx.user, "allocated_to": ["!=", ctx.user], "status": "Open"})
	elif show == "done":
		filters.update({"allocated_to": ctx.user, "status": "Closed"})
	else:
		filters.update({"allocated_to": ctx.user, "status": "Open"})
	rows = frappe.get_all("ToDo", filters=filters, fields=["name", "description", "status", "date", "allocated_to", "assigned_by", "reference_name"],
						  order_by="creation desc", limit=200)
	rows.sort(key=lambda t: (t.date is None, t.date or getdate(nowdate())))
	chats = _visible_chats(ctx)
	msg_chat = {r.name: r.channel_id for r in frappe.get_all(team.MSG, filters={"name": ["in", [r.reference_name for r in rows] or [""]]},
															 fields=["name", "channel_id"])}
	names = team._names(ctx)
	out = []
	for t in rows:
		cid = msg_chat.get(t.reference_name)
		if cid not in chats:
			continue  # another business's, or the message is gone
		c = chats[cid]
		out.append({**_task_out(t, ctx, names), "chat": _chat_title(ctx, chats, cid), "open_chat": c.get("parent") or cid,
					"thread_of": cid if c.get("is_thread") else None})
	return {"tasks": out}


@frappe.whitelist(methods=["POST"])
def task_done(task: str, done: int = 1) -> dict:
	"""Mark a task done (or open again) — the person it's for, or who gave it."""
	ctx = team._ctx()
	t = frappe.get_doc("ToDo", task)
	if t.reference_type != team.MSG or ctx.user not in (t.allocated_to, t.assigned_by):
		frappe.throw(_("That isn't one of your tasks."), frappe.PermissionError)
	team._message(ctx, t.reference_name)
	t.status = "Closed" if cint(done) else "Open"
	t.save(ignore_permissions=True)
	return _task_out(t, ctx, team._names(ctx))


# ---- AI extras (AI credits) --------------------------------------------------------------------------------------------
def _wallet(tenant: str) -> str | None:
	"""The business's AI wallet with the most credits (any app); None when it has none."""
	row = frappe.get_all("QTT Tenant Product Wallet", filters={"tenant": tenant, "balance": [">", 0]}, fields=["product", "balance"],
						 order_by="balance desc", limit=1)
	return row[0].product if row else None


def ai_info(tenant: str) -> dict:
	from qtt_platform.house import is_house

	if is_house(tenant):
		return {"available": True, "credits": None, "costs": rules.CREDITS}
	try:
		credits = float(frappe.db.sql("select coalesce(sum(balance), 0) from `tabQTT Tenant Product Wallet` where tenant = %s", tenant)[0][0])
	except Exception:
		credits = 0
	return {"available": credits >= 1, "credits": credits, "costs": rules.CREDITS}


def _paid(tenant: str, feature: str, run):
	"""One AI job on AI credits: taken first, given back if it fails or says nothing; usage recorded."""
	from qtt_platform.ai.core.response import AiUsage
	from qtt_platform.ai.services import credit_service, usage_service
	from qtt_platform.house import is_house

	cost = rules.CREDITS[feature]
	paying = not is_house(tenant)
	product = _wallet(tenant) if paying else "QTT_STUDIO"
	ref = f"team:{feature}:{uuid.uuid4()}"
	if paying and (not product or not credit_service.deduct_credits(tenant, product, cost, reference=ref).get("ok")):
		frappe.throw(_("You're out of AI credits — more come with your apps' plans, or buy more in Business › Plans and billing."))
	start = time.monotonic()
	result = None
	try:
		result = run()
	except Exception:
		frappe.log_error(title=f"Team chat: AI {feature} failed")
	ok = bool(result)
	if not ok and paying:
		credit_service.refund_credits(tenant, product, cost, reference=ref)
	try:
		usage_service.record_usage(tenant=tenant, product=product or "QTT_STUDIO", user=frappe.session.user, feature=f"team_{feature}",
								   provider="assistant", model="assistant", usage=AiUsage(0, 0, 0), credits_used=cost if ok and paying else 0,
								   provider_cost=0, status="success" if ok else "error", duration_ms=int((time.monotonic() - start) * 1000))
	except Exception:
		frappe.log_error(title="Team chat: AI usage not recorded")
	if not ok:
		frappe.throw(_("That didn't work just now — no credits were used. Please try again in a minute."))
	return result


def _complete(messages: list[dict], max_tokens: int = 700) -> str | None:
	from qtt_platform.api.assistant import complete_json

	for json_mode in (True, False):
		text = complete_json(messages, max_tokens=max_tokens, json_mode=json_mode, temperature=0.2, timeout=45)
		if (text or "").strip():
			return text
	return None


@frappe.whitelist(methods=["POST"])
def catch_up(channel: str, language: str = "en") -> dict:
	"""✨ Catch me up: the chat's new messages for you (or the latest ones when nothing is new) summed up by AI —
	key points, decisions, what's asked of you, to-dos. 1 AI credit. {summary, decisions, asks, todos, count, credits}."""
	ctx = team._ctx()
	c = team._channel(ctx, channel)
	last = frappe.db.get_value(team.MEM, {"channel_id": channel, "user_id": ctx.user}, "last_visit")
	filters = {"channel_id": channel, "message_type": ["!=", "System"]}
	rows = frappe.get_all(team.MSG, filters={**filters, "creation": [">", last]}, fields=["owner", "content", "message_type", "file", "creation"],
						  order_by="creation desc", limit=rules.CATCH_UP_MAX) if last else []
	if len(rows) < 3:
		rows = frappe.get_all(team.MSG, filters=filters, fields=["owner", "content", "message_type", "file", "creation"],
							  order_by="creation desc", limit=60)
	if not rows:
		frappe.throw(_("There's nothing to catch up on here yet."))
	names = team._names(ctx)
	lines = [f"{names.get(r.owner, r.owner)}: {rules.preview(r.message_type, r.content, r.file)[:500]}" for r in reversed(rows)]
	title = team._chat_info(ctx, c)["name"]
	got = _paid(ctx.tenant, "catch_up", lambda: rules.parse_catch_up(_complete(rules.catch_up_prompt(title, lines, language))))
	return {**got, "count": len(rows), "credits": ai_info(ctx.tenant)["credits"]}


@frappe.whitelist(methods=["POST"])
def task_suggest(message: str) -> dict:
	"""✨ The task in a message, worked out by AI: {title, assign_to, due}. 1 AI credit. Check it before making it."""
	ctx = team._ctx()
	m, _c = team._message(ctx, message)
	names = team._names(ctx)
	text = rules.plain(rules.html_to_text(m.text or m.content or ""))
	if not text.strip():
		frappe.throw(_("This message has no words to make a task from."))
	return _paid(ctx.tenant, "task", lambda: rules.parse_task(
		_complete(rules.task_prompt(text[:2000], names.get(m.owner, m.owner), list(names.values()), nowdate()), max_tokens=200), names))
