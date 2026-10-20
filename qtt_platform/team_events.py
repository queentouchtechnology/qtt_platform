"""
Team chat (api/team.py) — live updates and phone notifications.

  Raven Message after_insert / on_trash  → "qtt_team:message" to everyone in the chat (the app refreshes the open chat
                                           and the unread counts); a phone notification to the others (not for system
                                           messages, not when the person switched notifications off for the chat)
  QTT Tenant Membership on_update / trash → the business's Team workspace follows its members

Only business chats (workspace "qtt-…" or a direct message between people of one business) — QTT's own Raven
workspace keeps Raven's own behaviour. Never breaks the save it hangs on.
"""

import frappe

from qtt_platform import team_rules as rules


def _business_channel(channel_id: str):
	c = frappe.db.get_value("Raven Channel", channel_id, ["name", "channel_name", "workspace", "is_direct_message"], as_dict=True)
	if not c:
		return None
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


def on_message(doc, method=None):
	try:
		c = _business_channel(doc.channel_id)
		if not c:
			return
		members = frappe.get_all("Raven Channel Member", filters={"channel_id": doc.channel_id}, fields=["user_id", "allow_notifications"])
		deleted = method == "on_trash"
		payload = {"channel": doc.channel_id, "message": doc.name, "owner": doc.owner, "deleted": deleted, "tenant": c.tenant}
		for m in members:
			frappe.publish_realtime("qtt_team:message", payload, user=m.user_id, after_commit=True)
		if deleted or doc.message_type == "System":
			return
		others = [m.user_id for m in members if m.user_id != doc.owner and m.allow_notifications]
		if not others:
			return
		sender = frappe.db.get_value("User", doc.owner, "full_name") or doc.owner
		title = sender if c.is_direct_message else f"{sender} · #{c.channel_name}"
		body = rules.preview(doc.message_type, doc.text or doc.content, doc.file)
		data = {"kind": "team", "tenant": c.tenant, "channel": doc.channel_id}

		def send():
			from qtt_platform import push

			push.notify(others, title=title, body=body, data=data, collapse_key=f"team-{doc.channel_id}")

		if frappe.request and hasattr(frappe.request, "after_response"):
			frappe.request.after_response.add(send)
		else:
			frappe.enqueue(send_push, queue="short", users=others, title=title, body=body, data=data, enqueue_after_commit=True)
	except Exception:
		frappe.log_error(title="Team chat: live update failed")


def send_push(users, title, body, data):
	from qtt_platform import push

	push.notify(users, title=title, body=body, data=data, collapse_key=f"team-{data.get('channel')}")


def on_membership(doc, method=None):
	"""The business's Team workspace follows its members (only once the business has opened Team)."""
	try:
		if "raven" not in frappe.get_installed_apps():
			return
		if not frappe.db.exists("Raven Workspace", rules.workspace_name(doc.tenant)):
			return
		from qtt_platform.api.team import sync

		sync(doc.tenant, exclude=doc.user if method == "on_trash" else None)
	except Exception:
		frappe.log_error(title="Team chat: member sync failed")
