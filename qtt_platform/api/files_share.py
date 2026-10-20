"""
Office Pulse Files — sharing and file control inside the app (PROJ-0016 A; files_core.py does the checks):

  share / shares / unshare      a file or folder for people in the business: view or edit → their "Shared with me"
  ask / requests / decide       someone without access asks; someone who may share it approves (→ a share) or declines;
                                share-link guests waiting for approval are decided here too
  versions / restore_version / version_file   a file's older versions (30 days)
  bin / restore / purge_item    the recycle bin (30 days)
  lock / tag / comments / comment              work on a file together
  activity / audit              a file's or folder's activity; the business's file audit log (owners and admins)
  folder_rules / set_rule / delete_rule        who may read, write, create, delete or share in a folder
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from qtt_platform import file_store as store
from qtt_platform import files_core as core
from qtt_platform import files_rules as fr
from qtt_platform.api import team
from qtt_platform.api.workplace import _at, _ctx, _space_of

REQUEST, GUEST, LINK, COMMENT = "QTT File Request", "QTT Share Link Guest", "QTT Share Link", "QTT File Comment"


def _title(key: str) -> str:
	return key.rstrip("/").rsplit("/", 1)[-1]


def _push(users: list[str], title: str, body: str, data: dict) -> None:
	try:
		from qtt_platform.push import notify

		notify([u for u in users if u], title=title, body=body, data={"type": "files", **data})
	except Exception:
		frappe.log_error(title="Files: notification not sent")


def _pulse_people(ctx) -> dict[str, dict]:
	"""People in the business who have Files (Office Pulse)."""
	from qtt_platform.api.team_calls import can_screen_share

	return {u: p for u, p in team._people(ctx.tenant).items() if can_screen_share(ctx.tenant, u)}


# ---- shared with me ----------------------------------------------------------------------------------------------------
def shared_root(ctx) -> dict:
	"""The "Shared with me" space's first page: everything shared with this person."""
	rows = frappe.get_all(core.SHARE, filters={"tenant": ctx.tenant, "user": ctx.user}, fields=["name", "file_key", "is_dir", "permission", "shared_by", "creation"],
						  order_by="creation desc")
	names = team._names(ctx)
	items = []
	for r in rows:
		h = None if r.is_dir else store.head(r.file_key)
		if not r.is_dir and not h:
			continue
		from qtt_platform import workplace_rules as rules

		name = _title(r.file_key)
		items.append({"name": name, "path": r.name, "is_dir": bool(r.is_dir), "size": int((h or {}).get("ContentLength") or 0),
					  "size_text": "" if r.is_dir else rules.human_size(int((h or {}).get("ContentLength") or 0)),
					  "modified": str(r.creation)[:19], "type": rules.kind_of_file(name, bool(r.is_dir)), "editable": not r.is_dir and rules.editable(name),
					  "permission": r.permission, "shared_by": names.get(r.shared_by, r.shared_by), "tags": [], "locked_by": None, "shared": True})
	items.sort(key=lambda i: (not i["is_dir"], i["name"].lower()))
	return {"items": items, "path": "", "write": False, "rights": ["read"], "used": 0, "free": None}


