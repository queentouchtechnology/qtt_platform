"""
Office Pulse Workplace (PROJ-0015) — files, documents and remote control for people with Office Pulse. QTT's own
servers (QTT Workplace Settings): S3 storage (Garage, files), OnlyOffice (documents), RustDesk (remote control).

Files live in one private bucket that only Frappe reaches (file_store.py); Frappe decides who may see and change
what. Each business's spaces:
  team     Team files — everyone in the business reads and writes (quota: Team files per business)
  mine     the person's own files in this business (quota: My files per person)
  company  Company — policies, forms: everyone reads; owners, admins and HR write
  hr       HR — owners, admins and HR only; People/<name>/ holds each employee's documents
  mydocs   an employee's own folder from HR (People/<their name>), read-only
A deleted or replaced file stays in the trash for 30 days.

  info          what this person has: spaces, quotas, remote control settings, whether they can manage computers
  list          a folder of a space (folders first) and the space's use
  download      a file (preview, save)
  upload        a file into a folder (multipart `file`, up to 100 MB)
  mkdir         a new folder
  new_doc       a new Word / Excel / PowerPoint file (blank) — then open it
  rename        rename a file or folder
  delete        delete a file or folder (kept in the trash for 30 days)
  open          edit a document in OnlyOffice (with everyone else who has it open): a link for the app's browser view
  send_to_chat  put a copy of a file into a Team chat
  employee_docs HR: an employee's document folder (made the first time)

Remote control (RustDesk, the standard app set to QTT's server):
  remote        server settings (the import string, host, key, download link)
  devices       Company computers (everyone sees the ones they use; owners / admins / HR Admins all of them)
  save_device / delete_device   owners / admins / HR Admins
  connect       open a computer in RustDesk (with its permanent password for owners / admins / HR Admins)
  help_request  "I need remote help" in a chat, with this computer's RustDesk ID (and a one-time password if given)
"""

import mimetypes
import os
import time

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from qtt_platform import file_store as store
from qtt_platform import workplace_rules as rules
from qtt_platform.api import team

SETTINGS = "QTT Workplace Settings"
HR_FOLDER = "QTT HR Folder"
DEVICE = "QTT Remote Device"
HR_ROLES = ("HR", "HR Admin")
MAX_UPLOAD = 100 * 1024 * 1024
TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workplace_templates")


# ---- who and where ------------------------------------------------------------------------------------------------------
def _ctx() -> frappe._dict:
	"""Team's checks + Office Pulse (the Workplace comes with it) + the person's Pulse role."""
	from qtt_platform.api.team_calls import can_screen_share

	ctx = team._ctx()  # (also asks Frappe to save this request's writes, GET included)
	if not can_screen_share(ctx.tenant, ctx.user):
		frappe.throw(_("Files, documents and remote control come with Office Pulse — ask your business owner."), frappe.PermissionError)
	m = frappe.db.get_value("QTT Tenant Membership", {"user": ctx.user, "tenant": ctx.tenant}, "name")
	ctx.pulse_role = frappe.db.get_value("QTT Product Access", {"membership": m, "product": rules.PULSE}, "product_role")
	ctx.hr = ctx.admin or ctx.pulse_role in HR_ROLES
	ctx.manager = rules.can_manage_devices(ctx.role, ctx.pulse_role)
	return ctx


def _settings():
	return frappe.get_cached_doc(SETTINGS)


def _prefix(ctx, space: str) -> str:
	"""Where a space starts in the store, for this person ("" for "My documents from HR" before HR made one)."""
	if space == "hr" and not ctx.hr:
		frappe.throw(_("HR's folder is for owners, admins and HR."), frappe.PermissionError)
	if space not in rules.SPACES:
		frappe.throw(_("Choose Team files, My files or Company."))
	folder = frappe.db.get_value(HR_FOLDER, {"tenant": ctx.tenant, "user": ctx.user}, "folder") if space == "mydocs" else ""
	return rules.space_prefix(ctx.tenant, space, ctx.user, folder or "")


def _can_write(ctx, key: str) -> bool:
	return key in ("team", "mine") or (key in ("company", "hr") and ctx.hr)


def _quota_gb(space: str) -> int | None:
	s = _settings()
	return (cint(s.team_quota_gb) or 10) if space == "team" else (cint(s.personal_quota_gb) or 2) if space == "mine" else None


def _need_write(ctx, space: str) -> str:
	if not _can_write(ctx, space):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	prefix = _prefix(ctx, space)
	if not prefix:
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	return prefix


