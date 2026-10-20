"""
Team chat (api/team.py) — live updates and phone notifications.

  Raven Message after_insert / on_trash  → "qtt_team:message" to everyone in the chat — and, for a reply in a thread,
                                           to the chat the thread belongs to (its reply count) — the app refreshes;
                                           phone notifications (below)
  api.team.changed()                      → the same event for edits, reactions, pins, read ticks
  QTT Tenant Membership on_update / trash → the business's Team workspace follows its members

Phone notifications for a new message go to the others in the chat, except:
  - a muted chat notifies only when you're @mentioned (or @everyone);
  - Do not disturb (Team › your status) holds them all until it ends;
  - system messages ("X joined") never notify.
A thread notifies the people in the thread (its writer and whoever replied).

Only business chats (workspace "qtt-…", a direct message between people of one business, or a thread of either) —
QTT's own Raven workspace keeps Raven's own behaviour. Never breaks the save it hangs on.
"""

import frappe

from qtt_platform import team_rules as rules


def _business_channel(channel_id: str):
	c = frappe.db.get_value("Raven Channel", channel_id, ["name", "channel_name", "workspace", "is_direct_message", "is_thread"], as_dict=True)
	if not c:
		return None
	if c.is_thread:
		parent = frappe.db.get_value("Raven Message", c.name, "channel_id")
		p = _business_channel(parent) if parent else None
		if not p:
			return None
		c.tenant, c.parent = p.tenant, p
		return c
	if c.is_direct_message:
		# a DM between two people of the same business (the business = the one both are active in)
		users = [u.strip() for u in (c.channel_name or "").split(" _ ")]
		if len(users) != 2:
			return None
		shared = set(frappe.get_all("QTT Tenant Membership", filters={"user": users[0], "status": "active"}, pluck="tenant")) & set(
			frappe.get_all("QTT Tenant Membership", filters={"user": users[1], "status": "active"}, pluck="tenant"))
		if not shared:
			return None
		c.tenant = sorted(shared)[0]
		return c
	if not rules.is_business_workspace(c.workspace):
		return None
	c.tenant = c.workspace[len(rules.PREFIX):]
	return c


def _members(channel: str) -> list:
	return frappe.get_all("Raven Channel Member", filters={"channel_id": channel}, fields=["user_id", "allow_notifications"])


def publish(channel: str, payload: dict) -> None:
	""""qtt_team:message" {channel, …payload} to everyone in the chat; a thread's also goes to its chat (thread_of)."""
	c = _business_channel(channel)
	if not c:
		return
	data = {"channel": channel, "tenant": c.tenant, **payload}
	users = {m.user_id for m in _members(channel)}
	if c.get("parent"):
		data["thread_of"] = channel
		data["parent"] = c.parent.name
		users |= {m.user_id for m in _members(c.parent.name)}
	for user in users:
		frappe.publish_realtime("qtt_team:message", data, user=user, after_commit=True)


def on_message(doc, method=None):
	try:
		c = _business_channel(doc.channel_id)
		if not c:
			return
		deleted = method == "on_trash"
		publish(doc.channel_id, {"message": doc.name, "owner": doc.owner, "deleted": deleted, "kind": "deleted" if deleted else "new"})
		if deleted or doc.message_type == "System":
			return
		_notify(doc, c)
	except Exception:
		frappe.log_error(title="Team chat: live update failed")


def _notify(doc, c) -> None:
	from qtt_platform.api import team_extras as extras

	members = _members(doc.channel_id)
	text = rules.html_to_text(doc.text or doc.content or "")
	mentioned = {r.user for r in (doc.get("mentions") or [])}
	everyone = rules.mentions_everyone(text) and not c.is_direct_message
	for_all, for_mention = [], []
	for m in members:
		if m.user_id == doc.owner:
			continue
		if m.user_id in mentioned or everyone:
			for_mention.append(m.user_id)
		elif m.allow_notifications:
			for_all.append(m.user_id)
	# mentioned people who can read the chat but aren't in it yet (an open channel)
	for user in mentioned - {m.user_id for m in members} - {doc.owner}:
		for_mention.append(user)
	quiet = extras.dnd_users(for_all + for_mention)
	for_all = [u for u in for_all if u not in quiet]
	for_mention = [u for u in for_mention if u not in quiet]
	if not for_all and not for_mention:
		return
	sender = frappe.db.get_value("User", doc.owner, "full_name") or doc.owner
	where = _where(c)
	body = rules.preview(doc.message_type, doc.text or doc.content, doc.file)
	data = {"kind": "team", "tenant": c.tenant, "channel": c.parent.name if c.get("parent") else doc.channel_id,
			"message": doc.name, "thread_of": doc.channel_id if c.get("parent") else ""}
	jobs = []
	if for_all:
		jobs.append((for_all, sender if c.is_direct_message else f"{sender} · {where}", body))
	if for_mention:
		jobs.append((for_mention, f"{sender} mentioned you · {where}", body))

	def send():
		for users, title, text_ in jobs:
			send_push(users, title, text_, data)

	if frappe.request and hasattr(frappe.request, "after_response"):
		frappe.request.after_response.add(send)
	else:
		for users, title, text_ in jobs:
			frappe.enqueue(send_push, queue="short", users=users, title=title, body=text_, data=data, enqueue_after_commit=True)


def _where(c) -> str:
	if c.get("parent"):
		return "thread in " + _where(c.parent)
	return "direct message" if c.is_direct_message else f"#{c.channel_name}"


def send_push(users, title, body, data):
	from qtt_platform import push

	push.notify(users, title=title, body=body, data=data, collapse_key=f"team-{data.get('channel')}")


def on_membership(doc, method=None):
	"""The business's Team workspace follows its members (only once the business has opened Team); someone who leaves
	(or is suspended) also leaves its Nextcloud groups (Workplace)."""
	if method == "on_trash" or doc.status != "active":
		from qtt_platform.api.workplace import drop

		drop(doc.tenant, doc.user)
	try:
		if "raven" not in frappe.get_installed_apps():
			return
		if not frappe.db.exists("Raven Workspace", rules.workspace_name(doc.tenant)):
			return
		from qtt_platform.api.team import sync

		sync(doc.tenant, exclude=doc.user if method == "on_trash" else None)
	except Exception:
		frappe.log_error(title="Team chat: member sync failed")