# ---- sharing with people -----------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def share(space: str, path: str, users, permission: str = "view") -> dict:
	"""Share a file or folder with people in the business (view or edit). users: a list (or JSON list) of logins."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "share")
	if permission not in fr.SHARE_PERMS:
		frappe.throw(_("Choose View or Edit."))
	if permission == "edit" and "write" not in at.rights:
		frappe.throw(_("You can only share this to view — you can't change it yourself."))
	users = frappe.parse_json(users) if isinstance(users, str) else (users or [])
	people = _pulse_people(ctx)
	is_dir = not store.head(at.key) and store.exists_dir(at.key)
	if not is_dir and not store.head(at.key):
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	done = []
	for u in users:
		if u not in people or u == ctx.user:
			continue
		have = frappe.db.get_value(core.SHARE, {"tenant": ctx.tenant, "user": u, "file_key": at.key.rstrip("/")}, "name")
		if have:
			frappe.db.set_value(core.SHARE, have, "permission", permission)
		else:
			frappe.get_doc({"doctype": core.SHARE, "tenant": ctx.tenant, "space": _space_of(at), "path": at.path, "file_key": at.key.rstrip("/"),
							"is_dir": 1 if is_dir else 0, "user": u, "permission": permission, "shared_by": ctx.user}).insert(ignore_permissions=True)
		done.append(u)
		core.log(ctx.tenant, at.key, _space_of(at), at.path, "share", ctx.user, detail=f"{u}: {permission}")
	if not done:
		frappe.throw(_("Choose people in your business who have Office Pulse."))
	me = team._names(ctx).get(ctx.user, ctx.user)
	_push(done, _("{0} shared {1}").format(me, _title(at.key)), _("Open it in Files › Shared with me."), {"space": "shared"})
	return shares(space, path)


@frappe.whitelist(methods=["GET"])
def shares(space: str, path: str) -> dict:
	"""Who has this (people and links)."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	names = team._names(ctx)
	people = [{"name": r.name, "user": r.user, "title": names.get(r.user, r.user), "permission": r.permission, "by": names.get(r.shared_by, r.shared_by)}
			  for r in frappe.get_all(core.SHARE, filters={"tenant": ctx.tenant, "file_key": at.key.rstrip("/")}, fields=["name", "user", "permission", "shared_by"])]
	from qtt_platform.api import files_links

	return {"people": people, "links": files_links.links_of(ctx, at), "can_share": "share" in at.rights, "can_edit": "write" in at.rights,
			"choices": [{"user": u, "title": p["name"]} for u, p in sorted(_pulse_people(ctx).items(), key=lambda x: x[1]["name"]) if u != ctx.user]}


@frappe.whitelist(methods=["POST"])
def unshare(name: str) -> dict:
	"""Stop sharing with a person (anyone who may share the item, or the person themselves)."""
	ctx = _ctx()
	s = frappe.db.get_value(core.SHARE, {"name": name, "tenant": ctx.tenant}, ["name", "space", "path", "file_key", "user"], as_dict=True)
	if not s:
		return {"ok": True}
	if s.user != ctx.user:
		core.need(_at(ctx, s.space, s.path), "share")
	frappe.delete_doc(core.SHARE, s.name, ignore_permissions=True, force=True)
	core.log(ctx.tenant, s.file_key, s.space, s.path, "unshare", ctx.user, detail=s.user)
	return {"ok": True}


# ---- asking for access -------------------------------------------------------------------------------------------------
def _approvers(ctx, space: str) -> list[str]:
	people = team._people(ctx.tenant)
	out = [u for u, p in people.items() if p["role"] in team.GOVERNANCE]
	if space in ("hr", "company"):
		from qtt_platform.api.workplace import HR_ROLES

		pulse = frappe.get_all("QTT Product Access", filters={"tenant": ctx.tenant, "product": "QTT_OFFICE_PULSE", "status": "active",
															  "product_role": ["in", list(HR_ROLES)]}, fields=["membership"])
		ms = frappe.get_all("QTT Tenant Membership", filters={"name": ["in", [p.membership for p in pulse] or [""]]}, pluck="user")
		out += ms
	return sorted(set(out) - {ctx.user})


@frappe.whitelist(methods=["POST"])
def ask(space: str, path: str, permission: str = "view", note: str = "") -> dict:
	"""Ask for access to a file or folder you can't open (or can only view). Owners, admins (and HR for HR / Company)
	are told; any of them — or anyone who may share it — approves or declines."""
	ctx = _ctx()
	if space not in ("team", "company", "hr"):
		frappe.throw(_("Ask the person who has it to share it with you."))
	from qtt_platform import workplace_rules as rules

	key = rules.object_key(rules.space_prefix(ctx.tenant, space), path)
	if permission not in fr.SHARE_PERMS:
		permission = "view"
	if frappe.db.exists(REQUEST, {"tenant": ctx.tenant, "file_key": key, "requested_by": ctx.user, "status": "Pending"}):
		return {"ok": True, "already": True}
	is_dir = not store.head(key) and store.exists_dir(key)
	frappe.get_doc({"doctype": REQUEST, "tenant": ctx.tenant, "space": space, "path": rules.clean_path(path), "file_key": key, "is_dir": 1 if is_dir else 0,
					"requested_by": ctx.user, "permission": permission, "note": (note or "")[:500]}).insert(ignore_permissions=True)
	core.log(ctx.tenant, key, space, path, "ask", ctx.user, detail=permission)
	me = team._names(ctx).get(ctx.user, ctx.user)
	_push(_approvers(ctx, space), _("{0} asks for access").format(me), _("{0} — open Files › Requests to approve or decline.").format(_title(key)),
		  {"open": "requests"})
	return {"ok": True}


