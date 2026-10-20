"""
Team — the business's own team chat, free in QTT OS (PROJ-0013). Built on Raven (installed on the site): each
business gets a private Raven workspace ("qtt-<tenant>") with #general for everyone, channels its members make and
direct messages between its members. Every call checks the business and the person's membership here — customers
never get Raven's role (it would open Desk), so Raven's own API isn't used; its records and behaviour are (last
message, system messages, its realtime).

  home           channels (with unread counts and the last message), direct messages, the people in the business
  messages       a channel's messages, newest page first (before= for older); marks it read
  send           a message (plain text; reply_to for a reply)
  send_file      a photo or file (multipart `file`, up to 25 MB)
  file           a photo / file of a message — only for people in that chat
  delete_message your own message
  start_dm       a direct message with someone in the business
  new_channel    a channel: open to the whole business, or private with the people chosen
  channel        a channel's details and members
  add_members    add people from the business to a channel
  leave          leave a channel (not #general)

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
GOVERNANCE = ("Tenant Owner", "Tenant Admin")


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
	"""Everyone active in the business: {user: {name, image, role}}."""
	rows = frappe.get_all("QTT Tenant Membership", filters={"tenant": tenant, "status": "active"}, fields=["user", "tenant_role"])
	users = [r.user for r in rows]
	info = {u.name: u for u in frappe.get_all("User", filters={"name": ["in", users or [""]]}, fields=["name", "full_name", "user_image", "enabled"])}
	return {r.user: {"user": r.user, "name": (info.get(r.user) or {}).get("full_name") or r.user, "image": (info.get(r.user) or {}).get("user_image"),
					 "role": r.tenant_role} for r in rows if (info.get(r.user) or {}).get("enabled", 1)}


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
	people = _people(tenant)
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
	inside = set(frappe.get_all(MEM, filters={"channel_id": general}, pluck="user_id"))
	added = [u for u in people if u not in inside]
	for user in added:
		frappe.get_doc({"doctype": MEM, "channel_id": general, "user_id": user, "is_admin": 0, "last_visit": now_datetime(),
						"allow_notifications": 1}).db_insert()
	if added:
		from raven.utils import delete_channel_members_cache

		delete_channel_members_cache(general)


def _channel(ctx, channel: str, *, need_member: bool = False) -> frappe._dict:
	"""The channel, if this person may see it in this business (a channel of its workspace they're in or that's open
	to the business, or a direct message with someone in it)."""
	c = frappe.db.get_value(CH, channel, ["name", "channel_name", "channel_description", "type", "workspace", "is_direct_message",
										  "is_self_message", "is_archived", "is_thread", "owner"], as_dict=True)
	if not c:
		frappe.throw(_("That chat isn't here any more."), frappe.DoesNotExistError)
	member = frappe.db.exists(MEM, {"channel_id": channel, "user_id": ctx.user})
	if c.is_direct_message:
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


def _join(channel: str, user: str) -> None:
	frappe.get_doc({"doctype": MEM, "channel_id": channel, "user_id": user}).insert(ignore_permissions=True)


def _unread(channel: str, user: str) -> int:
	last = frappe.db.get_value(MEM, {"channel_id": channel, "user_id": user}, "last_visit")
	return frappe.db.count(MSG, {"channel_id": channel, "creation": [">", last or "2000-01-01"], "message_type": ["!=", "System"],
								 "owner": ["!=", user]})


def _last(row) -> dict | None:
	d = row.last_message_details
	try:
		d = json.loads(d) if isinstance(d, str) else (d or {})
	except ValueError:
		d = {}
	if not row.last_message_timestamp:
		return None
	return {"text": rules.preview(d.get("message_type"), d.get("content")), "owner": d.get("owner"), "at": str(row.last_message_timestamp)}


# ---- endpoints -------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def home() -> dict:
	"""The business's chats for this person: channels (open to the business, or private ones they're in), direct
	messages with people in the business, each with unread and the last message; and the people."""
	ctx = _ctx()
	people = _people(ctx.tenant)
	mine = set(frappe.get_all(MEM, filters={"user_id": ctx.user}, pluck="channel_id"))
	fields = ["name", "channel_name", "channel_description", "type", "is_archived", "is_thread", "last_message_timestamp", "last_message_details"]
	channels = []
	for c in frappe.get_all(CH, filters={"workspace": ctx.ws, "is_direct_message": 0, "is_thread": 0, "is_archived": 0}, fields=fields):
		member = c.name in mine
		if not rules.can_see(c, member):
			continue
		channels.append({"id": c.name, "name": c.channel_name, "about": c.channel_description or "", "private": c.type == "Private",
						 "member": member, "general": c.channel_name == rules.GENERAL, "unread": _unread(c.name, ctx.user) if member else 0,
						 "last": _last(c)})
	channels.sort(key=lambda c: (not c["general"], c["name"]))
	dms = []
	for c in frappe.get_all(CH, filters={"is_direct_message": 1, "is_self_message": 0, "name": ["in", list(mine) or [""]]},
							fields=["name", "channel_name", "last_message_timestamp", "last_message_details"]):
		peer = rules.dm_peer(c.channel_name, ctx.user)
		if peer in people:
			dms.append({"id": c.name, "peer": people[peer], "unread": _unread(c.name, ctx.user), "last": _last(c)})
	dms.sort(key=lambda d: (d["last"] or {}).get("at") or "", reverse=True)
	return {"channels": channels, "dms": dms, "people": [p for u, p in people.items() if u != ctx.user], "me": ctx.user,
			"can_manage": ctx.admin}


def _out(m, names: dict, me: str) -> dict:
	reply = m.replied_message_details
	try:
		reply = json.loads(reply) if isinstance(reply, str) else reply
	except ValueError:
		reply = None
	return {"id": m.name, "type": m.message_type, "text": rules.html_to_text(m.text or m.content or ""), "owner": m.owner,
			"name": names.get(m.owner, m.owner), "at": str(m.creation), "mine": m.owner == me, "edited": bool(m.is_edited),
			"file": f"/api/method/qtt_platform.api.team.file?message={m.name}" if m.file else None,
			"file_name": (m.file or "").rsplit("/", 1)[-1] or None,
			"reply": {"id": m.linked_message, "text": rules.preview((reply or {}).get("message_type"), (reply or {}).get("content") or (reply or {}).get("text")),
					  "name": names.get((reply or {}).get("owner"), (reply or {}).get("owner"))} if m.is_reply and reply else None}


@frappe.whitelist(methods=["GET"])
def messages(channel: str, before: str | None = None, limit: int = 40) -> dict:
	"""A page of the chat's messages (oldest first), the newest by default or those before `before` (a timestamp).
	Opening the newest page marks the chat read. {messages, more, channel}."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	limit = max(1, min(100, cint(limit) or 40))
	filters = {"channel_id": channel}
	if before:
		filters["creation"] = ["<", get_datetime(before)]
	rows = frappe.get_all(MSG, filters=filters, fields=["name", "owner", "creation", "text", "content", "message_type", "file", "is_reply",
															"linked_message", "replied_message_details", "is_edited"],
						  order_by="creation desc", limit=limit + 1)
	more = len(rows) > limit
	rows = list(reversed(rows[:limit]))
	names = {p["user"]: p["name"] for p in _people(ctx.tenant).values()}
	if not before and c.member:
		frappe.db.set_value(MEM, {"channel_id": channel, "user_id": ctx.user}, "last_visit", now_datetime(), update_modified=False)
	title = c.channel_name
	if c.is_direct_message:
		peer = rules.dm_peer(c.channel_name, ctx.user)
		title = names.get(peer, peer)
	return {"messages": [_out(m, names, ctx.user) for m in rows], "more": more,
			"channel": {"id": c.name, "name": title, "dm": bool(c.is_direct_message), "private": c.type == "Private", "member": c.member,
						"about": c.channel_description or "", "general": c.channel_name == rules.GENERAL}}


