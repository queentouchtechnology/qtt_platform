"""
Office Pulse Workplace (PROJ-0015) — files, documents and remote control for people with Office Pulse. QTT's own
servers (QTT Workplace Settings): Nextcloud (files), OnlyOffice (documents), RustDesk (remote control).

Files: the app never shows Nextcloud — QTT makes each person a Nextcloud user ("qtt-…", their password kept here,
encrypted), each business a group and group folders, and reaches them over WebDAV as that person:
  team     "<Business> · Team files" — everyone in the business reads and writes (quota: Team files per business)
  mine     the person's own files (quota: My files per person)
  company  "<Business> · Company" — policies, forms: everyone reads; owners, admins and HR write
  hr       "<Business> · HR" — owners, admins and HR only; People/<name>/ holds each employee's documents
  mydocs   an employee's own folder from HR (People/<their name>), read-only, shared with them

  info          what this person has: spaces, quotas, remote control settings, whether they can manage computers
  list          a folder of a space (folders first) and the space's use
  download      a file (preview, save)
  upload        a file into a folder (multipart `file`, up to 100 MB)
  mkdir         a new folder
  new_doc       a new Word / Excel / PowerPoint file (blank) — then open it
  rename        rename a file or folder
  delete        delete a file or folder (Nextcloud keeps it in its trash for 30 days)
  open          edit a document in OnlyOffice (with everyone else who has it open): a link for the app's browser view
  send_to_chat  put a copy of a file into a Team chat
  employee_docs HR: an employee's document folder (made and shared with them the first time)

Remote control (RustDesk, the standard app set to QTT's server):
  remote        server settings (the import string, host, key, download link)
  devices       Company computers (everyone sees the ones they use; owners / admins / HR Admins all of them)
  save_device / delete_device   owners / admins / HR Admins
  connect       open a computer in RustDesk (with its permanent password for owners / admins / HR Admins)
  help_request  "I need remote help" in a chat, with this computer's RustDesk ID (and a one-time password if given)
"""

import os
import re
import secrets
import threading
import time
from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime

from qtt_platform import workplace_rules as rules
from qtt_platform.api import team

SETTINGS = "QTT Workplace Settings"
ACCOUNT = "QTT Cloud Account"
SPACE = "QTT Cloud Space"
DEVICE = "QTT Remote Device"
HR_ROLES = ("HR", "HR Admin")
MAX_UPLOAD = 100 * 1024 * 1024
TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workplace_templates")


# ---- who and the servers ------------------------------------------------------------------------------------------------
def _ctx() -> frappe._dict:
	"""Team's checks + Office Pulse (the Workplace comes with it) + the person's Pulse role."""
	from qtt_platform.api.team_calls import can_screen_share

	ctx = team._ctx()  # (also asks Frappe to save this request's writes, GET included: accounts, spaces)
	if not can_screen_share(ctx.tenant, ctx.user):
		frappe.throw(_("Files, documents and remote control come with Office Pulse — ask your business owner."), frappe.PermissionError)
	m = frappe.db.get_value("QTT Tenant Membership", {"user": ctx.user, "tenant": ctx.tenant}, "name")
	ctx.pulse_role = frappe.db.get_value("QTT Product Access", {"membership": m, "product": rules.PULSE}, "product_role")
	ctx.hr = ctx.admin or ctx.pulse_role in HR_ROLES
	ctx.manager = rules.can_manage_devices(ctx.role, ctx.pulse_role)
	return ctx


def _settings():
	return frappe.get_cached_doc(SETTINGS)


def _nc() -> tuple[str, tuple[str, str]]:
	s = _settings()
	pw = s.get_password("nextcloud_admin_password", raise_exception=False)
	if not s.files_enabled or not s.nextcloud_url or not pw:
		frappe.throw(_("Files aren't set up yet."))
	return s.nextcloud_url.rstrip("/"), (s.nextcloud_admin_user, pw)