def _file_key(ctx, space: str, path: str) -> str:
	prefix = _prefix(ctx, space)
	if not prefix or not rules.clean_path(path):
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	return rules.object_key(prefix, path)


# ---- endpoints: files ---------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def info() -> dict:
	"""What this person has in the Workplace: the spaces, whether they can write in each, remote control."""
	ctx = _ctx()
	s = _settings()
	spaces = [{"key": "team", "title": "Team files", "write": True}, {"key": "mine", "title": "My files", "write": True},
			  {"key": "company", "title": "Company", "write": ctx.hr}]
	if ctx.hr:
		spaces.append({"key": "hr", "title": "HR", "write": True})
	spaces.append({"key": "mydocs", "title": "My documents from HR", "write": False})
	return {"files": bool(s.files_enabled), "spaces": spaces, "hr": ctx.hr, "manager": ctx.manager, "remote": bool(s.remote_enabled),
			"onlyoffice": bool(s.onlyoffice_url)}


@frappe.whitelist(methods=["GET"])
def list_folder(space: str = "team", path: str = "") -> dict:
	"""A folder in a space: folders first, then files; how full the space is."""
	ctx = _ctx()
	prefix = _prefix(ctx, space)
	if not prefix:
		return {"items": [], "path": "", "write": False, "used": 0, "free": None, "empty_reason": "none"}
	folder = rules.clean_path(path)
	items = store.list_folder(prefix + (folder + "/" if folder else ""))
	for i in items:
		i["size_text"] = "" if i["is_dir"] else rules.human_size(i["size"])
		i["editable"] = not i["is_dir"] and rules.editable(i["name"])
		i["path"] = "/".join(p for p in (folder, i["name"]) if p)
	used = store.used(prefix)
	return {"items": items, "path": folder, "write": _can_write(ctx, space), "used": used, "free": rules.free_bytes(used, _quota_gb(space))}


@frappe.whitelist(methods=["GET"])
def download(space: str, path: str):
	"""A file's bytes (to preview or save)."""
	ctx = _ctx()
	data = store.read(_file_key(ctx, space, path))
	frappe.local.response.filename = rules.clean_path(path).rsplit("/", 1)[-1]
	frappe.local.response.filecontent = data
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(methods=["POST"])
def upload(space: str = "team", path: str = "") -> dict:
	"""Multipart `file` into a folder (up to 100 MB). A file with the same name is replaced (the old one stays in the
	trash for 30 days)."""
	ctx = _ctx()
	prefix = _need_write(ctx, space)
	up = frappe.request.files.get("file") if frappe.request else None
	if not up:
		frappe.throw(_("Choose a file."))
	data = up.stream.read(MAX_UPLOAD + 1)
	if len(data) > MAX_UPLOAD:
		frappe.throw(_("A file can be up to 100 MB."))
	if not rules.fits(store.used(prefix), _quota_gb(space), len(data)):
		frappe.throw(_("This space is full — delete something, or ask QTT for more room."))
	name = rules.clean_name(up.filename or "file") or "file"
	store.write(rules.object_key(prefix, f"{path}/{name}"), data, up.mimetype or mimetypes.guess_type(name)[0])
	return {"name": name, "path": rules.clean_path(f"{path}/{name}")}


@frappe.whitelist(methods=["POST"])
def mkdir(space: str, path: str, name: str) -> dict:
	"""A new folder."""
	ctx = _ctx()
	prefix = _need_write(ctx, space)
	name = rules.clean_name(name)
	if not name:
		frappe.throw(_("Give the folder a name."))
	store.mkdir(rules.object_key(prefix, f"{path}/{name}"))
	return {"name": name}


@frappe.whitelist(methods=["POST"])
def new_doc(space: str, path: str = "", kind: str = "word", title: str | None = None) -> dict:
	"""A new blank Word / Excel / PowerPoint file in a folder. {name, path} — then open it."""
	ctx = _ctx()
	prefix = _need_write(ctx, space)
	try:
		name = rules.new_doc_name(kind, title)
	except ValueError:
		frappe.throw(_("Choose a document, a sheet or a presentation."))
	if store.head(rules.object_key(prefix, f"{path}/{name}")):
		stem, e = name.rsplit(".", 1)
		name = f"{stem} {time.strftime('%d-%m %H%M')}.{e}"
	with open(os.path.join(TEMPLATES, f"new.{rules.NEW_DOCS[kind]}"), "rb") as f:
		store.write(rules.object_key(prefix, f"{path}/{name}"), f.read(), mimetypes.guess_type(name)[0])
	return {"name": name, "path": rules.clean_path(f"{path}/{name}")}


