"""
Team — the business's own team chat, free in QTT OS (PROJ-0013, PROJ-0014). Built on Raven (installed on the site): each
business gets a private Raven workspace ("qtt-<tenant>") with #general for everyone, channels its members make and
direct messages between its members. Every call checks the business and the person's membership here — customers
never get Raven's role (it would open Desk), so Raven's own API isn't used; its records and behaviour are (last
message, threads, reactions, mentions, pins, system messages).

  home           channels (unread, the last message), direct messages, threads with new replies, the people (with
                 presence and status), my status, unread activity, whether AI extras can be used
  messages       a chat's messages, newest page first (before= for older); marks it read; who has seen what
  send           a message (text with *bold* _italic_ ~strike~ `code`, links, @mentions, @everyone); reply_to for a
                 quoted reply, thread_of to reply in a message's thread
  send_file      a photo, file or voice note (multipart `file`, up to 25 MB; thread_of as above)
  edit_message   change your own message
  delete_message your own message
  react          add / take back a reaction (any emoji)
  pin            pin / unpin a message in the chat (everyone in it sees the pins)
  thread         a message's thread: the message, its replies, who's in it; marks it read
  threads        threads you're in, newest reply first, with new replies
  file           a photo / file of a message — only for people in that chat
  file_link      a 10-minute link to a message's file, to open it in the browser
  start_dm       a direct message with someone in the business
  new_channel    a channel: open to the whole business, or private with the people chosen
  channel        a channel's details, members and pinned messages
  update_channel rename / describe a channel (people in it)
  add_members    add people from the business to a channel
  leave          leave a channel (not #general)
  mute           phone notifications for a chat: all, or only @mentions

Search, saved for later, presence / status / typing, tasks and the AI extras: api/team_extras.py.
Who: everyone in the business (the business's own users), nothing to buy.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from qtt_platform import team_rules as rules
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership

CH = "Raven Channel"
MEM = "Raven Channel Member"
MSG = "Raven Message"
WS = "Raven Workspace"
WSM = "Raven Workspace Member"
RU = "Raven User"
REACTION = "Raven Message Reaction"
GOVERNANCE = ("Tenant Owner", "Tenant Admin")
MSG_FIELDS = ["name", "channel_id", "owner", "creation", "text", "content", "message_type", "file", "is_reply", "linked_message",
			  "replied_message_details", "is_edited", "is_thread", "message_reactions"]


# ---- who and where ---------------------------------------------------------------------------------------------------
def _ctx() -> frappe._dict:
	if "raven" not in frappe.get_installed_apps():
		frappe.throw(_("Team chat isn't set up on this server yet."))
	tenant = resolve_active_tenant()
	m = require_tenant_membership(tenant)
	user = frappe.session.user
	_raven_user(user)
	ws = _workspace(tenant)
	return frappe._dict(tenant=tenant, user=user, role=m.tenant_role, ws=ws, admin=m.tenant_role in GOVERNANCE)


def _people(tenant: str) -> dict[str, dict]:
	"""Everyone active in the business: {user: {user, name, image, role}}."""
	cache = getattr(frappe.local, "qtt_team_people", None)
	if cache is None:
		cache = frappe.local.qtt_team_people = {}
	if tenant in cache:
		return cache[tenant]
	rows = frappe.get_all("QTT Tenant Membership", filters={"tenant": tenant, "status": "active"}, fields=["user", "tenant_role"])
	users = [r.user for r in rows]
	info = {u.name: u for u in frappe.get_all("User", filters={"name": ["in", users or [""]]}, fields=["name", "full_name", "user_image", "enabled"])}
	cache[tenant] = {r.user: {"user": r.user, "name": (info.get(r.user) or {}).get("full_name") or r.user,
							  "image": (info.get(r.user) or {}).get("user_image"), "role": r.tenant_role}
					 for r in rows if (info.get(r.user) or {}).get("enabled", 1)}
	return cache[tenant]


def _names(ctx) -> dict[str, str]:
	return {u: p["name"] for u, p in _people(ctx.tenant).items()}


def _raven_user(user: str) -> None:
	"""The person's Raven User (kept switched on — Raven switches off users without its role on every profile save;
	QTT decides who belongs, from the business membership)."""
	if frappe.db.exists(RU, user):
		if not frappe.db.get_value(RU, user, "enabled"):
			frappe.db.set_value(RU, user, "enabled", 1, update_modified=False)
		return
	full, image = frappe.db.get_value("User", user, ["full_name", "user_image"]) or (user, None)
	full = full or user
	# the photo's link as it is: Raven would otherwise copy the file, and fails when it's gone from disk
	frappe.get_doc({"doctype": RU, "user": user, "type": "User", "full_name": full, "first_name": full.split(" ")[0], "enabled": 1,
					"user_image": image}).insert(ignore_permissions=True)


def _workspace(tenant: str) -> str:
	"""The business's private workspace and #general, made the first time; its members follow the business."""
	name = rules.workspace_name(tenant)
	if not frappe.db.exists(WS, name):
		frappe.get_doc({"doctype": WS, "workspace_name": name, "type": "Private", "can_only_join_via_invite": 1,
						"description": frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or tenant,
						"only_admins_can_create_channels": 0}).insert(ignore_permissions=True)
	sync(tenant)
	return name