def _ocs(method: str, path: str, auth, data=None, params=None, ok=(100, 200, 102)) -> dict:
	"""A Nextcloud OCS call; {} for "already there" style answers (code 102 / 400 where we expect them)."""
	base, _admin = _nc()
	url = f"{base}/ocs/v1.php/{path}" if path.startswith("cloud/") else f"{base}/{path}"
	r = requests.request(method, url, auth=auth, data=data, params={**(params or {}), "format": "json"},
						 headers={"OCS-APIRequest": "true", "Accept": "application/json"}, timeout=30)
	try:
		body = r.json()
	except ValueError:
		frappe.log_error(title="Workplace: Nextcloud answered oddly", message=f"{method} {path}: {r.status_code} {r.text[:500]}")
		frappe.throw(_("Files are having a problem right now. Please try again in a minute."))
	meta = (body.get("ocs") or {}).get("meta") or {}
	code = int(meta.get("statuscode") or r.status_code)
	if code not in ok:
		frappe.log_error(title="Workplace: Nextcloud refused", message=f"{method} {path}: {meta}")
		frappe.throw(_("Files are having a problem right now. Please try again in a minute."))
	return (body.get("ocs") or {}).get("data") or {}


_local = threading.local()


def _http() -> requests.Session:
	"""One kept-alive connection pool to Nextcloud per worker thread (no new TLS handshake per request)."""
	s = getattr(_local, "session", None)
	if s is None:
		s = _local.session = requests.Session()
	return s


def _app_password(cu: str, pw: str) -> str | None:
	"""A Nextcloud app password for this account: checked far faster than the login password on every request
	(~100 ms instead of ~500 ms), and revocable on its own."""
	base, _a = _nc()
	r = requests.get(f"{base}/ocs/v2.php/core/getapppassword", auth=(cu, pw), headers={"OCS-APIRequest": "true"},
					 params={"format": "json"}, timeout=30)
	try:
		return r.json()["ocs"]["data"]["apppassword"]
	except (ValueError, KeyError, TypeError):
		frappe.log_error(title="Workplace: no Nextcloud app password", message=f"{r.status_code} {r.text[:200]}")
		return None


def _account(user: str, name: str) -> tuple[str, str]:
	"""The person's Nextcloud user (made the first time) → (cloud user, app password — or the login password while
	there's none yet)."""
	_base, admin = _nc()
	if frappe.db.exists(ACCOUNT, user):
		doc = frappe.get_doc(ACCOUNT, user)
		token = doc.get_password("cloud_token", raise_exception=False)
		if token:
			return doc.cloud_user, token
		pw = doc.get_password("cloud_password")
		token = _app_password(doc.cloud_user, pw)
		if token:
			doc.cloud_token = token
			doc.save(ignore_permissions=True)
			return doc.cloud_user, token
		return doc.cloud_user, pw
	cu = rules.cloud_user(user)
	pw = secrets.token_urlsafe(24)
	s = _settings()
	_ocs("POST", "cloud/users", admin, data={"userid": cu, "password": pw, "displayName": name[:60]}, ok=(100, 200, 102))
	# an account that existed already (made before, its row lost): set a new password we know
	_ocs("PUT", f"cloud/users/{cu}", admin, data={"key": "password", "value": pw})
	_ocs("PUT", f"cloud/users/{cu}", admin, data={"key": "quota", "value": f"{cint(s.personal_quota_gb) or 2} GB"})
	token = _app_password(cu, pw)
	frappe.get_doc({"doctype": ACCOUNT, "user": user, "cloud_user": cu, "cloud_password": pw, "cloud_token": token}).insert(ignore_permissions=True)
	return cu, token or pw


def _groupfolder(admin, mount: str, groups: dict[str, int], quota_gb: int | None) -> int:
	base, _a = _nc()
	data = _ocs("POST", "index.php/apps/groupfolders/folders", admin, data={"mountpoint": mount})
	fid = int(data.get("id"))
	for g, perms in groups.items():
		_ocs("POST", f"index.php/apps/groupfolders/folders/{fid}/groups", admin, data={"group": g})
		_ocs("POST", f"index.php/apps/groupfolders/folders/{fid}/groups/{g}", admin, data={"permissions": perms})
	if quota_gb:
		_ocs("POST", f"index.php/apps/groupfolders/folders/{fid}/quota", admin, data={"quota": quota_gb * 1024 ** 3})
	return fid