@frappe.whitelist(methods=["POST"])
def send(channel: str, text: str, reply_to: str | None = None) -> dict:
	"""Send a message (plain text, up to 4,000 characters; links become links). reply_to: a message in the same chat."""
	ctx = _ctx()
	_channel(ctx, channel, need_member=True)
	if not str(text or "").strip():
		frappe.throw(_("Write a message."))
	if len(str(text)) > rules.MAX_TEXT:
		frappe.throw(_("A message can be up to {0} characters.").format(rules.MAX_TEXT))
	doc = {"doctype": MSG, "channel_id": channel, "text": rules.text_to_html(text), "content": str(text).strip(), "message_type": "Text"}
	if reply_to and frappe.db.get_value(MSG, reply_to, "channel_id") == channel:
		doc.update({"is_reply": 1, "linked_message": reply_to})
	m = frappe.get_doc(doc)
	m.flags.send_silently = True  # QTT's own push (team_events), not Raven's push service
	m.insert(ignore_permissions=True)
	names = {p["user"]: p["name"] for p in _people(ctx.tenant).values()}
	frappe.db.set_value(MEM, {"channel_id": channel, "user_id": ctx.user}, "last_visit", now_datetime(), update_modified=False)
	return _out(frappe.get_doc(MSG, m.name), names, ctx.user)


