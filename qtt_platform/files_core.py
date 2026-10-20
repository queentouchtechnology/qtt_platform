"""
Office Pulse Files — the file control every Files action goes through (PROJ-0016 A; rules in files_rules.py):

  access        what this person may do here: the space's rights → folder rules → a lock by someone else; the
                "shared" space is what others shared with them (view / edit)
  save          write a file; the one it replaces is kept as a version (QTT File Version, 30 days)
  to_bin        a deleted file or folder to the recycle bin (QTT File Trash, 30 days); restore / delete for good
  rekey         a rename or move carries its shares, links, tags, comments and versions along
  log           the activity / audit log (QTT File Activity)
  purge         daily: versions and recycle-bin items older than 30 days go for good

Kept objects live beside the business's spaces: <tenant>/.versions/<id> and <tenant>/.bin/<id>[/…] — never listed
as a space, never counted in a quota.
"""

import uuid

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

from qtt_platform import file_store as store
from qtt_platform import files_rules as fr
from qtt_platform import workplace_rules as rules

VERSION, BIN, SHARE, META, RULE, ACTIVITY = "QTT File Version", "QTT File Trash", "QTT File Share", "QTT File Meta", "QTT Folder Rule", "QTT File Activity"
KEYED = ("QTT File Version", "QTT File Share", "QTT File Request", "QTT Share Link", "QTT File Meta", "QTT File Comment", "QTT File Activity",
		 "QTT File Index")


# ---- who may do what ---------------------------------------------------------------------------------------------------
def access(ctx, space: str, path: str = "", *, hr_folder: str = "") -> frappe._dict:
	"""→ {space, path, prefix, key, rights, share}. key: the store key of path in that space (prefix + path)."""
	path = rules.clean_path(path)
	if space == "shared":
		if not path:
			return frappe._dict(space=space, path="", prefix="", key="", rights=frozenset({"read"}), share=None)
		sid, _s, sub = path.partition("/")
		sh = frappe.db.get_value(SHARE, {"name": sid, "tenant": ctx.tenant, "user": ctx.user},
								 ["name", "file_key", "is_dir", "permission", "space", "path"], as_dict=True)
		if not sh:
			frappe.throw(_("That isn't shared with you any more."), frappe.PermissionError)
		key = sh.file_key.rstrip("/") + ("/" + sub if sub else "") if sh.is_dir else sh.file_key
		if not sh.is_dir and sub:
			frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
		rights = fr.SHARE_PERMS.get(sh.permission, frozenset())
		rights = fr.without_lock(rights, *_lock(ctx.tenant, key), ctx.user, now_datetime())
		return frappe._dict(space=space, path=path, prefix=sh.file_key.rstrip("/") + "/" if sh.is_dir else "", key=key, rights=rights, share=sh)
	if space not in rules.SPACES:
		frappe.throw(_("Choose Team files, My files or Company."))
	if space == "hr" and not ctx.hr:
		frappe.throw(_("HR's folder is for owners, admins and HR."), frappe.PermissionError)
	prefix = rules.space_prefix(ctx.tenant, space, ctx.user, hr_folder)
	rights = fr.space_rights(space, hr=ctx.hr, admin=ctx.admin)
	if space in ("team", "company", "hr") and not ctx.admin:
		rights = fr.folder_rights(rights, folder_rules(ctx.tenant, space), path, user=ctx.user, roles=roles(ctx))
	key = rules.object_key(prefix, path) if prefix else ""
	if key and path:
		rights = fr.without_lock(rights, *_lock(ctx.tenant, key), ctx.user, now_datetime())
	return frappe._dict(space=space, path=path, prefix=prefix, key=key, rights=rights, share=None)


def need(a: frappe._dict, right: str) -> None:
	if right not in a.rights:
		msg = {"read": _("You can't open this — ask for access."), "share": _("You can't share this.")}.get(right, _("You can't change this folder."))
		frappe.throw(msg, frappe.PermissionError)