def _can_decide_file(ctx, r) -> bool:
	try:
		return "share" in _at(ctx, r.space, r.path).rights
	except frappe.PermissionError:
		return False


def _guest_rows(ctx) -> list:
	links = frappe.get_all(LINK, filters={"tenant": ctx.tenant, "require_approval": 1, "status": "Active"}, fields=["name", "space", "path", "file_key", "created_by"])
	mine = [l for l in links if l.created_by == ctx.user or ctx.admin]
	if not mine:
		return []
	by = {l.name: l for l in mine}
	return [(g, by[g.link]) for g in frappe.get_all(GUEST, filters={"link": ["in", list(by)], "status": "Pending"},
													fields=["name", "link", "email", "guest_name", "note", "creation"])]


def waiting_count(ctx) -> int:
	try:
		files = [r for r in frappe.get_all(REQUEST, filters={"tenant": ctx.tenant, "status": "Pending"}, fields=["space", "path", "requested_by"])
				 if r.requested_by != ctx.user and _can_decide_file(ctx, r)]
		return len(files) + len(_guest_rows(ctx))
	except Exception:
		return 0


@frappe.whitelist(methods=["GET"])
def requests() -> dict:
	"""Requests waiting for this person: people in the business asking for files, guests asking to open a link."""
	ctx = _ctx()
	names = team._names(ctx)
	out = []
	for r in frappe.get_all(REQUEST, filters={"tenant": ctx.tenant, "status": "Pending"},
							fields=["name", "space", "path", "file_key", "requested_by", "permission", "note", "creation"], order_by="creation desc"):
		if r.requested_by != ctx.user and _can_decide_file(ctx, r):
			out.append({"kind": "file", "name": r.name, "who": names.get(r.requested_by, r.requested_by), "what": _title(r.file_key),
						"space": r.space, "path": r.path, "permission": r.permission, "note": r.note, "when": str(r.creation)[:16]})
	for g, link in _guest_rows(ctx):
		out.append({"kind": "guest", "name": g.name, "who": f"{g.guest_name or ''} <{g.email}>".strip(), "what": _title(link.file_key),
					"space": link.space, "path": link.path, "permission": "link", "note": g.note, "when": str(g.creation)[:16]})
	mine = [{"name": r.name, "what": _title(r.file_key), "status": r.status, "when": str(r.modified)[:16]}
			for r in frappe.get_all(REQUEST, filters={"tenant": ctx.tenant, "requested_by": ctx.user}, fields=["name", "file_key", "status", "modified"],
									order_by="modified desc", limit=20)]
	return {"waiting": out, "mine": mine}


@frappe.whitelist(methods=["POST"])
def decide(name: str, approve: int = 1, kind: str = "file") -> dict:
	"""Approve or decline a request (kind "file": a person in the business — approving shares it with them; kind
	"guest": someone asking to open a share link — approving lets them in after they confirm their email)."""
	ctx = _ctx()
	yes = str(approve).lower() in ("1", "true", "yes")
	if kind == "guest":
		from qtt_platform.api import files_links

		return files_links.decide_guest(ctx, name, yes)
	r = frappe.get_doc(REQUEST, name)
	if r.tenant != ctx.tenant or r.status != "Pending":
		frappe.throw(_("That request isn't waiting any more."))
	if not _can_decide_file(ctx, r):
		frappe.throw(_("You can't share this."), frappe.PermissionError)
	r.status, r.decided_by = ("Approved" if yes else "Declined"), ctx.user
	r.save(ignore_permissions=True)
	if yes:
		if not frappe.db.exists(core.SHARE, {"tenant": ctx.tenant, "user": r.requested_by, "file_key": r.file_key}):
			frappe.get_doc({"doctype": core.SHARE, "tenant": ctx.tenant, "space": r.space, "path": r.path, "file_key": r.file_key, "is_dir": r.is_dir,
							"user": r.requested_by, "permission": r.permission, "shared_by": ctx.user}).insert(ignore_permissions=True)
	core.log(ctx.tenant, r.file_key, r.space, r.path, "approve" if yes else "decline", ctx.user, detail=r.requested_by)
	_push([r.requested_by], _("Access approved") if yes else _("Access declined"),
		  _("{0} is in Files › Shared with me.").format(_title(r.file_key)) if yes else _title(r.file_key), {"space": "shared"})
	return {"ok": True}