@frappe.whitelist(methods=["POST"])
def send_file(channel: str, caption: str | None = None) -> dict:
	"""Multipart `file`: a photo or file for the chat (up to 25 MB). Kept private — only people in the chat can open it."""
	ctx = _ctx()
	_channel(ctx, channel, need_member=True)
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a photo or file."))
	data = upload.stream.read(rules.MAX_FILE + 1)
	if len(data) > rules.MAX_FILE:
		frappe.throw(_("A file can be up to 25 MB."))
	name = (upload.filename or "file").strip()[-120:]
	f = frappe.get_doc({"doctype": "File", "file_name": name, "content": data, "is_private": 1, "attached_to_doctype": CH,
						"attached_to_name": channel}).insert(ignore_permissions=True)
	doc = {"doctype": MSG, "channel_id": channel, "message_type": rules.kind_of(name), "file": f.file_url,
		   "text": rules.text_to_html(caption) if caption else None, "content": (caption or "").strip() or None}
	m = frappe.get_doc(doc)
	m.flags.send_silently = True  # QTT's own push (team_events), not Raven's push service
	m.insert(ignore_permissions=True)
	names = {p["user"]: p["name"] for p in _people(ctx.tenant).values()}
	return _out(frappe.get_doc(MSG, m.name), names, ctx.user)


@frappe.whitelist(methods=["GET"])
def file(message: str):
	"""A message's photo or file — only for people in that chat."""
	ctx = _ctx()
	row = frappe.db.get_value(MSG, message, ["channel_id", "file"], as_dict=True)
	if not row or not row.file:
		frappe.throw(_("That file isn't here any more."), frappe.DoesNotExistError)
	_channel(ctx, row.channel_id)
	f = frappe.get_doc("File", {"file_url": row.file})
	frappe.local.response.filename = f.file_name
	frappe.local.response.filecontent = f.get_content()
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(methods=["POST"])
def delete_message(message: str) -> dict:
	"""Delete your own message."""
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
	"""A channel's details and the people in it."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	people = _people(ctx.tenant)
	inside = frappe.get_all(MEM, filters={"channel_id": channel}, fields=["user_id", "is_admin"])
	return {"id": c.name, "name": c.channel_name, "about": c.channel_description or "", "private": c.type == "Private",
			"general": c.channel_name == rules.GENERAL, "dm": bool(c.is_direct_message), "member": c.member,
			"members": [{**people[m.user_id], "admin": bool(m.is_admin)} for m in inside if m.user_id in people],
			"can_add": not c.is_direct_message and c.channel_name != rules.GENERAL and c.member}


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


channel_info = channel


@frappe.whitelist(methods=["POST"])
def leave(channel: str) -> dict:
	"""Leave a channel (#general can't be left — it's everyone in the business)."""
	ctx = _ctx()
	c = _channel(ctx, channel)
	if c.is_direct_message or c.channel_name == rules.GENERAL:
		frappe.throw(_("You can't leave this chat."))
	row = frappe.db.get_value(MEM, {"channel_id": channel, "user_id": ctx.user})
	if row:
		frappe.delete_doc(MEM, row, ignore_permissions=True)
	return {"left": True}
