"""
Team calls — voice and video in any chat, free for every business (PROJ-0014, TASK-233); screen sharing with Office
Pulse (PROJ-0015 B). Media goes through QTT's own LiveKit server (QTT Workplace Settings); a call's room is the chat's
id, so everyone who can see the chat can join it.

  call      the chat's call now: who's in it, video or not, since when; what you may do (share your screen)
  start     start a call (rings the other person in a direct message; tells the channel) — and join it
  join      join the chat's call: {url, token} for the app's LiveKit client
  decline   don't take a ringing call (the caller sees it)
  webhook   LiveKit → Frappe (signed): people joining / leaving; when the room ends, a line in the chat
            ("📞 Call · 12 min · Anna, Ravi" or "missed")

Live: "qtt_team:call" {channel, kind: ring | started | joined | left | ended | declined, by, name, video, count}.
"""

import json
import time

import frappe
from frappe import _
from frappe.utils import cint

from qtt_platform import team_rules
from qtt_platform import workplace_rules as rules
from qtt_platform.api import team

SETTINGS = "QTT Workplace Settings"


def _key(room: str) -> str:
	return f"qtt_team_call|{room}"


def state(room: str) -> dict | None:
	return frappe.cache().get_value(_key(room))


def _save(room: str, s: dict | None) -> None:
	if s is None:
		frappe.cache().delete_value(_key(room))
	else:
		frappe.cache().set_value(_key(room), s, expires_in_sec=12 * 3600)


def _settings():
	s = frappe.get_cached_doc(SETTINGS)
	if not s.calls_enabled or not s.livekit_url or not s.livekit_api_key:
		frappe.throw(_("Calls aren't set up yet."))
	return s


def _secret(s) -> str:
	return s.get_password("livekit_api_secret", raise_exception=False) or ""


def can_screen_share(tenant: str, user: str) -> bool:
	"""Screen sharing (and remote control) come with Office Pulse."""
	from qtt_platform.product.guards import has_product_access

	return has_product_access(tenant, rules.PULSE, user)


def _members(channel: str) -> list[str]:
	return frappe.get_all(team.MEM, filters={"channel_id": channel}, pluck="user_id")


def _tell(channel: str, payload: dict, users: list[str] | None = None) -> None:
	for u in users if users is not None else _members(channel):
		frappe.publish_realtime("qtt_team:call", {"channel": channel, **payload}, user=u, after_commit=True)


def active(chats: list[str]) -> dict[str, dict]:
	"""Calls going on in these chats: {chat: {count, video, since}} (for the Team list)."""
	out = {}
	for c in chats:
		s = state(c)
		if s and s.get("inside"):
			out[c] = {"count": len(s["inside"]), "video": bool(s.get("video")), "since": rules.stamp(s.get("started_at"))}
	return out


def _out(ctx, chat, s: dict | None) -> dict:
	names = team._names(ctx)
	inside = list((s or {}).get("inside") or {})
	return {"channel": chat.name, "active": bool(inside), "video": bool((s or {}).get("video")), "since": rules.stamp((s or {}).get("started_at")),
			"inside": [{"user": u, "name": names.get(u, u)} for u in inside],
			"can_screen_share": can_screen_share(ctx.tenant, ctx.user), "dm": bool(chat.is_direct_message)}


@frappe.whitelist(methods=["GET"])
def call(channel: str) -> dict:
	"""The chat's call now (who's in it), and what you may do in it."""
	ctx = team._ctx()
	chat = team._channel(ctx, channel)
	return _out(ctx, chat, state(channel))


def _join_payload(ctx, chat, s: dict | None) -> dict:
	cfg = _settings()
	names = team._names(ctx)
	token = rules.call_token(key=cfg.livekit_api_key, secret=_secret(cfg), room=chat.name, user=ctx.user,
							 name=names.get(ctx.user, ctx.user), screen_share=can_screen_share(ctx.tenant, ctx.user),
							 metadata={"tenant": ctx.tenant})
	return {"url": cfg.livekit_url, "token": token, **_out(ctx, chat, s)}


@frappe.whitelist(methods=["POST"])
def start(channel: str, video: int = 0) -> dict:
	"""Start a call in a chat and join it. A direct message rings the other person (a phone notification too); a
	channel shows "call started" to its people (a phone notification for those who haven't muted it). If a call is
	already going on, this just joins it."""
	ctx = team._ctx()
	chat = team._channel(ctx, channel)
	if chat.get("is_thread"):
		frappe.throw(_("Calls are in chats, not threads."))
	s = state(channel)
	if not s or not s.get("inside"):
		s = {"started_by": ctx.user, "started_at": time.time(), "video": bool(cint(video)), "inside": {}, "ever": [], "chat_tenant": ctx.tenant}
		_save(channel, s)
		_ring(ctx, chat, bool(cint(video)))
	return _join_payload(ctx, chat, s)


