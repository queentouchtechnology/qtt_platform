"""
Office Pulse Files over WebDAV (PROJ-0016 E2; rules in dav_rules.py): Files as a drive on Windows / macOS / Linux
and in phone file apps. The WebDAV gateway (ops/dav_gateway, on QTT-AI-OS behind office.queentouchtech.in/dav/) does no
file work itself: every step is one of the gw_* calls here, signed with the gateway secret and carrying the person's
email + sync password — so rights, locks, versions, the recycle bin, activity, quotas and encryption are exactly the
app's (api/workplace.py, files_core.py).

  sync_info / new_sync_password / revoke_sync_password    the app: the address, and each person's sync passwords
                                                          (one per computer or phone; shown once; only a hash kept)
  gw_auth / gw_list / gw_stat / gw_get / gw_put / gw_mkdir / gw_delete / gw_move / gw_copy    the gateway

Ten wrong passwords for one email in 15 minutes → that email waits 15 minutes.
"""

import hashlib
import mimetypes
import secrets

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime
from werkzeug.wrappers import Response

from qtt_platform import dav_rules as dr
from qtt_platform import file_store as store
from qtt_platform import files_core as core
from qtt_platform import workplace_rules as rules

PW = "QTT Sync Password"
SETTINGS = "QTT Workplace Settings"
MAX_TRIES = 10


def _settings():
	return frappe.get_cached_doc(SETTINGS)


# ---- the app ------------------------------------------------------------------------------------------------------------
def _app_ctx():
	from qtt_platform.api.workplace import _ctx

	return _ctx()


def _pw_out(r) -> dict:
	return {"name": r.name, "label": r.label or "", "hint": r.hint, "created": str(r.creation)[:16], "last_used": str(r.last_used)[:16] if r.last_used else None}


@frappe.whitelist(methods=["GET"])
def sync_info() -> dict:
	"""Whether sync is offered, the address to type into a computer or phone, the user name (your email), and your
	sync passwords for this business."""
	ctx = _app_ctx()
	s = _settings()
	rows = frappe.get_all(PW, filters={"tenant": ctx.tenant, "user": ctx.user, "revoked": 0}, fields=["name", "label", "hint", "creation", "last_used"],
						  order_by="creation desc")
	return {"enabled": bool(s.get("dav_enabled")), "url": s.get("dav_url") or "", "username": ctx.user, "passwords": [_pw_out(r) for r in rows],
			"folders": dr.top_folders(bool(ctx.hr))}


@frappe.whitelist(methods=["POST"])
def new_sync_password(label: str = "") -> dict:
	"""A new sync password for one computer or phone — shown this once ({password}); only its hash is kept."""
	ctx = _app_ctx()
	if not _settings().get("dav_enabled"):
		frappe.throw(_("Sync from computers and phones isn't switched on yet."))
	if frappe.db.count(PW, {"tenant": ctx.tenant, "user": ctx.user, "revoked": 0}) >= 10:
		frappe.throw(_("You have 10 sync passwords — stop one you no longer use first."))
	pw = dr.new_password()
	h, salt = dr.hash_password(pw)
	r = frappe.get_doc({"doctype": PW, "tenant": ctx.tenant, "user": ctx.user, "label": str(label or "").strip()[:60] or _("Computer"),
						"secret_hash": h, "salt": salt, "hint": dr.hint(pw)}).insert(ignore_permissions=True)
	from qtt_platform.audit import write_audit_event

	write_audit_event("sync_password_made", tenant=ctx.tenant, target_doctype=PW, target_name=r.name, metadata={"label": r.label})
	return {"password": pw, **_pw_out(r)}


@frappe.whitelist(methods=["POST"])
def revoke_sync_password(name: str) -> dict:
	"""Stop a sync password — that computer or phone can't open Files any more."""
	ctx = _app_ctx()
	r = frappe.get_doc(PW, name) if frappe.db.exists(PW, name) else None
	if not r or r.tenant != ctx.tenant or (r.user != ctx.user and not ctx.admin):
		frappe.throw(_("That sync password isn't here any more."), frappe.DoesNotExistError)
	r.revoked = 1
	r.save(ignore_permissions=True)
	frappe.cache().delete_keys("qtt_dav_ok|")
	return {"ok": True}


def revoke_all(tenant: str, user: str) -> None:
	"""Someone leaves the business: their sync passwords stop (called from api/workplace.drop)."""
	frappe.db.sql(f"update `tab{PW}` set revoked = 1 where tenant = %s and user = %s", (tenant, user))
	frappe.cache().delete_keys("qtt_dav_ok|")