def roles(ctx) -> set[str]:
	return {r for r in (getattr(ctx, "role", None), getattr(ctx, "pulse_role", None)) if r}


def folder_rules(tenant: str, space: str) -> list[dict]:
	key = f"qtt_folder_rules|{tenant}|{space}"
	hit = frappe.cache().get_value(key)
	if hit is None:
		hit = frappe.get_all(RULE, filters={"tenant": tenant, "space": space}, fields=["name", "path", "who_type", "who", "rights"])
		frappe.cache().set_value(key, hit, expires_in_sec=300)
	return hit


def forget_rules(tenant: str, space: str) -> None:
	frappe.cache().delete_value(f"qtt_folder_rules|{tenant}|{space}")


def _lock(tenant: str, key: str) -> tuple:
	m = frappe.db.get_value(META, {"tenant": tenant, "file_key": key}, ["locked_by", "locked_until"], as_dict=True)
	return (m.locked_by, get_datetime(m.locked_until) if m.locked_until else None) if m else (None, None)


# ---- the activity log --------------------------------------------------------------------------------------------------
def log(tenant: str, key: str, space: str, path: str, action: str, actor: str, *, link: str | None = None, detail: str | None = None) -> None:
	try:
		frappe.get_doc({"doctype": ACTIVITY, "tenant": tenant, "file_key": key[:700], "space": space, "path": (path or "")[:700],
						"action": action, "actor": (actor or "")[:200], "link": link, "detail": (detail or "")[:1000],
						"ip": getattr(frappe.local, "request_ip", None)}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Files: activity not recorded")


# ---- versions ----------------------------------------------------------------------------------------------------------
def save(tenant: str, key: str, data: bytes, by: str, content_type: str | None = None) -> str:
	"""Write a file; the one it replaces is kept as a version (30 days). → the new etag."""
	old = store.head(key)
	if old:
		kept = f"{tenant}/.versions/{uuid.uuid4().hex}"
		store.copy(key, kept)
		frappe.get_doc({"doctype": VERSION, "tenant": tenant, "file_key": key, "store_key": kept, "size": int(old.get("ContentLength") or 0),
						"by_user": by if frappe.db.exists("User", by) else None}).insert(ignore_permissions=True)
	etag = store.write(key, data, content_type)
	index_later(key)
	return etag


def index_later(key: str = "", prefix: str = "") -> None:
	"""Search: (re)read a file — or everything under a folder — into the index, after this request commits."""
	try:
		frappe.enqueue("qtt_platform.api.files_search.run_index", queue="short", key=key, prefix=prefix, enqueue_after_commit=True)
	except Exception:
		frappe.log_error(title="Files: search index not queued")


def restore_version(tenant: str, name: str, by: str) -> str:
	"""The file goes back to this version (what it is now is kept as a version too). → its key."""
	v = frappe.db.get_value(VERSION, {"name": name, "tenant": tenant}, ["file_key", "store_key"], as_dict=True)
	if not v:
		frappe.throw(_("That version isn't kept any more."), frappe.DoesNotExistError)
	save(tenant, v.file_key, store.read(v.store_key), by)
	return v.file_key


# ---- the recycle bin ---------------------------------------------------------------------------------------------------
def to_bin(tenant: str, space: str, path: str, key: str, is_dir: bool, by: str) -> int:
	"""Move a file or folder to the recycle bin. → files moved."""
	kept = f"{tenant}/.bin/{uuid.uuid4().hex}"
	src = key.rstrip("/") + "/" if is_dir else key
	objs = store.copy_tree(src, kept + "/" if is_dir else kept)
	store.remove([o["Key"] for o in objs] + ([src] if is_dir else []))
	frappe.get_doc({"doctype": BIN, "tenant": tenant, "space": space, "path": path, "file_key": key[:700], "store_key": kept, "is_dir": 1 if is_dir else 0,
					"size": sum(int(o.get("Size") or 0) for o in objs), "files": len([o for o in objs if not o["Key"].endswith("/")]),
					"deleted_by": by}).insert(ignore_permissions=True)
	return len(objs)


def restore_bin(tenant: str, name: str) -> frappe._dict:
	"""Put a file or folder back where it was (beside it, "… (restored)", if something new took its name)."""
	b = frappe.get_doc(BIN, name)
	if b.tenant != tenant:
		frappe.throw(_("That isn't in the recycle bin any more."), frappe.DoesNotExistError)
	dest = b.file_key
	if store.head(dest) or store.exists_dir(dest):
		stem, dot, ext = dest.rpartition(".") if not b.is_dir and "." in dest.rsplit("/", 1)[-1] else (dest, "", "")
		dest = f"{stem} (restored).{ext}" if dot else f"{dest} (restored)"
	if b.is_dir:
		objs = store.copy_tree(b.store_key + "/", dest.rstrip("/") + "/")
		store.mkdir(dest)
		store.remove([o["Key"] for o in objs])
	else:
		store.copy(b.store_key, dest)
		store.remove([b.store_key])
	frappe.delete_doc(BIN, b.name, ignore_permissions=True, force=True)
	index_later(prefix=dest.rstrip("/") + "/") if b.is_dir else index_later(dest)
	return frappe._dict(space=b.space, key=dest, path=b.path if dest == b.file_key else dest[len(b.file_key) - len(b.path):])


def drop_bin(tenant: str, name: str) -> None:
	b = frappe.db.get_value(BIN, {"name": name, "tenant": tenant}, ["name", "store_key", "is_dir"], as_dict=True)
	if not b:
		return
	store.remove([o["Key"] for o in store.keys_under(b.store_key + "/")] if b.is_dir else [b.store_key])
	frappe.delete_doc(BIN, b.name, ignore_permissions=True, force=True)


# ---- renames carry everything along ------------------------------------------------------------------------------------
def _like(text: str) -> str:
	return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def rekey(tenant: str, old: str, new: str, is_dir: bool) -> None:
	o, n = old.rstrip("/"), new.rstrip("/")
	for dt in KEYED:
		frappe.db.sql(f"update `tab{dt}` set file_key = %s where tenant = %s and file_key = %s", (n, tenant, o))
		if is_dir:
			frappe.db.sql(f"update `tab{dt}` set file_key = concat(%s, substring(file_key, %s)) where tenant = %s and file_key like %s",
						  (n + "/", len(o) + 2, tenant, _like(o) + "/%"))


def forget(tenant: str, key: str, is_dir: bool) -> None:
	"""A deleted file / folder: its shares, links, requests and lock end (its versions and comments stay with the bin item
	for 30 days, keyed by where it was)."""
	cond, val = ("file_key like %s", _like(key.rstrip("/")) + "/%") if is_dir else ("file_key = %s", key)
	for dt in ("QTT File Share", "QTT File Request", "QTT File Meta", "QTT File Index"):
		frappe.db.sql(f"delete from `tab{dt}` where tenant = %s and ({cond} or file_key = %s)", (tenant, val, key.rstrip("/")))
	frappe.db.sql(f"update `tabQTT Share Link` set status = 'Revoked' where tenant = %s and ({cond} or file_key = %s)", (tenant, val, key.rstrip("/")))


# ---- daily -------------------------------------------------------------------------------------------------------------
def purge() -> None:
	"""Scheduler (daily): versions and recycle-bin items older than 30 days are removed for good."""
	cut = add_days(now_datetime(), -fr.KEEP_DAYS)
	try:
		for v in frappe.get_all(VERSION, filters={"creation": ["<", cut]}, fields=["name", "store_key"], limit=5000):
			store.remove([v.store_key])
			frappe.delete_doc(VERSION, v.name, ignore_permissions=True, force=True)
		for b in frappe.get_all(BIN, filters={"creation": ["<", cut]}, fields=["name", "tenant"], limit=2000):
			drop_bin(b.tenant, b.name)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Files: daily clean-up failed")