def sync(tenant: str, exclude: str | None = None) -> None:
	"""Workspace members = the business's active members (owners and admins as workspace admins); everyone in #general.
	Quiet: no "joined" messages for this."""
	name = rules.workspace_name(tenant)
	if not frappe.db.exists(WS, name):
		return
	(getattr(frappe.local, "qtt_team_people", None) or {}).pop(tenant, None)
	people = dict(_people(tenant))
	people.pop(exclude, None)  # a membership being deleted
	for user in people:
		_raven_user(user)
	have = {r.user: r.name for r in frappe.get_all(WSM, filters={"workspace": name}, fields=["name", "user"])}
	for user, p in people.items():
		if user not in have:
			frappe.get_doc({"doctype": WSM, "workspace": name, "user": user, "is_admin": 1 if p["role"] in GOVERNANCE else 0}).insert(ignore_permissions=True)
	for user, row in have.items():
		if user not in people:
			try:
				frappe.delete_doc(WSM, row, ignore_permissions=True)  # also takes them out of the workspace's channels
			except frappe.ValidationError:
				frappe.clear_messages()  # Raven keeps the last admin; they're out of the business anyway
	general = rules.channel_id(name, rules.GENERAL)
	if not frappe.db.exists(CH, general):
		ch = frappe.get_doc({"doctype": CH, "channel_name": rules.GENERAL, "channel_description": _("Everyone in the business"),
							 "type": "Public", "workspace": name})
		ch.flags.do_not_add_member = True
		ch.insert(ignore_permissions=True)
	_quiet_join(general, [u for u in people])


def _quiet_join(channel: str, users: list[str]) -> None:
	"""Put people in a chat without Raven's "X joined" message (#general, threads)."""
	inside = set(frappe.get_all(MEM, filters={"channel_id": channel}, pluck="user_id"))
	added = [u for u in dict.fromkeys(users) if u and u not in inside]
	for user in added:
		frappe.get_doc({"doctype": MEM, "channel_id": channel, "user_id": user, "is_admin": 0, "last_visit": now_datetime(),
						"allow_notifications": 1}).db_insert()
	if added:
		from raven.utils import delete_channel_members_cache

		delete_channel_members_cache(channel)


def _channel(ctx, channel: str, *, need_member: bool = False) -> frappe._dict:
	"""The chat, if this person may see it in this business: a channel of its workspace they're in or that's open to
	the business, a direct message with someone in it, or a thread of one of those (anyone who can see the message can
	read and reply)."""
	c = frappe.db.get_value(CH, channel, ["name", "channel_name", "channel_description", "type", "workspace", "is_direct_message",
										  "is_self_message", "is_archived", "is_thread", "owner"], as_dict=True)
	if not c:
		frappe.throw(_("That chat isn't here any more."), frappe.DoesNotExistError)
	member = frappe.db.exists(MEM, {"channel_id": channel, "user_id": ctx.user})
	if c.is_thread:
		parent = frappe.db.get_value(MSG, c.name, "channel_id")
		if not parent:
			frappe.throw(_("That chat isn't here any more."), frappe.DoesNotExistError)
		c.parent = _channel(ctx, parent)
		if need_member and not member:
			_quiet_join(channel, [ctx.user])
	elif c.is_direct_message:
		peer = rules.dm_peer(c.channel_name, ctx.user)
		if not member or not peer or peer not in _people(ctx.tenant):
			frappe.throw(_("That chat isn't in this business."), frappe.PermissionError)
	else:
		if c.workspace != ctx.ws or not rules.can_see(c, bool(member)):
			frappe.throw(_("That chat isn't in this business."), frappe.PermissionError)
		if need_member and not member:
			if c.type in ("Public", "Open"):
				_join(channel, ctx.user)  # writing in an open channel joins it
			else:
				frappe.throw(_("You're not in this channel."), frappe.PermissionError)
	c.member = bool(member) or need_member
	return c


def _message(ctx, message: str) -> tuple[frappe._dict, frappe._dict]:
	"""A message and its chat, if this person may see them."""
	m = frappe.db.get_value(MSG, message, MSG_FIELDS, as_dict=True)
	if not m:
		frappe.throw(_("That message isn't here any more."), frappe.DoesNotExistError)
	return m, _channel(ctx, m.channel_id)


def _join(channel: str, user: str) -> None:
	frappe.get_doc({"doctype": MEM, "channel_id": channel, "user_id": user}).insert(ignore_permissions=True)


def _unread(channel: str, user: str) -> int:
	last = frappe.db.get_value(MEM, {"channel_id": channel, "user_id": user}, "last_visit")
	return frappe.db.count(MSG, {"channel_id": channel, "creation": [">", last or "2000-01-01"], "message_type": ["!=", "System"],
								 "owner": ["!=", user]})