# ---- versions ----------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def versions(space: str, path: str) -> dict:
	"""A file's older versions (kept 30 days), newest first."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	from qtt_platform import workplace_rules as rules

	names = team._names(ctx)
	h = store.head(at.key) or {}
	rows = frappe.get_all(core.VERSION, filters={"tenant": ctx.tenant, "file_key": at.key}, fields=["name", "size", "by_user", "creation"], order_by="creation desc")
	return {"current": {"size_text": rules.human_size(int(h.get("ContentLength") or 0)), "modified": str(h.get("LastModified") or "")[:19]},
			"versions": [{"name": v.name, "size_text": rules.human_size(v.size or 0), "when": str(v.creation)[:16], "by": names.get(v.by_user, v.by_user or "")}
						 for v in rows], "can_restore": "write" in at.rights}


@frappe.whitelist(methods=["POST"])
def restore_version(space: str, path: str, version: str) -> dict:
	"""Make an older version the file again (what it is now is kept as a version too)."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "write")
	if frappe.db.get_value(core.VERSION, version, "file_key") != at.key:
		frappe.throw(_("That version isn't kept any more."), frappe.DoesNotExistError)
	core.restore_version(ctx.tenant, version, ctx.user)
	core.log(ctx.tenant, at.key, _space_of(at), at.path, "restore_version", ctx.user)
	return {"ok": True}