def _space(ctx) -> frappe._dict:
	"""The business's groups and folders (made the first time), and this person in the right groups."""
	_base, admin = _nc()
	business = frappe.db.get_value("QTT Tenant", ctx.tenant, "tenant_name") or ctx.tenant
	everyone, hr = rules.cloud_group(ctx.tenant), rules.cloud_group(ctx.tenant, "hr")
	if not frappe.db.exists(SPACE, ctx.tenant):
		for g in (everyone, hr):
			_ocs("POST", "cloud/groups", admin, data={"groupid": g, "displayname": f"{business}{' · HR' if g == hr else ''}"}, ok=(100, 200, 102))
		_ocs("POST", f"cloud/users/{admin[0]}/groups", admin, data={"groupid": hr}, ok=(100, 200, 102))
		s = _settings()
		team_name, company_name = rules.folder_name(business, "team"), rules.folder_name(business, "company")
		hr_name = team_name.replace("Team files", "HR")
		frappe.get_doc({"doctype": SPACE, "tenant": ctx.tenant,
						"team_folder_id": _groupfolder(admin, team_name, {everyone: 31}, cint(s.team_quota_gb) or 10), "team_folder": team_name,
						"company_folder_id": _groupfolder(admin, company_name, {everyone: 1, hr: 31}, None), "company_folder": company_name,
						}).insert(ignore_permissions=True)
		_groupfolder(admin, hr_name, {hr: 31}, None)
		frappe.db.commit()  # the folders exist on Nextcloud now; keep the record even if the rest of this call fails
	space = frappe.get_doc(SPACE, ctx.tenant)
	space.hr_folder = space.team_folder.replace("Team files", "HR")
	cu, pw = _account(ctx.user, team._names(ctx).get(ctx.user, ctx.user))
	want = [everyone] + ([hr] if ctx.hr else [])
	key = f"qtt_cloud_groups|{ctx.user}|{ctx.tenant}|{','.join(want)}"
	if not frappe.cache().get_value(key):
		for g in want:
			_ocs("POST", f"cloud/users/{cu}/groups", admin, data={"groupid": g}, ok=(100, 200, 102))
		if not ctx.hr:
			_ocs("DELETE", f"cloud/users/{cu}/groups", admin, data={"groupid": hr}, ok=(100, 200, 102, 105))
		frappe.cache().set_value(key, 1, expires_in_sec=6 * 3600)
	space.cloud_user, space.cloud_password = cu, pw
	return space


def _root(ctx, space, key: str) -> str:
	"""Where a space starts in the person's files."""
	match key:
		case "team":
			return space.team_folder
		case "company":
			return space.company_folder
		case "hr":
			if not ctx.hr:
				frappe.throw(_("HR's folder is for owners, admins and HR."), frappe.PermissionError)
			return space.hr_folder
		case "mine":
			return ""
		case "mydocs":
			return _my_docs_mount(ctx, space)
	frappe.throw(_("Choose Team files, My files or Company."))


def _can_write(ctx, key: str) -> bool:
	return key in ("team", "mine") or (key in ("company", "hr") and ctx.hr)


def _dav(space, root: str, path: str = "") -> str:
	base, _a = _nc()
	full = "/".join(p for p in (root, rules.clean_path(path)) if p)
	return f"{base}/remote.php/dav/files/{space.cloud_user}/" + quote(full)


def _req(space, method: str, url: str, **kw) -> requests.Response:
	r = _http().request(method, url, auth=(space.cloud_user, space.cloud_password), timeout=kw.pop("timeout", 60), **kw)
	if r.status_code == 404:
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	if r.status_code == 507:
		frappe.throw(_("This space is full — delete something, or ask QTT for more room."))
	if r.status_code in (403, 401):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	if r.status_code >= 400 and r.status_code != 405:
		frappe.log_error(title="Workplace: WebDAV refused", message=f"{method} {url}: {r.status_code} {r.text[:300]}")
		frappe.throw(_("Files are having a problem right now. Please try again in a minute."))
	return r