def _mentions_me(channel: str, user: str) -> int:
	"""New messages in the chat that @mention this person (or @everyone)."""
	last = frappe.db.get_value(MEM, {"channel_id": channel, "user_id": user}, "last_visit") or "2000-01-01"
	direct = frappe.db.sql(f"""select count(*) from `tab{MSG}` m join `tabRaven Mention` r on r.parent = m.name and r.parenttype = %s
		where m.channel_id = %s and m.creation > %s and r.user = %s""", (MSG, channel, last, user))[0][0]
	everyone = frappe.db.sql(f"""select count(*) from `tab{MSG}` where channel_id = %s and creation > %s and owner != %s
		and content like %s""", (channel, last, user, f"%@{rules.EVERYONE}%"))[0][0]
	return int(direct or 0) + int(everyone or 0)


def _last(row) -> dict | None:
	d = row.last_message_details
	try:
		d = json.loads(d) if isinstance(d, str) else (d or {})
	except ValueError:
		d = {}
	if not row.last_message_timestamp:
		return None
	return {"text": rules.preview(d.get("message_type"), d.get("content"), d.get("file")), "owner": d.get("owner"),
			"at": str(row.last_message_timestamp)}


def changed(channel: str, message: str, kind: str = "updated", extra: dict | None = None) -> None:
	"""Tell everyone in the chat (and, for a thread, in the chat it belongs to) that a message changed: the app
	refreshes it. kind: new | updated | deleted | read."""
	from qtt_platform.team_events import publish

	publish(channel, {"message": message, "kind": kind, **(extra or {})})


# ---- what a message looks like to the app ----------------------------------------------------------------------------
def _threads_of(ids: list[str]) -> dict[str, dict]:
	"""Thread summaries of root messages: {id: {count, last_at, people}}."""
	if not ids:
		return {}
	rows = frappe.db.sql(f"""select channel_id, count(*) n, max(creation) last_at from `tab{MSG}`
		where channel_id in %s and message_type != 'System' group by channel_id""", (tuple(ids),), as_dict=True)
	people = {}
	for r in frappe.db.sql(f"""select channel_id, owner from `tab{MSG}` where channel_id in %s and message_type != 'System'
		group by channel_id, owner order by max(creation) desc""", (tuple(ids),), as_dict=True):
		people.setdefault(r.channel_id, []).append(r.owner)
	return {r.channel_id: {"count": r.n, "last_at": str(r.last_at), "people": people.get(r.channel_id, [])[:4]} for r in rows}


def _pins(channel: str) -> set[str]:
	return set(frappe.get_all("Raven Pinned Messages", filters={"parent": channel, "parenttype": CH}, pluck="message_id"))


def _out_many(ctx, rows: list, *, pins: set | None = None) -> list[dict]:
	names = _names(ctx)
	threads = _threads_of([m.name for m in rows if m.is_thread])
	mentions = {}
	ids = [m.name for m in rows]
	if ids:
		for r in frappe.get_all("Raven Mention", filters={"parent": ["in", ids], "parenttype": MSG}, fields=["parent", "user"]):
			mentions.setdefault(r.parent, []).append(r.user)
	return [_out(m, names, ctx.user, thread=threads.get(m.name), mentions=mentions.get(m.name, []), pinned=m.name in (pins or ()))
			for m in rows]


def _out(m, names: dict, me: str, *, thread: dict | None = None, mentions: list | None = None, pinned: bool = False) -> dict:
	reply = m.replied_message_details
	try:
		reply = json.loads(reply) if isinstance(reply, str) else reply
	except ValueError:
		reply = None
	seconds = rules.voice(m.file)
	text = rules.html_to_text(m.text or m.content or "")
	return {"id": m.name, "type": m.message_type, "text": text, "owner": m.owner, "name": names.get(m.owner, m.owner),
			"at": str(m.creation), "mine": m.owner == me, "edited": bool(m.is_edited),
			"file": f"/api/method/qtt_platform.api.team.file?message={m.name}" if m.file else None,
			"file_name": (m.file or "").rsplit("/", 1)[-1] or None, "voice": seconds,
			"reactions": rules.reactions(m.message_reactions, me, names),
			"mentions": [{"user": u, "name": names.get(u, u)} for u in (mentions or [])],
			"mentions_me": me in (mentions or []) or (m.owner != me and rules.mentions_everyone(text)),
			"pinned": pinned,
			"thread": {**thread, "people": [{"user": u, "name": names.get(u, u)} for u in thread["people"]]} if thread else None,
			"reply": {"id": m.linked_message, "text": rules.preview((reply or {}).get("message_type"), (reply or {}).get("content") or (reply or {}).get("text"),
															  (reply or {}).get("file")),
					  "name": names.get((reply or {}).get("owner"), (reply or {}).get("owner"))} if m.is_reply and reply else None}


def _seen(channel: str, ctx) -> dict[str, str]:
	"""Up to when each other person in the chat has read it: {user: last_visit}."""
	people = _people(ctx.tenant)
	return {r.user_id: str(r.last_visit) for r in frappe.get_all(MEM, filters={"channel_id": channel}, fields=["user_id", "last_visit"])
			if r.user_id != ctx.user and r.user_id in people and r.last_visit}