@frappe.whitelist(methods=["GET"])
def version_file(space: str, path: str, version: str):
	"""An older version's bytes (to look at or save)."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	v = frappe.db.get_value(core.VERSION, {"name": version, "tenant": ctx.tenant, "file_key": at.key}, "store_key")
	if not v:
		frappe.throw(_("That version isn't kept any more."), frappe.DoesNotExistError)
	frappe.local.response.filename = _title(at.key)
	frappe.local.response.filecontent = store.read(v)
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


# ---- the recycle bin ---------------------------------------------------------------------------------------------------
def _bin_visible(ctx, b) -> bool:
	from qtt_platform import workplace_rules as rules

	if b.space == "mine":
		return b.file_key.startswith(rules.space_prefix(ctx.tenant, "mine", ctx.user))
	try:
		parent = b.path.rsplit("/", 1)[0] if "/" in b.path else ""
		return "delete" in _at(ctx, b.space, parent).rights
	except frappe.PermissionError:
		return False


@frappe.whitelist(methods=["GET"])
def bin() -> dict:
	"""The recycle bin: what was deleted in the spaces this person may change (kept 30 days)."""
	ctx = _ctx()
	from qtt_platform import workplace_rules as rules

	names = team._names(ctx)
	rows = frappe.get_all(core.BIN, filters={"tenant": ctx.tenant}, fields=["name", "space", "path", "file_key", "is_dir", "size", "files", "deleted_by", "creation"],
						  order_by="creation desc", limit=500)
	items = [{"name": b.name, "title": _title(b.file_key), "space": b.space, "path": b.path, "is_dir": bool(b.is_dir), "files": b.files,
			  "size_text": rules.human_size(b.size or 0), "when": str(b.creation)[:16], "by": names.get(b.deleted_by, b.deleted_by or ""),
			  "days_left": max(0, fr.KEEP_DAYS - (now_datetime() - get_datetime(b.creation)).days), "type": rules.kind_of_file(_title(b.file_key), bool(b.is_dir))}
			 for b in rows if _bin_visible(ctx, b)]
	return {"items": items}


def _bin_row(ctx, name: str):
	b = frappe.db.get_value(core.BIN, {"name": name, "tenant": ctx.tenant}, ["name", "space", "path", "file_key", "is_dir"], as_dict=True)
	if not b or not _bin_visible(ctx, b):
		frappe.throw(_("That isn't in the recycle bin any more."), frappe.DoesNotExistError)
	return b


@frappe.whitelist(methods=["POST"])
def restore(name: str) -> dict:
	"""Put a deleted file or folder back where it was."""
	ctx = _ctx()
	b = _bin_row(ctx, name)
	r = core.restore_bin(ctx.tenant, b.name)
	core.log(ctx.tenant, r.key, b.space, b.path, "restore", ctx.user)
	return {"space": r.space, "path": b.path}


@frappe.whitelist(methods=["POST"])
def purge_item(name: str) -> dict:
	"""Delete a recycle-bin item for good (it can't be brought back)."""
	ctx = _ctx()
	b = _bin_row(ctx, name)
	core.drop_bin(ctx.tenant, b.name)
	core.log(ctx.tenant, b.file_key, b.space, b.path, "purge", ctx.user)
	return {"ok": True}


# ---- working together --------------------------------------------------------------------------------------------------
def _meta(ctx, key: str):
	name = frappe.db.get_value(core.META, {"tenant": ctx.tenant, "file_key": key})
	return frappe.get_doc(core.META, name) if name else frappe.get_doc({"doctype": core.META, "tenant": ctx.tenant, "file_key": key})


@frappe.whitelist(methods=["POST"])
def lock(space: str, path: str, on: int = 1) -> dict:
	"""Lock a file while you work on it (others can open it, not change it) — for 24 hours or until you unlock it.
	Owners and admins can unlock anyone's lock."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	m = _meta(ctx, at.key)
	now = now_datetime()
	held = m.locked_by and (not m.locked_until or get_datetime(m.locked_until) > now)
	if str(on).lower() in ("1", "true"):
		if "write" not in at.rights:
			frappe.throw(_("You can't change this file."), frappe.PermissionError)
		if held and m.locked_by != ctx.user:
			frappe.throw(_("{0} has locked it.").format(team._names(ctx).get(m.locked_by, m.locked_by)))
		m.locked_by, m.locked_until = ctx.user, add_to_date(now, hours=fr.LOCK_HOURS)
		action = "lock"
	else:
		if held and m.locked_by != ctx.user and not ctx.admin:
			frappe.throw(_("Only {0} or an admin can unlock it.").format(team._names(ctx).get(m.locked_by, m.locked_by)), frappe.PermissionError)
		m.locked_by, m.locked_until = None, None
		action = "unlock"
	m.save(ignore_permissions=True)
	core.log(ctx.tenant, at.key, _space_of(at), at.path, action, ctx.user)
	return {"locked_by": m.locked_by, "locked_until": str(m.locked_until or "")}


@frappe.whitelist(methods=["POST"])
def tag(space: str, path: str, tags) -> dict:
	"""Set a file's or folder's tags (a list or comma-separated)."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "write")
	items = frappe.parse_json(tags) if isinstance(tags, str) and tags.strip().startswith("[") else str(tags or "").split(",")
	clean = sorted({t.strip()[:30] for t in items if str(t).strip()})[:12]
	m = _meta(ctx, at.key.rstrip("/"))
	m.tags = ",".join(clean)
	m.save(ignore_permissions=True)
	core.log(ctx.tenant, at.key, _space_of(at), at.path, "tag", ctx.user, detail=m.tags)
	return {"tags": clean}


@frappe.whitelist(methods=["GET"])
def tags_in_use() -> list[str]:
	"""The business's tags (for suggestions)."""
	ctx = _ctx()
	out = set()
	for t in frappe.get_all(core.META, filters={"tenant": ctx.tenant, "tags": ["is", "set"]}, pluck="tags", limit=2000):
		out.update(x for x in (t or "").split(",") if x)
	return sorted(out)


@frappe.whitelist(methods=["GET"])
def comments(space: str, path: str) -> dict:
	"""A file's comments, oldest first."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	names = team._names(ctx)
	rows = frappe.get_all(COMMENT, filters={"tenant": ctx.tenant, "file_key": at.key.rstrip("/")}, fields=["name", "user", "text", "creation"], order_by="creation asc")
	return {"comments": [{"name": c.name, "by": names.get(c.user, c.user), "mine": c.user == ctx.user, "text": c.text, "when": str(c.creation)[:16]} for c in rows]}


@frappe.whitelist(methods=["POST"])
def comment(space: str, path: str, text: str) -> dict:
	"""Comment on a file; the people it's shared with and earlier commenters are told."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	text = str(text or "").strip()[:2000]
	if not text:
		frappe.throw(_("Write a comment."))
	key = at.key.rstrip("/")
	frappe.get_doc({"doctype": COMMENT, "tenant": ctx.tenant, "file_key": key, "user": ctx.user, "text": text}).insert(ignore_permissions=True)
	core.log(ctx.tenant, key, _space_of(at), at.path, "comment", ctx.user)
	others = set(frappe.get_all(COMMENT, filters={"tenant": ctx.tenant, "file_key": key}, pluck="user")) | set(
		frappe.get_all(core.SHARE, filters={"tenant": ctx.tenant, "file_key": key}, pluck="user"))
	me = team._names(ctx).get(ctx.user, ctx.user)
	_push(sorted(others - {ctx.user}), _("{0} commented on {1}").format(me, _title(key)), text[:120], {"space": _space_of(at), "path": at.path})
	return comments(space, path)


# ---- activity and audit ------------------------------------------------------------------------------------------------
_WORDS = {"upload": "uploaded", "replace": "uploaded a new version of", "create": "made", "rename": "renamed", "delete": "deleted",
		  "restore": "restored", "restore_version": "restored an older version of", "purge": "deleted for good", "download": "downloaded",
		  "open": "opened", "edit": "edited", "share": "shared", "unshare": "stopped sharing", "ask": "asked for access to",
		  "approve": "approved access to", "decline": "declined access to", "lock": "locked", "unlock": "unlocked", "tag": "tagged",
		  "comment": "commented on", "send_to_chat": "sent to a chat", "link_create": "made a link to", "link_revoke": "stopped a link to",
		  "link_rotate": "changed the key of a link to", "link_view": "opened (link)", "link_download": "downloaded (link)",
		  "link_upload": "uploaded (link) to", "rule": "changed who may use"}


def _activity_out(ctx, rows) -> list[dict]:
	names = team._names(ctx)
	return [{"who": names.get(a.actor, a.actor), "what": _WORDS.get(a.action, a.action), "action": a.action, "item": _title(a.file_key or a.path or ""),
			 "path": a.path, "space": a.space, "detail": a.detail, "when": str(a.creation)[:16], "ip": a.ip if ctx.admin else None} for a in rows]


@frappe.whitelist(methods=["GET"])
def activity(space: str, path: str = "", limit: int = 50) -> dict:
	"""What happened to a file, or in a folder (and everything in it), newest first."""
	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "read")
	base = (at.key if at.path else at.prefix).rstrip("/")
	from qtt_platform.files_core import _like

	rows = frappe.db.sql("""select actor, action, file_key, path, space, detail, creation, ip from `tabQTT File Activity`
		where tenant = %s and (file_key = %s or file_key like %s) order by creation desc limit %s""",
						 (ctx.tenant, base, _like(base) + "/%", min(int(limit or 50), 200)), as_dict=True)
	return {"activity": _activity_out(ctx, rows)}