PROPFIND = """<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop>
<d:getlastmodified/><d:getcontentlength/><d:resourcetype/><d:getetag/><oc:size/><oc:fileid/>
<d:quota-used-bytes/><d:quota-available-bytes/></d:prop></d:propfind>"""


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
	sp = _space(ctx)
	root = _root(ctx, sp, space)
	if space == "mydocs" and not root:
		return {"items": [], "path": "", "write": False, "used": 0, "free": None, "empty_reason": "none"}
	r = _req(sp, "PROPFIND", _dav(sp, root, path), data=PROPFIND, headers={"Depth": "1", "Content-Type": "application/xml"})
	base = f"/remote.php/dav/files/{sp.cloud_user}/" + "/".join(p for p in (root, rules.clean_path(path)) if p)
	items = rules.parse_propfind(r.text, base)
	if space == "mine":
		# the business folders and shares are their own spaces
		items = [i for i in items if not re.search(r" · (Team files|Company|HR)$", i["name"]) and i["name"] != "Shared"]
	used, free = _quota(r.text)
	for i in items:
		i["size_text"] = "" if i["is_dir"] else rules.human_size(i["size"])
		i["editable"] = not i["is_dir"] and rules.editable(i["name"])
		i["path"] = "/".join(p for p in (rules.clean_path(path), i["name"]) if p)
	return {"items": items, "path": rules.clean_path(path), "write": _can_write(ctx, space), "used": used, "free": free}


def _quota(xml: str) -> tuple[int, int | None]:
	m_used = re.search(r"<d:quota-used-bytes>(\d+)</d:quota-used-bytes>", xml)
	m_free = re.search(r"<d:quota-available-bytes>(-?\d+)</d:quota-available-bytes>", xml)
	free = int(m_free.group(1)) if m_free else None
	return int(m_used.group(1)) if m_used else 0, (free if free is not None and free >= 0 else None)


@frappe.whitelist(methods=["GET"])
def download(space: str, path: str):
	"""A file's bytes (to preview or save)."""
	ctx = _ctx()
	sp = _space(ctx)
	r = _req(sp, "GET", _dav(sp, _root(ctx, sp, space), path), timeout=120)
	frappe.local.response.filename = rules.clean_path(path).rsplit("/", 1)[-1]
	frappe.local.response.filecontent = r.content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(methods=["POST"])
def upload(space: str = "team", path: str = "") -> dict:
	"""Multipart `file` into a folder (up to 100 MB). A file with the same name is replaced (Nextcloud keeps the old
	version)."""
	ctx = _ctx()
	if not _can_write(ctx, space):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	sp = _space(ctx)
	up = frappe.request.files.get("file") if frappe.request else None
	if not up:
		frappe.throw(_("Choose a file."))
	data = up.stream.read(MAX_UPLOAD + 1)
	if len(data) > MAX_UPLOAD:
		frappe.throw(_("A file can be up to 100 MB."))
	name = rules.clean_name(up.filename or "file")
	_req(sp, "PUT", _dav(sp, _root(ctx, sp, space), f"{path}/{name}"), data=data, timeout=300)
	return {"name": name, "path": rules.clean_path(f"{path}/{name}")}


@frappe.whitelist(methods=["POST"])
def mkdir(space: str, path: str, name: str) -> dict:
	"""A new folder."""
	ctx = _ctx()
	if not _can_write(ctx, space):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	name = rules.clean_name(name)
	if not name:
		frappe.throw(_("Give the folder a name."))
	sp = _space(ctx)
	_req(sp, "MKCOL", _dav(sp, _root(ctx, sp, space), f"{path}/{name}"))
	return {"name": name}


@frappe.whitelist(methods=["POST"])
def new_doc(space: str, path: str = "", kind: str = "word", title: str | None = None) -> dict:
	"""A new blank Word / Excel / PowerPoint file in a folder. {name, path} — then open it."""
	ctx = _ctx()
	if not _can_write(ctx, space):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	try:
		name = rules.new_doc_name(kind, title)
	except ValueError:
		frappe.throw(_("Choose a document, a sheet or a presentation."))
	sp = _space(ctx)
	root = _root(ctx, sp, space)
	head = requests.head(_dav(sp, root, f"{path}/{name}"), auth=(sp.cloud_user, sp.cloud_password), timeout=30)
	if head.status_code == 200:
		stem, e = name.rsplit(".", 1)
		name = f"{stem} {time.strftime('%d-%m %H%M')}.{e}"
	with open(os.path.join(TEMPLATES, f"new.{rules.NEW_DOCS[kind]}"), "rb") as f:
		_req(sp, "PUT", _dav(sp, root, f"{path}/{name}"), data=f.read())
	return {"name": name, "path": rules.clean_path(f"{path}/{name}")}