def _read(channel: str, ctx) -> None:
	"""Mark the chat read for this person and tell the others (their "seen" ticks)."""
	if frappe.db.exists(MEM, {"channel_id": channel, "user_id": ctx.user}):
		now = now_datetime()
		frappe.db.set_value(MEM, {"channel_id": channel, "user_id": ctx.user}, "last_visit", now, update_modified=False)
		changed(channel, "", "read", {"user": ctx.user, "at": str(now)})


# ---- endpoints -------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def home() -> dict:
	"""The business's chats for this person: channels (open to the business, or private ones they're in), direct
	messages with people in the business, each with unread, @mentions and the last message; threads with new replies;
	the people with presence and status; my status; unread activity; whether the AI extras can be used."""
	from qtt_platform.api import team_extras as extras

	ctx = _ctx()
	people = _people(ctx.tenant)
	mine = {r.channel_id: r for r in frappe.get_all(MEM, filters={"user_id": ctx.user}, fields=["channel_id", "allow_notifications"])}
	fields = ["name", "channel_name", "channel_description", "type", "is_archived", "is_thread", "last_message_timestamp", "last_message_details"]
	channels = []
	for c in frappe.get_all(CH, filters={"workspace": ctx.ws, "is_direct_message": 0, "is_thread": 0, "is_archived": 0}, fields=fields):
		member = c.name in mine
		if not rules.can_see(c, member):
			continue
		channels.append({"id": c.name, "name": c.channel_name, "about": c.channel_description or "", "private": c.type == "Private",
						 "member": member, "general": c.channel_name == rules.GENERAL, "unread": _unread(c.name, ctx.user) if member else 0,
						 "mentions": _mentions_me(c.name, ctx.user) if member else 0,
						 "muted": member and not mine[c.name].allow_notifications, "last": _last(c)})
	channels.sort(key=lambda c: (not c["general"], c["name"]))
	live = extras.presence_of(list(people), ctx.tenant)
	dms = []
	for c in frappe.get_all(CH, filters={"is_direct_message": 1, "is_self_message": 0, "name": ["in", list(mine) or [""]]},
							fields=["name", "channel_name", "last_message_timestamp", "last_message_details"]):
		peer = rules.dm_peer(c.channel_name, ctx.user)
		if peer in people:
			dms.append({"id": c.name, "peer": {**people[peer], **live.get(peer, {})}, "unread": _unread(c.name, ctx.user),
						"muted": not mine[c.name].allow_notifications, "last": _last(c)})
	dms.sort(key=lambda d: (d["last"] or {}).get("at") or "", reverse=True)
	extras.touch(ctx.user)
	return {"channels": channels, "dms": dms,
			"people": [{**p, **live.get(u, {})} for u, p in people.items() if u != ctx.user],
			"me": ctx.user, "my_status": extras.my_status(ctx.user), "can_manage": ctx.admin,
			"threads_unread": sum(t["unread"] for t in _my_threads(ctx, limit=50)),
			"activity_unread": extras.activity_unread(ctx), "saved_due": extras.saved_due(ctx),
			"ai": extras.ai_info(ctx.tenant), "quick_reactions": rules.QUICK_REACTIONS}