# ---- the gateway: who is calling --------------------------------------------------------------------------------------
def _gw():
	"""Check the gateway's signature and the person's email + sync password; act as them in that business."""
	s = _settings()
	secret = s.get_password("dav_gateway_secret", raise_exception=False) if s.get("dav_enabled") else None
	if not secret or not secrets.compare_digest(secret, frappe.get_request_header("X-QTT-Gateway") or ""):
		raise frappe.PermissionError("gateway")
	user = (frappe.get_request_header("X-QTT-User") or "").strip().lower()
	pw = frappe.get_request_header("X-QTT-Pass") or ""
	if not user or not pw:
		raise frappe.AuthenticationError("login")
	fails = f"qtt_dav_fail|{user}"
	if cint(frappe.cache().get_value(fails)) >= MAX_TRIES:
		raise frappe.AuthenticationError("wait")
	ok_key = "qtt_dav_ok|" + hashlib.sha256(f"{user}|{dr.normalise(pw)}".encode()).hexdigest()
	name = frappe.cache().get_value(ok_key)
	row = frappe.db.get_value(PW, {"name": name, "revoked": 0}, ["name", "tenant", "user", "last_used"], as_dict=True) if name else None
	if not row:
		row = None
		for r in frappe.get_all(PW, filters={"user": user, "revoked": 0}, fields=["name", "tenant", "user", "secret_hash", "salt", "last_used"]):
			if dr.check_password(pw, r.secret_hash, r.salt):
				row = r
				break
		if not row:
			n = cint(frappe.cache().get_value(fails)) + 1
			frappe.cache().set_value(fails, n, expires_in_sec=15 * 60)
			raise frappe.AuthenticationError("login")
		frappe.cache().set_value(ok_key, row.name, expires_in_sec=300)
	if not frappe.db.get_value("User", row.user, "enabled"):
		raise frappe.AuthenticationError("login")
	if not row.last_used or (now_datetime() - get_datetime(row.last_used)).total_seconds() > 600:
		frappe.db.set_value(PW, row.name, "last_used", now_datetime(), update_modified=False)
	frappe.local.session_obj = None  # never save a login session for the gateway's calls
	form = frappe.local.form_dict
	frappe.set_user(row.user)
	frappe.local.form_dict = form
	frappe.local.qtt_pinned_tenant = {"user": row.user, "tenant": row.tenant}
	frappe.local.qtt_team_people = {}
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	frappe.local.flags.commit = True
	return ctx


def _p(name: str) -> str:
	return frappe.form_dict.get(name) or (frappe.request.args.get(name) if frappe.request else "") or ""


def _shared_names(ctx) -> dict:
	"""'Shared with me' folder names → share ids (two shares with one name get ' (2)')."""
	from qtt_platform.api import files_share

	items = sorted(files_share.shared_root(ctx)["items"], key=lambda i: (i["name"].lower(), i["path"]))
	names = dr.unique_names([i["name"] for i in items])
	return {n: i for n, i in zip(names, items)}


def _where(ctx, dav_path: str) -> tuple[str, str]:
	"""A WebDAV path → (space, path in Files). ('', '') is the top; ('shared', '') the Shared with me folder."""
	try:
		space, path = dr.split(dav_path)
	except ValueError:
		raise frappe.PermissionError("path")
	if space == "?" or (space == "hr" and not ctx.hr):
		raise frappe.DoesNotExistError("path")
	if space == "shared" and path:
		first, _s, rest = path.partition("/")
		hit = _shared_names(ctx).get(first)
		if not hit:
			raise frappe.DoesNotExistError("path")
		path = "/".join(p for p in (hit["path"], rest) if p)
	return space, path


def _at(ctx, space: str, path: str):
	from qtt_platform.api.workplace import _at as at

	return at(ctx, space, path)


def _item(i: dict) -> dict:
	return {"name": i["name"], "is_dir": bool(i["is_dir"]), "size": int(i.get("size") or 0), "modified": i.get("modified"),
			"etag": f"{i.get('size') or 0}-{i.get('modified') or ''}"}


def _list(ctx, dav_path: str) -> list[dict]:
	from qtt_platform.api.workplace import list_folder

	space, path = _where(ctx, dav_path)
	if not space:
		return [{"name": n, "is_dir": True, "size": 0, "modified": None, "etag": n} for n in dr.top_folders(bool(ctx.hr))]
	if space == "shared" and not path:
		return [{**_item(i), "name": n} for n, i in _shared_names(ctx).items()]
	if path:
		at = _at(ctx, space, path)
		if not store.exists_dir(at.key) and store.head(at.key):
			raise frappe.ValidationError("not a folder")
	return [_item(i) for i in list_folder(space, path)["items"] if not dr.is_junk(i["name"])]