@frappe.whitelist(methods=["POST"])
def rename(space: str, path: str, name: str) -> dict:
	"""Rename a file or folder (in the same folder)."""
	ctx = _ctx()
	if not _can_write(ctx, space):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	new = rules.clean_name(name)
	if not new:
		frappe.throw(_("Give it a name."))
	sp = _space(ctx)
	root = _root(ctx, sp, space)
	parent = rules.clean_path(path).rsplit("/", 1)[0] if "/" in rules.clean_path(path) else ""
	_req(sp, "MOVE", _dav(sp, root, path), headers={"Destination": _dav(sp, root, f"{parent}/{new}"), "Overwrite": "F"})
	return {"name": new}


@frappe.whitelist(methods=["POST"])
def delete(space: str, path: str) -> dict:
	"""Delete a file or folder (it stays in the trash for 30 days)."""
	ctx = _ctx()
	if not _can_write(ctx, space) or not rules.clean_path(path):
		frappe.throw(_("You can't change this folder."), frappe.PermissionError)
	sp = _space(ctx)
	_req(sp, "DELETE", _dav(sp, _root(ctx, sp, space), path))
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def open_doc(space: str, path: str) -> dict:
	"""Edit a document in OnlyOffice — with everyone else who has it open. {url}: a link that opens the editor without
	signing in to Nextcloud (it works for a short while)."""
	ctx = _ctx()
	sp = _space(ctx)
	full = "/" + "/".join(p for p in (_root(ctx, sp, space), rules.clean_path(path)) if p)
	if not rules.editable(full):
		frappe.throw(_("This file opens as it is — download it."))
	base, _a = _nc()
	r = requests.post(f"{base}/ocs/v2.php/apps/files/api/v1/directEditing/open", auth=(sp.cloud_user, sp.cloud_password),
					  data={"path": full, "editorId": "onlyoffice"}, params={"format": "json"},
					  headers={"OCS-APIRequest": "true", "Accept": "application/json"}, timeout=30)
	try:
		url = r.json()["ocs"]["data"]["url"]
	except (ValueError, KeyError, TypeError):
		frappe.log_error(title="Workplace: OnlyOffice didn't open", message=f"{r.status_code} {r.text[:400]}")
		frappe.throw(_("Documents are having a problem right now. Please try again in a minute."))
	return {"url": url}


@frappe.whitelist(methods=["POST"])
def send_to_chat(space: str, path: str, channel: str) -> dict:
	"""A copy of the file in a Team chat (everyone in the chat can open it; the original stays in Files)."""
	ctx = _ctx()
	team._channel(ctx, channel, need_member=True)
	sp = _space(ctx)
	r = _req(sp, "GET", _dav(sp, _root(ctx, sp, space), path), timeout=120)
	if len(r.content) > team_rules_max():
		frappe.throw(_("A file can be up to 25 MB in a chat."))
	name = rules.clean_path(path).rsplit("/", 1)[-1]
	from qtt_platform import team_rules

	f = frappe.get_doc({"doctype": "File", "file_name": name, "content": r.content, "is_private": 1, "attached_to_doctype": team.CH,
						"attached_to_name": channel}).insert(ignore_permissions=True)
	m = team._post(ctx, channel, message_type=team_rules.kind_of(name), file_url=f.file_url)
	return {"message": m.name}


def team_rules_max() -> int:
	from qtt_platform import team_rules

	return team_rules.MAX_FILE


def _my_docs_mount(ctx, space) -> str:
	"""Where HR's folder for this person shows in their files ("" when HR hasn't made one)."""
	base, _a = _nc()
	r = requests.get(f"{base}/ocs/v2.php/apps/files_sharing/api/v1/shares", auth=(space.cloud_user, space.cloud_password),
					 params={"shared_with_me": "true", "format": "json"}, headers={"OCS-APIRequest": "true"}, timeout=30)
	try:
		shares = r.json()["ocs"]["data"]
	except (ValueError, KeyError, TypeError):
		return ""
	owner = _settings().nextcloud_admin_user
	for sh in shares:
		if sh.get("uid_owner") == owner and "/People/" in str(sh.get("path") or "") + str(sh.get("file_target") or ""):
			return str(sh.get("file_target") or "").strip("/")
	return ""