def _ring(ctx, chat, video: bool) -> None:
	from qtt_platform.api import team_extras
	from qtt_platform.team_events import send_push

	names = team._names(ctx)
	me = names.get(ctx.user, ctx.user)
	rows = frappe.get_all(team.MEM, filters={"channel_id": chat.name, "user_id": ["!=", ctx.user]}, fields=["user_id", "allow_notifications"])
	others = [r.user_id for r in rows]
	payload = {"kind": "ring" if chat.is_direct_message else "started", "by": ctx.user, "name": me, "video": video,
			   "title": me if chat.is_direct_message else f"#{chat.channel_name}", "tenant": ctx.tenant}
	_tell(chat.name, payload, others)
	quiet = team_extras.dnd_users(others)
	push_to = [r.user_id for r in rows if r.user_id not in quiet and (chat.is_direct_message or r.allow_notifications)]
	if push_to:
		title = (f"📹 {me} is video calling" if video else f"📞 {me} is calling") if chat.is_direct_message else f"📞 {me} started a call · #{chat.channel_name}"
		frappe.enqueue(send_push, queue="short", enqueue_after_commit=True, users=push_to, title=title,
					   body=_("Tap to join"), data={"kind": "team_call", "tenant": ctx.tenant, "channel": chat.name, "video": "1" if video else ""})


@frappe.whitelist(methods=["POST"])
def join(channel: str) -> dict:
	"""Join the chat's call (or be the first in it): {url, token, …} for the app."""
	ctx = team._ctx()
	chat = team._channel(ctx, channel)
	if chat.get("is_thread"):
		frappe.throw(_("Calls are in chats, not threads."))
	s = state(channel)
	if not s:
		s = {"started_by": ctx.user, "started_at": time.time(), "video": False, "inside": {}, "ever": [], "chat_tenant": ctx.tenant}
		_save(channel, s)
	return _join_payload(ctx, chat, s)


@frappe.whitelist(methods=["POST"])
def decline(channel: str) -> dict:
	"""Don't take the ringing call — the people in it see "declined"."""
	ctx = team._ctx()
	chat = team._channel(ctx, channel)
	s = state(channel) or {}
	names = team._names(ctx)
	_tell(chat.name, {"kind": "declined", "by": ctx.user, "name": names.get(ctx.user, ctx.user)}, list(s.get("inside") or {}) or [s.get("started_by")])
	return {"ok": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook():
	"""LiveKit → Frappe: who joins and leaves a call; when it ends, a line in the chat. Signed with the API secret."""
	cfg = frappe.get_cached_doc(SETTINGS)
	body = frappe.request.get_data() or b""
	if not cfg.livekit_api_secret or not rules.webhook_ok(body, frappe.get_request_header("Authorization") or "", _secret(cfg)):
		frappe.local.response.http_status_code = 401
		return {"ok": False}
	try:
		data = json.loads(body or b"{}")
	except ValueError:
		return {"ok": False}
	event = data.get("event")
	room = (data.get("room") or {}).get("name") or ""
	who = (data.get("participant") or {}).get("identity")
	if not room or not frappe.db.exists(team.CH, room):
		return {"ok": True}
	frappe.set_user("Administrator")
	s = state(room) or {"started_by": who, "started_at": time.time(), "video": False, "inside": {}, "ever": []}
	if event == "participant_joined" and who:
		s["inside"][who] = time.time()
		if who not in s["ever"]:
			s["ever"].append(who)
		_save(room, s)
		_tell(room, {"kind": "joined", "by": who, "count": len(s["inside"])})
	elif event == "participant_left" and who:
		s["inside"].pop(who, None)
		_save(room, s)
		_tell(room, {"kind": "left", "by": who, "count": len(s["inside"])})
	elif event == "room_finished":
		_finish(room, s)
	return {"ok": True}


def _finish(room: str, s: dict) -> None:
	"""The call ended: a line in the chat, and everyone's app hears it."""
	_save(room, None)
	try:
		from qtt_platform.api.team import _names_of

		names = _names_of([u for u in s.get("ever") or []])
		text = rules.call_summary(bool(s.get("video")), rules.call_minutes(s.get("started_at"), time.time()),
								  [names.get(u, u) for u in s.get("ever") or []] if len(s.get("ever") or []) > 1 else [])
		m = frappe.get_doc({"doctype": team.MSG, "channel_id": room, "message_type": "System", "text": team_rules.text_to_html(text)})
		m.flags.send_silently = True
		m.insert(ignore_permissions=True)
		if s.get("started_by"):
			frappe.db.set_value(team.MSG, m.name, "owner", s["started_by"], update_modified=False)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="Team calls: summary not saved")
	_tell(room, {"kind": "ended"})