@frappe.whitelist(methods=["GET"])
def messages(channel: str, before: str | None = None, after: str | None = None, around: str | None = None, limit: int = 40) -> dict:
	"""A page of the chat's messages (oldest first): the newest by default, those before / after a timestamp, or those
	around a message (to open a search result or a mention). Opening the newest page marks the chat read.
	{messages, more, newer, channel, seen, pins}."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	limit = max(1, min(100, cint(limit) or 40))
	if around:
		at = frappe.db.get_value(MSG, {"name": around, "channel_id": channel}, "creation")
		if not at:
			frappe.throw(_("That message isn't here any more."), frappe.DoesNotExistError)
		older = frappe.get_all(MSG, filters={"channel_id": channel, "creation": ["<=", at]}, fields=MSG_FIELDS, order_by="creation desc", limit=limit // 2 + 1)
		newer = frappe.get_all(MSG, filters={"channel_id": channel, "creation": [">", at]}, fields=MSG_FIELDS, order_by="creation asc", limit=limit // 2 + 1)
		more, has_newer = len(older) > limit // 2, len(newer) > limit // 2
		rows = list(reversed(older[: limit // 2])) + newer[: limit // 2]
	elif after:
		rows = frappe.get_all(MSG, filters={"channel_id": channel, "creation": [">", get_datetime(after)]}, fields=MSG_FIELDS,
							  order_by="creation asc", limit=limit + 1)
		has_newer, more = len(rows) > limit, False
		rows = rows[:limit]
	else:
		filters = {"channel_id": channel}
		if before:
			filters["creation"] = ["<", get_datetime(before)]
		rows = frappe.get_all(MSG, filters=filters, fields=MSG_FIELDS, order_by="creation desc", limit=limit + 1)
		more, has_newer = len(rows) > limit, False
		rows = list(reversed(rows[:limit]))
	if not before and not around and not has_newer and c.member:
		_read(channel, ctx)
	return {"messages": _out_many(ctx, rows, pins=_pins(channel)), "more": more, "newer": has_newer,
			"channel": _chat_info(ctx, c), "seen": _seen(channel, ctx)}


def _chat_info(ctx, c) -> dict:
	from qtt_platform.api import team_extras as extras

	names = _names(ctx)
	title, peer = c.channel_name, None
	if c.is_direct_message:
		peer_user = rules.dm_peer(c.channel_name, ctx.user)
		peer = {**_people(ctx.tenant).get(peer_user, {"user": peer_user, "name": peer_user}), **extras.presence_of([peer_user], ctx.tenant).get(peer_user, {})}
		title = names.get(peer_user, peer_user)
	muted = not frappe.db.get_value(MEM, {"channel_id": c.name, "user_id": ctx.user}, "allow_notifications") if c.member else False
	return {"id": c.name, "name": title, "dm": bool(c.is_direct_message), "private": c.type == "Private", "member": c.member,
			"about": c.channel_description or "", "general": c.channel_name == rules.GENERAL, "peer": peer, "muted": bool(muted),
			"members": frappe.db.count(MEM, {"channel_id": c.name}), "pins": len(_pins(c.name))}


def _post(ctx, channel: str, *, text: str | None = None, reply_to: str | None = None, thread_of: str | None = None,
		  message_type: str = "Text", file_url: str | None = None) -> frappe._dict:
	"""Write a message in a chat (or a message's thread). Returns the Raven Message."""
	if thread_of:
		channel = _ensure_thread(ctx, thread_of, channel)
	c = _channel(ctx, channel, need_member=True)
	text = str(text or "")
	if len(text) > rules.MAX_TEXT:
		frappe.throw(_("A message can be up to {0} characters.").format(rules.MAX_TEXT))
	people = _names(ctx)
	if c.get("is_thread"):
		pool = c.parent
	else:
		pool = c
	# @mentions: people of the business who can see this chat
	can_see = set(frappe.get_all(MEM, filters={"channel_id": pool.name}, pluck="user_id")) if pool.type == "Private" or pool.is_direct_message else set(people)
	mentions = {u: n for u, n in rules.mentions_in(text, people).items() if u in can_see}
	doc = {"doctype": MSG, "channel_id": channel, "message_type": message_type, "file": file_url,
		   "text": rules.text_to_html(text, mentions) if text.strip() else None, "content": text.strip() or None}
	if reply_to and frappe.db.get_value(MSG, reply_to, "channel_id") == channel:
		doc.update({"is_reply": 1, "linked_message": reply_to})
	m = frappe.get_doc(doc)
	m.flags.send_silently = True  # QTT's own push (team_events), not Raven's push service
	m.insert(ignore_permissions=True)
	frappe.db.set_value(MEM, {"channel_id": channel, "user_id": ctx.user}, "last_visit", now_datetime(), update_modified=False)
	return m


def _ensure_thread(ctx, message: str, channel: str | None = None) -> str:
	"""The thread of a message (made the first time someone replies in it, as Raven does): a private chat named after the
	message, with its writer and whoever replies in it."""
	root, parent = _message(ctx, message)
	if channel and channel not in (root.channel_id, message):
		frappe.throw(_("That message isn't in this chat."))
	if parent.get("is_thread"):
		frappe.throw(_("Replies in a thread can't have their own thread."))
	if not frappe.db.exists(CH, message):
		t = frappe.get_doc({"doctype": CH, "channel_name": message, "workspace": parent.workspace, "type": "Private", "is_thread": 1,
							"is_dm_thread": parent.is_direct_message, "channel_description": rules.preview(root.message_type, root.text or root.content, root.file)})
		t.flags.do_not_add_member = True
		t.insert(ignore_permissions=True)
		frappe.db.set_value(MSG, message, "is_thread", 1, update_modified=False)
	_quiet_join(message, [root.owner, ctx.user])
	return message


@frappe.whitelist(methods=["POST"])
def send(channel: str, text: str, reply_to: str | None = None, thread_of: str | None = None) -> dict:
	"""Send a message (up to 4,000 characters): *bold* _italic_ ~strike~ `code`, links, @Name for people who can see the
	chat, @everyone. reply_to: quote a message of the same chat. thread_of: reply in that message's thread."""
	ctx = _ctx()
	if not str(text or "").strip():
		frappe.throw(_("Write a message."))
	m = _post(ctx, channel, text=text, reply_to=reply_to, thread_of=thread_of)
	return _out_many(ctx, [frappe.db.get_value(MSG, m.name, MSG_FIELDS, as_dict=True)])[0]


@frappe.whitelist(methods=["POST"])
def send_file(channel: str, caption: str | None = None, thread_of: str | None = None) -> dict:
	"""Multipart `file`: a photo, file or voice note (voice-<seconds>s-….wav) for the chat, up to 25 MB. Kept private —
	only people in the chat can open it."""
	ctx = _ctx()
	target = _ensure_thread(ctx, thread_of, channel) if thread_of else channel
	_channel(ctx, target, need_member=True)
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a photo or file."))
	data = upload.stream.read(rules.MAX_FILE + 1)
	if len(data) > rules.MAX_FILE:
		frappe.throw(_("A file can be up to 25 MB."))
	name = (upload.filename or "file").strip()[-120:]
	f = frappe.get_doc({"doctype": "File", "file_name": name, "content": data, "is_private": 1, "attached_to_doctype": CH,
						"attached_to_name": target}).insert(ignore_permissions=True)
	m = _post(ctx, target, text=caption, message_type=rules.kind_of(name), file_url=f.file_url)
	return _out_many(ctx, [frappe.db.get_value(MSG, m.name, MSG_FIELDS, as_dict=True)])[0]


@frappe.whitelist(methods=["POST"])
def edit_message(message: str, text: str) -> dict:
	"""Change your own message (it shows "edited")."""
	ctx = _ctx()
	m, c = _message(ctx, message)
	if m.owner != ctx.user:
		frappe.throw(_("You can change only your own messages."), frappe.PermissionError)
	if m.message_type != "Text" and not m.file:
		frappe.throw(_("This message can't be changed."))
	if not str(text or "").strip() and not m.file:
		frappe.throw(_("Write a message."))
	if len(str(text or "")) > rules.MAX_TEXT:
		frappe.throw(_("A message can be up to {0} characters.").format(rules.MAX_TEXT))
	pool = c.parent if c.get("is_thread") else c
	people = _names(ctx)
	can_see = set(frappe.get_all(MEM, filters={"channel_id": pool.name}, pluck="user_id")) if pool.type == "Private" or pool.is_direct_message else set(people)
	mentions = {u: n for u, n in rules.mentions_in(text, people).items() if u in can_see}
	doc = frappe.get_doc(MSG, message)
	doc.text = rules.text_to_html(text, mentions) if str(text or "").strip() else None
	doc.content = str(text or "").strip() or None
	doc.is_edited = 1
	doc.flags.send_silently = True
	doc.save(ignore_permissions=True)
	changed(m.channel_id, message)
	return _out_many(ctx, [frappe.db.get_value(MSG, message, MSG_FIELDS, as_dict=True)], pins=_pins(m.channel_id))[0]


@frappe.whitelist(methods=["POST"])
def delete_message(message: str) -> dict:
	"""Delete your own message (and its thread)."""
	ctx = _ctx()
	row = frappe.db.get_value(MSG, message, ["channel_id", "owner"], as_dict=True)
	if not row:
		return {"deleted": True}
	_channel(ctx, row.channel_id)
	if row.owner != ctx.user:
		frappe.throw(_("You can delete only your own messages."), frappe.PermissionError)
	frappe.delete_doc(MSG, message, ignore_permissions=True)
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def react(message: str, emoji: str) -> dict:
	"""Add a reaction to a message, or take yours back if you'd already reacted with it. {reactions}."""
	from raven.api.reactions import calculate_message_reaction

	ctx = _ctx()
	m, _c = _message(ctx, message)
	emoji = str(emoji or "").strip()
	if not emoji or len(emoji) > 16:
		frappe.throw(_("Choose a reaction."))
	key = rules.escaped(emoji)
	mine = frappe.db.get_value(REACTION, {"message": message, "owner": ctx.user, "reaction_escaped": key})
	if mine:
		frappe.db.delete(REACTION, {"name": mine})
	else:
		frappe.get_doc({"doctype": REACTION, "reaction": emoji, "message": message, "channel_id": m.channel_id, "owner": ctx.user,
						"is_custom": 0, "reaction_escaped": key}).insert(ignore_permissions=True)
	calculate_message_reaction(message, m.channel_id, do_not_publish=True)
	changed(m.channel_id, message, extra={"reaction": None if mine else emoji, "by": ctx.user})
	raw = frappe.db.get_value(MSG, message, "message_reactions")
	return {"reactions": rules.reactions(raw, ctx.user, _names(ctx))}


@frappe.whitelist(methods=["POST"])
def pin(message: str) -> dict:
	"""Pin a message to its chat, or unpin it. Anyone in the chat can. {pinned}."""
	ctx = _ctx()
	m, c = _message(ctx, message)
	if c.get("is_thread"):
		frappe.throw(_("Pin the message in the chat, not in a thread."))
	if not c.member:
		frappe.throw(_("Join the channel first."))
	doc = frappe.get_doc(CH, m.channel_id)
	row = next((p for p in doc.pinned_messages if p.message_id == message), None)
	if row:
		doc.remove(row)
	else:
		doc.append("pinned_messages", {"message_id": message})
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	changed(m.channel_id, message)
	return {"pinned": not row}


@frappe.whitelist(methods=["GET"])
def thread(message: str) -> dict:
	"""A message's thread: the message, its replies (oldest first), who's in it. Opening it marks it read."""
	ctx = _ctx()
	root, c = _message(ctx, message)
	replies = []
	if frappe.db.exists(CH, message):
		replies = frappe.get_all(MSG, filters={"channel_id": message, "message_type": ["!=", "System"]}, fields=MSG_FIELDS,
								 order_by="creation asc", limit=500)
		if frappe.db.exists(MEM, {"channel_id": message, "user_id": ctx.user}):
			_read(message, ctx)
	names = _names(ctx)
	inside = frappe.get_all(MEM, filters={"channel_id": message}, pluck="user_id") if frappe.db.exists(CH, message) else [root.owner]
	return {"root": _out_many(ctx, [root], pins=_pins(root.channel_id))[0], "replies": _out_many(ctx, replies),
			"chat": _chat_info(ctx, c), "people": [{"user": u, "name": names.get(u, u)} for u in inside if u in names],
			"following": ctx.user in inside, "seen": _seen(message, ctx) if frappe.db.exists(CH, message) else {}}


def _my_threads(ctx, limit: int = 30) -> list[dict]:
	"""Threads this person is in (in this business), newest reply first."""
	rows = frappe.db.sql(f"""select c.name, c.last_message_timestamp, c.last_message_details, m.last_visit
		from `tab{CH}` c join `tab{MEM}` m on m.channel_id = c.name and m.user_id = %s
		where c.is_thread = 1 and (c.workspace = %s or c.is_dm_thread = 1)
		order by c.last_message_timestamp desc limit %s""", (ctx.user, ctx.ws, limit * 2), as_dict=True)
	out = []
	for r in rows:
		try:
			root, chat = _message(ctx, r.name)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		unread = frappe.db.count(MSG, {"channel_id": r.name, "creation": [">", r.last_visit or "2000-01-01"], "message_type": ["!=", "System"],
									   "owner": ["!=", ctx.user]})
		out.append({"id": r.name, "root": root, "chat": chat, "unread": unread, "last": _last(r)})
		if len(out) >= limit:
			break
	return out


@frappe.whitelist(methods=["GET"])
def threads() -> dict:
	"""Threads you're in, newest reply first, with new replies on top of each."""
	ctx = _ctx()
	rows = _my_threads(ctx)
	roots = _out_many(ctx, [t["root"] for t in rows])
	return {"threads": [{"id": t["id"], "root": r, "chat": _chat_info(ctx, t["chat"]), "unread": t["unread"], "last": t["last"]}
						for t, r in zip(rows, roots)]}


def _sign(message: str, exp: int) -> str:
	import hashlib
	import hmac

	from frappe.utils.password import get_encryption_key

	return hmac.new(get_encryption_key().encode(), f"team-file:{message}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


@frappe.whitelist(methods=["GET"])
def file_link(message: str) -> dict:
	"""A link to a message's file that opens in the browser for 10 minutes (the app's login doesn't go with it).
	Only for people in that chat."""
	import time

	from frappe.utils import get_url

	ctx = _ctx()
	row = frappe.db.get_value(MSG, message, ["channel_id", "file"], as_dict=True)
	if not row or not row.file:
		frappe.throw(_("That file isn't here any more."), frappe.DoesNotExistError)
	_channel(ctx, row.channel_id)
	exp = int(time.time()) + 600
	return {"url": get_url(f"/api/method/qtt_platform.api.team.file?message={message}&exp={exp}&sig={_sign(message, exp)}")}


@frappe.whitelist(methods=["GET"], allow_guest=True)
def file(message: str, exp: int | None = None, sig: str | None = None):
	"""A message's photo or file — for people in that chat, or with a link from file_link (10 minutes)."""
	import hmac
	import time

	row = frappe.db.get_value(MSG, message, ["channel_id", "file"], as_dict=True)
	if not row or not row.file:
		frappe.throw(_("That file isn't here any more."), frappe.DoesNotExistError)
	if sig and exp:
		if cint(exp) < time.time() or not hmac.compare_digest(str(sig), _sign(message, cint(exp))):
			frappe.throw(_("This link has expired. Open the file again from the chat."), frappe.PermissionError)
	else:
		if frappe.session.user == "Guest":
			frappe.throw(_("Sign in to open this file."), frappe.PermissionError)
		_channel(_ctx(), row.channel_id)
	f = frappe.get_doc("File", {"file_url": row.file})
	frappe.local.response.filename = f.file_name
	frappe.local.response.filecontent = f.get_content()
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(methods=["POST"])
def start_dm(user: str) -> dict:
	"""A direct message with someone in the business (the same one each time). {id}."""
	ctx = _ctx()
	if user == ctx.user or user not in _people(ctx.tenant):
		frappe.throw(_("Choose someone in your business."))
	_raven_user(user)
	name = frappe.db.get_value(CH, {"is_direct_message": 1, "channel_name": ["in", [rules.dm_name(ctx.user, user), rules.dm_name(user, ctx.user)]]}, "name")
	if not name:
		name = frappe.get_doc({"doctype": CH, "channel_name": rules.dm_name(ctx.user, user), "is_direct_message": 1,
							   "is_self_message": 0}).insert(ignore_permissions=True).name
	return {"id": name}


@frappe.whitelist(methods=["POST"])
def new_channel(name: str, about: str | None = None, private: int = 0, members=None) -> dict:
	"""A channel: open to everyone in the business, or private with the people chosen (you're always in it). {id}."""
	ctx = _ctx()
	clean = rules.clean_channel_name(name)
	if len(clean) < 2:
		frappe.throw(_("Give the channel a name."))
	if frappe.db.exists(CH, rules.channel_id(ctx.ws, clean)):
		frappe.throw(_("There's already a channel called {0}.").format(clean))
	people = _people(ctx.tenant)
	members = json.loads(members) if isinstance(members, str) else (members or [])
	ch = frappe.get_doc({"doctype": CH, "channel_name": clean, "channel_description": (about or "").strip()[:200],
						 "type": "Private" if cint(private) else "Public", "workspace": ctx.ws}).insert(ignore_permissions=True)
	add = [u for u in members if u in people and u != ctx.user]
	for u in add:
		_raven_user(u)
	ch.add_members(add)
	return {"id": ch.name}


@frappe.whitelist(methods=["GET"])
def channel(channel: str) -> dict:
	"""A chat's details: the people in it (with presence), pinned messages, notifications."""
	from qtt_platform.api import team_extras as extras

	ctx = _ctx()
	c = _channel(ctx, channel)
	people = _people(ctx.tenant)
	inside = frappe.get_all(MEM, filters={"channel_id": channel}, fields=["user_id", "is_admin"])
	live = extras.presence_of([m.user_id for m in inside], ctx.tenant)
	pins = _pins(channel)
	pinned = frappe.get_all(MSG, filters={"name": ["in", list(pins) or [""]]}, fields=MSG_FIELDS, order_by="creation desc")
	admin = any(m.user_id == ctx.user and m.is_admin for m in inside) or ctx.admin
	return {**_chat_info(ctx, c), "name": c.channel_name if not c.is_direct_message else _chat_info(ctx, c)["name"],
			"members": [{**people[m.user_id], **live.get(m.user_id, {}), "admin": bool(m.is_admin)} for m in inside if m.user_id in people],
			"pinned": _out_many(ctx, pinned, pins=pins),
			"can_add": not c.is_direct_message and c.channel_name != rules.GENERAL and c.member,
			"can_edit": not c.is_direct_message and c.member and (admin or c.channel_name != rules.GENERAL)}


channel_info = channel


@frappe.whitelist(methods=["POST"])
def update_channel(channel: str, about: str | None = None, name: str | None = None) -> dict:
	"""Describe a channel (anyone in it), or rename it (channel admins and the business's owners / admins). #general keeps
	its name."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	if c.is_direct_message or not c.member:
		frappe.throw(_("Only people in the channel can change it."))
	doc = frappe.get_doc(CH, channel)
	if about is not None:
		doc.channel_description = str(about).strip()[:200]
	if name and rules.clean_channel_name(name) != c.channel_name:
		if c.channel_name == rules.GENERAL:
			frappe.throw(_("#general keeps its name."))
		admin = frappe.db.get_value(MEM, {"channel_id": channel, "user_id": ctx.user}, "is_admin") or ctx.admin
		if not admin:
			frappe.throw(_("Ask the channel's admin to rename it."), frappe.PermissionError)
		clean = rules.clean_channel_name(name)
		if len(clean) < 2:
			frappe.throw(_("Give the channel a name."))
		if frappe.db.exists(CH, {"workspace": ctx.ws, "channel_name": clean}):
			frappe.throw(_("There's already a channel called {0}.").format(clean))
		doc.channel_name = clean  # the id stays; Raven shows the new name
	doc.save(ignore_permissions=True)
	changed(channel, "", "updated")
	return channel_info(channel)


@frappe.whitelist(methods=["POST"])
def add_members(channel: str, members=None) -> dict:
	"""Add people from the business to a channel you're in."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	if c.is_direct_message or not c.member:
		frappe.throw(_("You can add people only to a channel you're in."))
	people = _people(ctx.tenant)
	members = json.loads(members) if isinstance(members, str) else (members or [])
	add = [u for u in members if u in people]
	for u in add:
		_raven_user(u)
	frappe.get_doc(CH, channel).add_members(add)
	return channel_info(channel)


@frappe.whitelist(methods=["POST"])
def leave(channel: str) -> dict:
	"""Leave a channel or a thread (#general can't be left — it's everyone in the business)."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	if c.is_direct_message or c.channel_name == rules.GENERAL:
		frappe.throw(_("You can't leave this chat."))
	row = frappe.db.get_value(MEM, {"channel_id": channel, "user_id": ctx.user})
	if row:
		if c.get("is_thread"):
			frappe.db.delete(MEM, {"name": row})  # quietly: no "left" message in a thread
		else:
			frappe.delete_doc(MEM, row, ignore_permissions=True)
	return {"left": True}


@frappe.whitelist(methods=["POST"])
def mute(channel: str, muted: int = 1) -> dict:
	"""Phone notifications for a chat: muted = only when someone @mentions you; unmuted = every message."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	if not c.member:
		frappe.throw(_("Join the channel first."))
	frappe.db.set_value(MEM, {"channel_id": channel, "user_id": ctx.user}, "allow_notifications", 0 if cint(muted) else 1)
	return {"muted": bool(cint(muted))}