@frappe.whitelist(methods=["POST"])
def rename(space: str, path: str, name: str) -> dict:
	"""Rename a file or folder (in the same folder)."""
	ctx = _ctx()
	prefix = _need_write(ctx, space)
	new = rules.clean_name(name)
	if not new or not rules.clean_path(path):
		frappe.throw(_("Give it a name."))
	old = rules.object_key(prefix, path)
	parent = rules.clean_path(path).rsplit("/", 1)[0] if "/" in rules.clean_path(path) else ""
	target = rules.object_key(prefix, f"{parent}/{new}")
	is_dir = not store.head(old)
	if is_dir and not store.exists_dir(old):
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	if store.head(target) or store.exists_dir(target):
		frappe.throw(_("Something with that name is already here."))
	store.move(old, target, is_dir)
	return {"name": new}


@frappe.whitelist(methods=["POST"])
def delete(space: str, path: str) -> dict:
	"""Delete a file or folder (it stays in the trash for 30 days)."""
	ctx = _ctx()
	prefix = _need_write(ctx, space)
	if not rules.clean_path(path):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	key = rules.object_key(prefix, path)
	store.delete(key, is_dir=not store.head(key))
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def open_doc(space: str, path: str) -> dict:
	"""Edit a document in OnlyOffice — with everyone else who has it open. {url}: a link to the editor page (it works
	for a few hours, for this person only)."""
	from qtt_platform.api import workplace_docs

	ctx = _ctx()
	key = _file_key(ctx, space, path)
	name = rules.clean_path(path).rsplit("/", 1)[-1]
	if not rules.editable(name):
		frappe.throw(_("This file opens as it is — download it."))
	h = store.head(key)
	if not h:
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	return {"url": workplace_docs.editor_link(ctx, key, name, str(h.get("ETag") or "").strip('"'), _can_write(ctx, space))}


@frappe.whitelist(methods=["POST"])
def send_to_chat(space: str, path: str, channel: str) -> dict:
	"""A copy of the file in a Team chat (everyone in the chat can open it; the original stays in Files)."""
	ctx = _ctx()
	team._channel(ctx, channel, need_member=True)
	key = _file_key(ctx, space, path)
	h = store.head(key)
	if not h:
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	if int(h.get("ContentLength") or 0) > team_rules_max():
		frappe.throw(_("A file can be up to 25 MB in a chat."))
	name = rules.clean_path(path).rsplit("/", 1)[-1]
	from qtt_platform import team_rules

	f = frappe.get_doc({"doctype": "File", "file_name": name, "content": store.read(key), "is_private": 1, "attached_to_doctype": team.CH,
						"attached_to_name": channel}).insert(ignore_permissions=True)
	m = team._post(ctx, channel, message_type=team_rules.kind_of(name), file_url=f.file_url)
	return {"message": m.name}


def team_rules_max() -> int:
	from qtt_platform import team_rules

	return team_rules.MAX_FILE


@frappe.whitelist(methods=["POST"])
def employee_docs(user: str) -> dict:
	"""HR: an employee's document folder (HR › People › <name>); the employee sees it, read-only, as "My documents
	from HR". {space: "hr", path}."""
	ctx = _ctx()
	if not ctx.hr:
		frappe.throw(_("HR's folder is for owners, admins and HR."), frappe.PermissionError)
	people = team._people(ctx.tenant)
	if user not in people:
		frappe.throw(_("Choose someone in your business."))
	have = frappe.db.get_value(HR_FOLDER, {"tenant": ctx.tenant, "user": user}, "folder")
	if have:
		return {"space": "hr", "path": have}
	name = rules.clean_name(people[user]["name"]) or rules.person_id(user)
	path = f"People/{name}"
	hr = rules.space_prefix(ctx.tenant, "hr")
	if store.exists_dir(rules.object_key(hr, path)) and frappe.db.exists(HR_FOLDER, {"tenant": ctx.tenant, "folder": path}):
		path = f"People/{name} {rules.person_id(user)[:4]}"  # two people with the same name
	store.mkdir(rules.object_key(hr, path))
	frappe.get_doc({"doctype": HR_FOLDER, "tenant": ctx.tenant, "user": user, "folder": path}).insert(ignore_permissions=True)
	return {"space": "hr", "path": path}