@frappe.whitelist(methods=["GET"])
def audit(who: str = "", action: str = "", days: int = 30, limit: int = 200) -> dict:
	"""The business's file audit log (owners and admins): who viewed, downloaded, changed, shared or deleted what — with
	the IP for link visits."""
	ctx = _ctx()
	if not ctx.admin:
		frappe.throw(_("The audit log is for owners and admins."), frappe.PermissionError)
	f = {"tenant": ctx.tenant, "creation": [">=", add_to_date(now_datetime(), days=-min(int(days or 30), 365))]}
	if who:
		f["actor"] = who
	if action:
		f["action"] = action
	rows = frappe.get_all(core.ACTIVITY, filters=f, fields=["actor", "action", "file_key", "path", "space", "detail", "creation", "ip"],
						  order_by="creation desc", limit=min(int(limit or 200), 1000))
	return {"activity": _activity_out(ctx, rows), "actions": sorted(_WORDS)}


# ---- folder permissions ------------------------------------------------------------------------------------------------
def _rules_admin(ctx, space: str) -> None:
	if not (ctx.admin or (space in ("company", "hr") and ctx.hr)):
		frappe.throw(_("Owners and admins set who may use a folder (HR for Company and HR)."), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def folder_rules(space: str, path: str = "") -> dict:
	"""Who may do what in this folder (its own rules and the ones it inherits from folders above)."""
	ctx = _ctx()
	_rules_admin(ctx, space)
	from qtt_platform import workplace_rules as rules

	path = rules.clean_path(path)
	names = team._names(ctx)
	out = [{"name": r.name, "path": r.path or "", "who_type": r.who_type, "who": r.who,
			"who_title": _("Everyone") if r.who_type == "everyone" else names.get(r.who, r.who), "rights": sorted(fr.parse_rights(r.rights)),
			"inherited": (r.path or "") != path}
		   for r in core.folder_rules(ctx.tenant, space) if not r.path or path == r.path or path.startswith(r.path + "/")]
	roles = sorted({p["role"] for p in team._people(ctx.tenant).values() if p.get("role")} | {"HR", "HR Admin", "Employee"})
	return {"rules": out, "rights": list(fr.RIGHTS), "roles": roles,
			"people": [{"user": u, "title": p["name"]} for u, p in sorted(_pulse_people(ctx).items(), key=lambda x: x[1]["name"])]}


@frappe.whitelist(methods=["POST"])
def set_rule(space: str, path: str, who_type: str, who: str = "", rights="") -> dict:
	"""Set who may do what in a folder and everything in it: everyone / a role / a person → read, write, create, delete,
	share (none = no access). Owners and admins always keep full access."""
	ctx = _ctx()
	_rules_admin(ctx, space)
	if space not in ("team", "company", "hr") or who_type not in ("everyone", "role", "user"):
		frappe.throw(_("Choose a folder in Team files, Company or HR, and who it's for."))
	from qtt_platform import workplace_rules as rules

	path = rules.clean_path(path)
	r_list = frappe.parse_json(rights) if isinstance(rights, str) and rights.strip().startswith("[") else str(rights or "").split(",")
	allowed = fr.parse_rights(",".join(r_list))
	if allowed and "read" not in allowed:
		allowed = allowed | {"read"}
	who = "" if who_type == "everyone" else str(who or "")
	have = frappe.db.get_value(core.RULE, {"tenant": ctx.tenant, "space": space, "path": path, "who_type": who_type, "who": who})
	doc = frappe.get_doc(core.RULE, have) if have else frappe.get_doc({"doctype": core.RULE, "tenant": ctx.tenant, "space": space, "path": path,
																	   "who_type": who_type, "who": who})
	doc.rights = ",".join(r for r in fr.RIGHTS if r in allowed)
	doc.save(ignore_permissions=True)
	core.forget_rules(ctx.tenant, space)
	core.log(ctx.tenant, rules.object_key(rules.space_prefix(ctx.tenant, space), path), space, path, "rule", ctx.user,
			 detail=f"{who_type} {who}: {doc.rights or 'no access'}")
	return folder_rules(space, path)


@frappe.whitelist(methods=["POST"])
def delete_rule(name: str) -> dict:
	"""Remove a folder rule (the folder goes back to what it inherits)."""
	ctx = _ctx()
	r = frappe.db.get_value(core.RULE, {"name": name, "tenant": ctx.tenant}, ["name", "space", "path"], as_dict=True)
	if not r:
		return {"ok": True}
	_rules_admin(ctx, r.space)
	frappe.delete_doc(core.RULE, r.name, ignore_permissions=True, force=True)
	core.forget_rules(ctx.tenant, r.space)
	core.log(ctx.tenant, "", r.space, r.path, "rule", ctx.user, detail="removed")
	return folder_rules(r.space, r.path)