# ---- the gateway: what it asks for ------------------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["GET"])
def gw_auth() -> dict:
	"""Gateway: is this email + sync password good? → who, which business, the top folders."""
	ctx = _gw()
	return {"ok": True, "user": ctx.user, "tenant": ctx.tenant, "folders": dr.top_folders(bool(ctx.hr))}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def gw_list(path: str = "/") -> dict:
	"""Gateway: a folder's items (name, is_dir, size, modified, etag) — desktop clutter left out."""
	ctx = _gw()
	return {"items": _list(ctx, path or _p("path") or "/")}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def gw_stat(path: str = "/") -> dict:
	"""Gateway: one file or folder (404 when it isn't there)."""
	ctx = _gw()
	path = path or _p("path") or "/"
	parts = [p for p in path.split("/") if p]
	if not parts:
		return {"name": "", "is_dir": True, "size": 0, "modified": None, "etag": "root"}
	if dr.is_junk(parts[-1]):
		raise frappe.DoesNotExistError("junk")
	parent = "/" + "/".join(parts[:-1])
	hit = next((i for i in _list(ctx, parent) if i["name"] == parts[-1]), None)
	if not hit:
		raise frappe.DoesNotExistError("missing")
	return hit


def _seen_recently(ctx, key: str) -> bool:
	k = "qtt_dav_read|" + hashlib.sha1(f"{ctx.user}|{key}".encode()).hexdigest()
	if frappe.cache().get_value(k):
		return True
	frappe.cache().set_value(k, 1, expires_in_sec=3600)
	return False


@frappe.whitelist(allow_guest=True, methods=["GET"])
def gw_get(path: str = ""):
	"""Gateway: a file's bytes (the activity shows it opened once an hour, not on every thumbnail)."""
	from qtt_platform.api.workplace import _space_of

	ctx = _gw()
	space, fpath = _where(ctx, path or _p("path"))
	if not space or not fpath:
		raise frappe.ValidationError("folder")
	at = _at(ctx, space, fpath)
	core.need(at, "read")
	data = store.read(at.key)
	if not _seen_recently(ctx, at.key):
		core.log(ctx.tenant, at.key, _space_of(at), at.path, "download", ctx.user, detail="sync")
	return Response(data, mimetype=mimetypes.guess_type(at.key)[0] or "application/octet-stream")