# ---- endpoints: remote control ---------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def remote() -> dict:
	"""QTT's RustDesk server for the RustDesk app: the string for "Import server config", the host and key (to type in
	by hand), where to get the app."""
	ctx = _ctx()
	s = _settings()
	if not s.remote_enabled or not s.rustdesk_host or not s.rustdesk_key:
		frappe.throw(_("Remote control isn't set up yet."))
	return {"host": s.rustdesk_host, "key": s.rustdesk_key, "config": rules.rustdesk_config(s.rustdesk_host, s.rustdesk_key),
			"download": "https://rustdesk.com/download", "manager": ctx.manager}


def _device_out(d, ctx, names) -> dict:
	return {"id": d.name, "title": d.title, "rustdesk_id": d.rustdesk_id, "assigned_to": d.assigned_to,
			"assigned_name": names.get(d.assigned_to, d.assigned_to) if d.assigned_to else None, "platform": d.platform or "",
			"notes": d.notes or "", "has_password": bool(d.password) if ctx.manager else False,
			"last_connected_at": str(d.last_connected_at) if d.last_connected_at else None,
			"managed": bool(d.get("managed")), "state": d.get("state") or "Active",
			"rotate_required": bool(d.get("rotate_required")) if ctx.manager else False,
			"rotate_reason": (d.get("rotate_reason") or "") if ctx.manager else "",
			"agent_seen_at": str(d.agent_seen_at) if d.get("agent_seen_at") else None,
			"password_set_at": str(d.password_set_at) if d.get("password_set_at") and ctx.manager else None}


@frappe.whitelist(methods=["GET"])
def devices(user: str | None = None) -> dict:
	"""Company computers: all of them for owners / admins / HR Admins, the ones you use for everyone else. user: only
	that person's (to control their computer from a call)."""
	ctx = _ctx()
	filters = {"tenant": ctx.tenant}
	if not ctx.manager:
		filters["assigned_to"] = ctx.user
	elif user:
		filters["assigned_to"] = user
	filters["state"] = ["!=", "Locked"]
	rows = frappe.get_all(DEVICE, filters=filters, fields=["name", "title", "rustdesk_id", "password", "assigned_to", "platform", "notes",
															 "last_connected_at", "managed", "state", "rotate_required", "rotate_reason",
															 "agent_seen_at", "password_set_at"], order_by="title asc")
	names = team._names(ctx)
	return {"devices": [_device_out(d, ctx, names) for d in rows], "manager": ctx.manager}


@frappe.whitelist(methods=["POST"])
def save_device(title: str, rustdesk_id: str, name: str | None = None, password: str | None = None, assigned_to: str | None = None,
				platform: str | None = None, notes: str | None = None) -> dict:
	"""Add or change a Company computer (owners, admins, HR Admins). password: its RustDesk permanent password (kept
	encrypted; empty leaves it as it is)."""
	ctx = _ctx()
	if not ctx.manager:
		frappe.throw(_("Owners, admins and HR Admins look after Company computers."), frappe.PermissionError)
	rid = rules.rustdesk_id(rustdesk_id)
	if not rid:
		frappe.throw(_("A RustDesk ID is 9 or 10 digits — it's on the RustDesk app's first screen."))
	if assigned_to and assigned_to not in team._people(ctx.tenant):
		frappe.throw(_("Choose someone in your business."))
	from qtt_platform.api import workplace_agent as agent

	before = None
	if name:
		d = frappe.get_doc(DEVICE, name)
		if d.tenant != ctx.tenant:
			frappe.throw(_("That computer isn't in this business."), frappe.PermissionError)
		before = d.assigned_to
	else:
		d = frappe.get_doc({"doctype": DEVICE, "tenant": ctx.tenant})
	if d.get("managed") and rid != d.rustdesk_id:
		rid = d.rustdesk_id  # the agent keeps the ID up to date
	d.update({"title": str(title or "").strip()[:80] or rid, "rustdesk_id": rid, "assigned_to": assigned_to or None,
			  "platform": platform or "", "notes": (notes or "").strip()[:500]})
	if password and not d.get("managed"):
		d.password = password  # with the agent, only QTT sets the password
		d.password_set_at = now_datetime()
		d.rotate_required = 0
		d.rotate_reason = None
	d.save(ignore_permissions=True)
	if name and before and before != (assigned_to or None):
		agent.ask_rotation(frappe.get_doc(DEVICE, d.name), f"given to someone else (was {team._names(ctx).get(before, before)})", ctx.user)
	return _device_out(frappe.get_doc(DEVICE, d.name), ctx, team._names(ctx))