@frappe.whitelist(methods=["POST"])
def employee_docs(user: str) -> dict:
	"""HR: an employee's document folder (HR › People › <name>), shared with them read-only so it shows in their
	"My documents from HR". {space: "hr", path}."""
	ctx = _ctx()
	if not ctx.hr:
		frappe.throw(_("HR's folder is for owners, admins and HR."), frappe.PermissionError)
	people = team._people(ctx.tenant)
	if user not in people:
		frappe.throw(_("Choose someone in your business."))
	sp = _space(ctx)
	base, admin = _nc()
	name = rules.clean_name(people[user]["name"]) or rules.cloud_user(user)
	path = f"People/{name}"
	for part in ("People", path):
		requests.request("MKCOL", f"{base}/remote.php/dav/files/{admin[0]}/" + quote(f"{sp.hr_folder}/{part}"), auth=admin, timeout=30)
	cu, _pw = _account(user, people[user]["name"])
	_ocs("POST", "ocs/v2.php/apps/files_sharing/api/v1/shares", admin,
		 data={"path": f"/{sp.hr_folder}/{path}", "shareType": 0, "shareWith": cu, "permissions": 1}, ok=(100, 200, 403))
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
			"last_connected_at": str(d.last_connected_at) if d.last_connected_at else None}


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
	rows = frappe.get_all(DEVICE, filters=filters, fields=["name", "title", "rustdesk_id", "password", "assigned_to", "platform", "notes",
															 "last_connected_at"], order_by="title asc")
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
	if name:
		d = frappe.get_doc(DEVICE, name)
		if d.tenant != ctx.tenant:
			frappe.throw(_("That computer isn't in this business."), frappe.PermissionError)
	else:
		d = frappe.get_doc({"doctype": DEVICE, "tenant": ctx.tenant})
	d.update({"title": str(title or "").strip()[:80] or rid, "rustdesk_id": rid, "assigned_to": assigned_to or None,
			  "platform": platform or "", "notes": (notes or "").strip()[:500]})
	if password:
		d.password = password
	d.save(ignore_permissions=True)
	return _device_out(frappe.get_doc(DEVICE, d.name), ctx, team._names(ctx))


@frappe.whitelist(methods=["POST"])
def delete_device(name: str) -> dict:
	"""Take a computer off the list (owners, admins, HR Admins)."""
	ctx = _ctx()
	if not ctx.manager or frappe.db.get_value(DEVICE, name, "tenant") != ctx.tenant:
		frappe.throw(_("Owners, admins and HR Admins look after Company computers."), frappe.PermissionError)
	frappe.delete_doc(DEVICE, name, ignore_permissions=True)
	return {"deleted": True}


@frappe.whitelist(methods=["POST"])
def connect(name: str | None = None, rustdesk_id: str | None = None) -> dict:
	"""Open a computer in the RustDesk app on this computer: a Company computer (with its permanent password for
	owners / admins / HR Admins), or any RustDesk ID someone gave you. {uri}."""
	ctx = _ctx()
	if name:
		d = frappe.get_doc(DEVICE, name)
		if d.tenant != ctx.tenant or (not ctx.manager and d.assigned_to != ctx.user):
			frappe.throw(_("That computer isn't yours to open."), frappe.PermissionError)
		pw = d.get_password("password", raise_exception=False) if ctx.manager else None
		frappe.db.set_value(DEVICE, d.name, {"last_connected_at": now_datetime(), "last_connected_by": ctx.user}, update_modified=False)
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
	"""Someone left the business (or was suspended): out of its Nextcloud groups. Never breaks the save it hangs on."""
	try:
		if not frappe.db.exists(SPACE, tenant) or not frappe.db.exists(ACCOUNT, user):
			return
		_base, admin = _nc()
		cu = frappe.db.get_value(ACCOUNT, user, "cloud_user")
		for g in (rules.cloud_group(tenant), rules.cloud_group(tenant, "hr")):
			_ocs("DELETE", f"cloud/users/{cu}/groups", admin, data={"groupid": g}, ok=(100, 200, 102, 105))
		frappe.cache().delete_keys(f"qtt_cloud_groups|{user}|{tenant}")
	except Exception:
		frappe.log_error(title="Workplace: couldn't take someone out of Nextcloud groups")