@frappe.whitelist(allow_guest=True, methods=["PUT", "POST"])
def gw_put(path: str = "") -> dict:
	"""Gateway: write a file (the request body). Replacing one keeps the old as a version — except an empty one a
	computer made just before writing it."""
	from qtt_platform.api.workplace import MAX_UPLOAD, _quota_gb, _quota_root, _space_of

	ctx = _gw()
	path = path or _p("path")
	name = [p for p in path.split("/") if p][-1] if path.strip("/") else ""
	if dr.is_junk(name):
		return {"ok": True, "ignored": True}
	space, fpath = _where(ctx, path)
	if not space or not fpath:  # (a new file straight into Shared with me has no share name, so _where refused it)
		raise frappe.PermissionError("here")
	at = _at(ctx, space, fpath)
	old = store.head(at.key)
	core.need(at, "write" if old else "create")
	if not old:
		parent_path = fpath.rsplit("/", 1)[0] if "/" in fpath else ""
		core.need(_at(ctx, space, parent_path), "create")
	data = frappe.request.get_data(cache=False) if frappe.request else b""
	if len(data) > MAX_UPLOAD:
		raise frappe.ValidationError("A file can be up to 100 MB.")
	root = _quota_root(at)
	if root and not rules.fits(store.used(root), _quota_gb(_space_of(at)), len(data) - int((old or {}).get("ContentLength") or 0)):
		raise frappe.ValidationError("This space is full.")
	ctype = mimetypes.guess_type(at.key)[0]
	if old and int(old.get("ContentLength") or 0) == 0:
		store.write(at.key, data, ctype)  # the empty file a computer made first: no version of it
		core.index_later(at.key)
	else:
		core.save(ctx.tenant, at.key, data, ctx.user, ctype)
	core.log(ctx.tenant, at.key, _space_of(at), at.path, "replace" if old and int(old.get("ContentLength") or 0) else "upload", ctx.user, detail="sync")
	if not old:
		core.automate(ctx.tenant, "upload", at.key, ctx.user)
	return {"ok": True, "size": len(data)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def gw_mkdir(path: str = "") -> dict:
	"""Gateway: a new folder."""
	ctx = _gw()
	space, fpath = _where(ctx, path or _p("path"))
	if not space or not fpath or (space == "shared" and "/" not in fpath):
		raise frappe.PermissionError("here")
	parent, _s, name = fpath.rpartition("/")
	at = _at(ctx, space, parent)
	core.need(at, "create")
	from qtt_platform.api.workplace import _child

	store.mkdir(_child(at, rules.clean_name(name)))
	return {"ok": True}


@frappe.whitelist(allow_guest=True, methods=["POST", "DELETE"])
def gw_delete(path: str = "") -> dict:
	"""Gateway: delete — to the recycle bin for 30 days, as in the app."""
	from qtt_platform.api import workplace

	ctx = _gw()
	path = path or _p("path")
	if dr.is_junk([p for p in path.split("/") if p][-1] if path.strip("/") else ""):
		return {"ok": True}
	space, fpath = _where(ctx, path)
	if not space or not fpath or (space == "shared" and "/" not in fpath):
		raise frappe.PermissionError("here")
	workplace.delete(space, fpath)
	return {"ok": True}


def _move_or_copy(ctx, src: str, dst: str, overwrite: bool, move: bool) -> dict:
	from qtt_platform.api.workplace import _child, _is_dir, _quota_gb, _quota_root, _space_of

	s_space, s_path = _where(ctx, src)
	d_space, d_path = _where(ctx, dst)
	if not s_space or not s_path or not d_space or not d_path or (s_space == "shared" and "/" not in s_path and move):
		raise frappe.PermissionError("here")
	s_at = _at(ctx, s_space, s_path)
	is_dir = _is_dir(s_at.key)
	if not is_dir and not store.head(s_at.key):
		raise frappe.DoesNotExistError("missing")
	core.need(s_at, "delete" if move else "read")
	d_parent, _s, d_name = d_path.rpartition("/")
	d_name = rules.clean_name(d_name)
	p_at = _at(ctx, d_space, d_parent)
	core.need(p_at, "create")
	target = _child(p_at, d_name)
	if target.rstrip("/") == s_at.key.rstrip("/"):
		return {"ok": True}
	if is_dir and (target.rstrip("/") + "/").startswith(s_at.key.rstrip("/") + "/"):
		raise frappe.ValidationError("A folder can't go inside itself.")
	exists = bool(store.head(target)) or store.exists_dir(target)
	if exists:
		if not overwrite:
			raise frappe.ValidationError("exists")
		t_at = _at(ctx, d_space, d_path)
		core.need(t_at, "delete")
		t_dir = _is_dir(target)
		core.to_bin(ctx.tenant, _space_of(t_at), t_at.path, target, t_dir, ctx.user)
		core.forget(ctx.tenant, target, t_dir)
	size = sum(int(o.get("Size") or 0) for o in store.keys_under(s_at.key.rstrip("/") + "/")) if is_dir else int(store.head(s_at.key).get("ContentLength") or 0)
	root = _quota_root(p_at)
	if root and (not move or _quota_root(s_at) != root) and not rules.fits(store.used(root), _quota_gb(_space_of(p_at)), size):
		raise frappe.ValidationError("This space is full.")
	if is_dir:
		objs = store.copy_tree(s_at.key.rstrip("/") + "/", target.rstrip("/") + "/")
	else:
		store.copy(s_at.key, target)
		objs = [{"Key": s_at.key}]
	if move:
		store.remove([o["Key"] for o in objs] if is_dir else [s_at.key])
		core.rekey(ctx.tenant, s_at.key, target, is_dir)
	if is_dir:
		core.index_later(prefix=target.rstrip("/") + "/")
	else:
		core.index_later(target)
	new_path = "/".join(p for p in (p_at.path, d_name) if p)
	core.log(ctx.tenant, target, _space_of(p_at), new_path, "move" if move else "copy", ctx.user, detail=s_at.path)
	return {"ok": True, "replaced": exists}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def gw_move(src: str = "", dst: str = "", overwrite: int = 0) -> dict:
	"""Gateway: move or rename — shares, links, tags, comments and versions go with it (as rename in the app). A file
	already at the destination goes to the recycle bin when overwrite is asked."""
	ctx = _gw()
	return _move_or_copy(ctx, src or _p("src"), dst or _p("dst"), bool(cint(overwrite or _p("overwrite"))), True)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def gw_copy(src: str = "", dst: str = "", overwrite: int = 0) -> dict:
	"""Gateway: copy a file or folder."""
	ctx = _gw()
	return _move_or_copy(ctx, src or _p("src"), dst or _p("dst"), bool(cint(overwrite or _p("overwrite"))), False)