@frappe.whitelist(methods=["POST"])
def setup_device(title: str = "New computer", assigned_to: str | None = None) -> dict:
	"""Add a computer the safe way (owners, admins, HR Admins): a one-use setup code (1 hour) and the command to run
	on it — Windows PowerShell as Administrator, or Mac / Linux with sudo. QTT then manages its RustDesk password."""
	from qtt_platform.api import workplace_agent as agent

	ctx = _ctx()
	if not ctx.manager:
		frappe.throw(_("Owners, admins and HR Admins look after Company computers."), frappe.PermissionError)
	if assigned_to and assigned_to not in team._people(ctx.tenant):
		frappe.throw(_("Choose someone in your business."))
	d = frappe.get_doc({"doctype": DEVICE, "tenant": ctx.tenant, "title": str(title or "").strip()[:80] or "New computer",
						"rustdesk_id": "000000000", "state": "Waiting for setup", "assigned_to": assigned_to or None}).insert(ignore_permissions=True)
	return {"device": d.name, **agent.setup_code(d)}


@frappe.whitelist(methods=["POST"])
def rotate_device(name: str) -> dict:
	"""Change a computer's password now (owners, admins, HR Admins): the agent does it within 15 minutes; a computer
	without the agent is flagged until its new password is saved."""
	from qtt_platform.api import workplace_agent as agent

	ctx = _ctx()
	d = frappe.get_doc(DEVICE, name)
	if not ctx.manager or d.tenant != ctx.tenant:
		frappe.throw(_("Owners, admins and HR Admins look after Company computers."), frappe.PermissionError)
	agent.ask_rotation(d, f"asked by {team._names(ctx).get(ctx.user, ctx.user)}", ctx.user)
	return _device_out(frappe.get_doc(DEVICE, name), ctx, team._names(ctx))


@frappe.whitelist(methods=["POST"])
def delete_device(name: str) -> dict:
	"""Take a computer off the list (owners, admins, HR Admins)."""
	from qtt_platform.api import workplace_agent as agent

	ctx = _ctx()
	if not ctx.manager or frappe.db.get_value(DEVICE, name, "tenant") != ctx.tenant:
		frappe.throw(_("Owners, admins and HR Admins look after Company computers."), frappe.PermissionError)
	agent.lock(frappe.get_doc(DEVICE, name), ctx.user)
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def connect(name: str | None = None, rustdesk_id: str | None = None) -> dict:
	"""Open a computer in the RustDesk app on this computer: a Company computer (with its permanent password for
	owners / admins / HR Admins), or any RustDesk ID someone gave you. {uri}."""
	ctx = _ctx()
	if name:
		from qtt_platform.api import workplace_agent as agent

		d = frappe.get_doc(DEVICE, name)
		if d.tenant != ctx.tenant or (not ctx.manager and d.assigned_to != ctx.user):
			frappe.throw(_("That computer isn't yours to open."), frappe.PermissionError)
		if d.get("state") in ("Waiting for setup", "Locking", "Locked"):
			frappe.throw(_("This computer isn't ready — finish its setup in Remote help."))
		pw = d.get_password("password", raise_exception=False) if ctx.manager else None
		frappe.db.set_value(DEVICE, d.name, {"last_connected_at": now_datetime(), "last_connected_by": ctx.user}, update_modified=False)
		agent.log(d, "Connect with saved password" if pw else "Connect", ctx.user)
		return {"uri": rules.rustdesk_uri(d.rustdesk_id, pw), "rustdesk_id": d.rustdesk_id}
	rid = rules.rustdesk_id(rustdesk_id)
	if not rid:
		frappe.throw(_("A RustDesk ID is 9 or 10 digits — it's on the RustDesk app's first screen."))
	return {"uri": rules.rustdesk_uri(rid), "rustdesk_id": rid}


@frappe.whitelist(methods=["POST"])
def help_request(channel: str, rustdesk_id: str, password: str | None = None) -> dict:
	"""Ask for remote help in a chat: a message with this computer's RustDesk ID (and its one-time password if given —
	it changes after each session) that the others can tap to connect."""
	ctx = _ctx()
	rid = rules.rustdesk_id(rustdesk_id)
	if not rid:
		frappe.throw(_("A RustDesk ID is 9 or 10 digits — it's on the RustDesk app's first screen."))
	spaced = " ".join(rid[i:i + 3] for i in range(0, len(rid), 3))
	text = f"🖥 I need remote help — RustDesk ID {spaced}" + (f"\nOne-time password: {password.strip()[:20]}" if password else "")
	m = team._post(ctx, channel, text=text)
	return {"message": m.name}


def drop(tenant: str, user: str) -> None:
	"""Someone left the business (or was suspended). Files need nothing here: every request checks membership and
	Office Pulse access, so they can't reach the business's files any more. Kept for team_events' call."""
	return None
