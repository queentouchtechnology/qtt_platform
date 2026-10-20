"""
Office Pulse Files — share links for people outside the app (PROJ-0016 A3; rules in files_rules.py).

In the app (someone who may share the item):
  make_link / update_link / rotate_link / revoke_link / link_activity
    a random, unguessable key per link — only its hash is kept, so the link is shown once (and again after "new key").
    Key in the URL, or sent separately (the page asks for it). Optional: password, expiry (1 hour … a date), view and
    download limits, only listed emails (they prove it with a code), "ask me first" (approval in the app), and what the
    link does: preview (no download button), download, or upload only (File Drop: they can't see what's there).

For the person with the link (no login; app.queentouchtech.in/s/<key> or /sl/<id>):
  page → open (key / password / email code / approval → a ticket for 2 hours) → items / get / view / drop
Every open, download and upload is in the activity log, with the IP.
"""

import mimetypes
from html import escape

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime, get_url, now_datetime
from werkzeug.wrappers import Response

from qtt_platform import file_store as store
from qtt_platform import files_core as core
from qtt_platform import files_rules as fr
from qtt_platform import workplace_rules as rules

LINK, GUEST = "QTT Share Link", "QTT Share Link Guest"
TICKET_TTL = 2 * 3600
MAX_UPLOAD = 100 * 1024 * 1024
INLINE = ("image", "video", "audio")


def _title(key: str) -> str:
	return key.rstrip("/").rsplit("/", 1)[-1]


def _url(key: str | None, name: str) -> str:
	return get_url(f"/s/{key}") if key else get_url(f"/sl/{name}")


# ---- in the app --------------------------------------------------------------------------------------------------------
def links_of(ctx, at) -> list[dict]:
	"""The item's live links (for the Share sheet)."""
	out = []
	for l in frappe.get_all(LINK, filters={"tenant": ctx.tenant, "file_key": at.key.rstrip("/"), "status": "Active"},
							fields=["name", "label", "mode", "key_hint", "expires_at", "max_views", "max_downloads", "views", "downloads", "uploads",
									"password_hash", "allowed_emails", "require_approval", "created_by", "creation"], order_by="creation desc"):
		expired = bool(l.expires_at and get_datetime(l.expires_at) <= now_datetime())
		out.append({"name": l.name, "label": l.label or "", "mode": l.mode, "key_hint": l.key_hint, "expires_at": str(l.expires_at or "")[:16], "expired": expired,
					"max_views": l.max_views or 0, "max_downloads": l.max_downloads or 0, "views": l.views or 0, "downloads": l.downloads or 0,
					"uploads": l.uploads or 0, "password": bool(l.password_hash), "emails": fr.emails(l.allowed_emails), "approval": bool(l.require_approval),
					"mine": l.created_by == ctx.user, "url_without_key": _url(None, l.name)})
	return out


def _link_for(ctx, name: str):
	from qtt_platform.api.workplace import _at

	l = frappe.get_doc(LINK, name)
	if l.tenant != ctx.tenant:
		frappe.throw(_("That link isn't here any more."), frappe.DoesNotExistError)
	if l.created_by != ctx.user and not ctx.admin:
		core.need(_at(ctx, l.space, l.path), "share")
	return l


def _apply(l, d: dict, now) -> None:
	if "mode" in d:
		if d["mode"] not in fr.LINK_MODES:
			frappe.throw(_("Choose Preview, Download or Upload only."))
		if d["mode"] == "upload" and not l.is_dir:
			frappe.throw(_("Upload only works on a folder."))
		l.mode = d["mode"]
	if "label" in d:
		l.label = str(d.get("label") or "")[:80]
	if "password" in d:
		pw = str(d.get("password") or "")
		if pw and len(pw) < 6:
			frappe.throw(_("A link password needs at least 6 characters."))
		l.password_hash = fr.hash_password(pw) if pw else None
	if "expiry" in d:
		try:
			e = fr.expires_at(str(d.get("expiry") or ""), now, d.get("date"))
		except ValueError:
			frappe.throw(_("Choose a date from today on."))
		l.expires_at = e
	for f in ("max_views", "max_downloads"):
		if f in d:
			l.set(f, max(0, int(d.get(f) or 0)))
	if "emails" in d:
		l.allowed_emails = ", ".join(fr.emails(d.get("emails") if isinstance(d.get("emails"), str) else ",".join(d.get("emails") or [])))
	if "approval" in d:
		l.require_approval = 1 if str(d.get("approval")).lower() in ("1", "true") else 0


@frappe.whitelist(methods=["POST"])
def make_link(space: str, path: str, data=None) -> dict:
	"""A share link to a file or folder. data: {mode: preview | download | upload, label, password, expiry: 1h | 1d | 7d |
	30d | date | "" (never), date, max_views, max_downloads, emails, approval, key_in_url (default yes)}.
	→ {name, url, key (when sent separately)} — the only time the key is shown."""
	from qtt_platform.api.workplace import _at, _ctx, _space_of

	ctx = _ctx()
	at = _at(ctx, space, path)
	core.need(at, "share")
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	is_dir = not store.head(at.key) and store.exists_dir(at.key)
	if not is_dir and not store.head(at.key):
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	if d.get("mode") == "upload":
		core.need(at, "create")
	key = fr.new_key()
	l = frappe.get_doc({"doctype": LINK, "tenant": ctx.tenant, "space": _space_of(at), "path": at.path, "file_key": at.key.rstrip("/"), "is_dir": 1 if is_dir else 0,
						"key_hash": fr.key_hash(key), "key_hint": key[-4:], "mode": "download", "status": "Active", "created_by": ctx.user})
	_apply(l, {"mode": d.get("mode") or "download", **{k: v for k, v in d.items() if k != "mode"}}, now_datetime())
	l.insert(ignore_permissions=True)
	core.log(ctx.tenant, at.key, _space_of(at), at.path, "link_create", ctx.user, link=l.name, detail=l.mode)
	in_url = str(d.get("key_in_url", 1)).lower() not in ("0", "false")
	return {"name": l.name, "url": _url(key if in_url else None, l.name), "key": None if in_url else key}


@frappe.whitelist(methods=["POST"])
def update_link(name: str, data=None) -> dict:
	"""Change a link's password, expiry, limits, emails, approval or what it does (the URL stays the same)."""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	l = _link_for(ctx, name)
	_apply(l, frappe.parse_json(data) if isinstance(data, str) else (data or {}), now_datetime())
	l.save(ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def rotate_link(name: str, key_in_url: int = 1) -> dict:
	"""A new key for the link: the old URL stops working at once. → {url, key}."""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	l = _link_for(ctx, name)
	key = fr.new_key()
	l.key_hash, l.key_hint = fr.key_hash(key), key[-4:]
	l.save(ignore_permissions=True)
	core.log(ctx.tenant, l.file_key, l.space, l.path, "link_rotate", ctx.user, link=l.name)
	in_url = str(key_in_url).lower() not in ("0", "false")
	return {"url": _url(key if in_url else None, l.name), "key": None if in_url else key}


@frappe.whitelist(methods=["POST"])
def revoke_link(name: str) -> dict:
	"""Stop a link now (before it ends by itself)."""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	l = _link_for(ctx, name)
	l.status = "Revoked"
	l.save(ignore_permissions=True)
	core.log(ctx.tenant, l.file_key, l.space, l.path, "link_revoke", ctx.user, link=l.name)
	return {"ok": True}


@frappe.whitelist(methods=["GET"])
def link_activity(name: str) -> dict:
	"""Who opened, downloaded or uploaded through this link, when, from where; and the people asking to use it."""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	l = _link_for(ctx, name)
	rows = frappe.get_all(core.ACTIVITY, filters={"tenant": ctx.tenant, "link": l.name}, fields=["actor", "action", "detail", "creation", "ip"],
						  order_by="creation desc", limit=200)
	guests = frappe.get_all(GUEST, filters={"link": l.name}, fields=["name", "email", "guest_name", "status", "creation"], order_by="creation desc")
	return {"activity": [{"who": a.actor, "action": a.action, "detail": a.detail, "when": str(a.creation)[:16], "ip": a.ip} for a in rows],
			"guests": [{"name": g.name, "email": g.email, "title": g.guest_name, "status": g.status, "when": str(g.creation)[:16]} for g in guests]}


def decide_guest(ctx, name: str, yes: bool) -> dict:
	g = frappe.get_doc(GUEST, name)
	l = _link_for(ctx, g.link)
	g.status, g.decided_by = ("Approved" if yes else "Declined"), ctx.user
	g.save(ignore_permissions=True)
	core.log(ctx.tenant, l.file_key, l.space, l.path, "approve" if yes else "decline", ctx.user, link=l.name, detail=g.email)
	try:
		business = frappe.db.get_value("QTT Tenant", ctx.tenant, "tenant_name") or "QTT OS"
		frappe.sendmail(recipients=[g.email], subject=(_("You can open {0} now") if yes else _("Your request for {0}")).format(_title(l.file_key)),
						message=(_("{0} approved your request. Open the link you were given again to see it.") if yes else
								 _("{0} declined your request for this file.")).format(escape(business)), now=True)
	except Exception:
		frappe.log_error(title="Files: approval email not sent")
	return {"ok": True}


# ---- for the person with the link --------------------------------------------------------------------------------------
def _secret() -> str:
	from frappe.utils.password import get_encryption_key

	return "qtt-share-link|" + get_encryption_key()


def _by_key(key: str):
	name = frappe.db.get_value(LINK, {"key_hash": fr.key_hash(key)}) if key else None
	return frappe.get_doc(LINK, name) if name else None


def _dict(l) -> dict:
	return {"status": l.status, "expires_at": get_datetime(l.expires_at) if l.expires_at else None, "mode": l.mode, "max_views": l.max_views,
			"views": l.views, "max_downloads": l.max_downloads, "downloads": l.downloads, "allowed_emails": l.allowed_emails,
			"require_approval": l.require_approval}


def _ip() -> str:
	return getattr(frappe.local, "request_ip", "") or ""


def _ticket(ticket: str):
	"""The link a ticket is for, still usable (live, not expired) — else None."""
	claims = rules.jwt_verify(ticket or "", _secret())
	if not claims:
		return None, None
	l = frappe.get_doc(LINK, claims["l"]) if frappe.db.exists(LINK, claims.get("l")) else None
	if not l or l.key_hash != claims.get("h") or fr.link_state({**_dict(l), "max_views": 0}, now_datetime()) in ("revoked", "expired"):
		return None, None
	return l, claims


def _info(l) -> dict:
	business = frappe.db.get_value("QTT Tenant", l.tenant, "tenant_name") or ""
	# the link's own name stays with the person who made it — the page shows the file's name
	out = {"title": _title(l.file_key), "mode": l.mode, "is_dir": bool(l.is_dir), "business": business,
		   "expires_at": str(l.expires_at or "")[:16], "can_download": l.mode == "download"}
	if not l.is_dir:
		h = store.head(l.file_key) or {}
		name = _title(l.file_key)
		out.update({"size_text": rules.human_size(int(h.get("ContentLength") or 0)), "type": rules.kind_of_file(name), "office": rules.editable(name)})
	return out


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=600)
def open(k: str = "", id: str = "", key: str = "", password: str = "", email: str = "", token: str = "", name: str = "", note: str = "") -> dict:
	"""Open a share link. → {need: key | password | email | approval, …} until everything this link asks for is given,
	then {ticket, info} (the ticket works for 2 hours)."""
	if id and not (k or key):
		return {"need": "key"} if frappe.db.exists(LINK, {"name": id, "status": "Active"}) else {"state": "gone"}
	l = _by_key(k or key)
	if not l or (id and l.name != id):
		if id:
			core.log(frappe.db.get_value(LINK, id, "tenant") or "", "", "", "", "link_bad_key", "guest", link=id if frappe.db.exists(LINK, id) else None)
		return {"state": "bad_key"} if id else {"state": "gone"}
	st = fr.link_state(_dict(l), now_datetime(), "upload" if l.mode == "upload" else "view")
	if st != "ok":
		return {"state": st}
	if l.password_hash and not fr.check_password(password, l.password_hash):
		if password:
			core.log(l.tenant, l.file_key, l.space, l.path, "link_bad_password", "guest", link=l.name)
		return {"need": "password", "wrong": bool(password)}
	who = "guest"
	if fr.needs_email(_dict(l)):
		from qtt_platform.api import verify

		email = str(email or "").strip().lower()
		if not email or not verify.check_token("file_link", "email", token, email):
			return {"need": "email", "approval": bool(l.require_approval), "listed": bool(fr.emails(l.allowed_emails))}
		if not fr.email_allowed(_dict(l), email):
			core.log(l.tenant, l.file_key, l.space, l.path, "link_refused", email, link=l.name)
			return {"state": "not_allowed"}
		who = email
		if l.require_approval:
			g = frappe.db.get_value(GUEST, {"link": l.name, "email": email}, ["name", "status"], as_dict=True)
			if not g:
				frappe.get_doc({"doctype": GUEST, "link": l.name, "email": email, "guest_name": str(name or "")[:80], "note": str(note or "")[:500]}).insert(ignore_permissions=True)
				frappe.db.commit()
				try:
					from qtt_platform.push import notify

					notify([l.created_by], title=_("{0} asks to open {1}").format(email, _title(l.file_key)), body=_("Approve or decline in Files › Requests."),
						   data={"kind": "files", "tenant": l.tenant, "open": "requests"})
				except Exception:
					pass
				return {"need": "approval", "sent": True}
			if g.status == "Pending":
				return {"need": "approval"}
			if g.status == "Declined":
				return {"state": "declined"}
	if l.mode != "upload":
		frappe.db.set_value(LINK, l.name, "views", (l.views or 0) + 1, update_modified=False)
	core.log(l.tenant, l.file_key, l.space, l.path, "link_view" if l.mode != "upload" else "link_open", who, link=l.name)
	frappe.db.commit()
	import time

	ticket = rules.jwt_hs256({"l": l.name, "h": l.key_hash, "e": who, "exp": int(time.time()) + TICKET_TTL}, _secret())
	return {"ticket": ticket, "info": _info(l)}


def _target(l, path: str) -> str:
	sub = rules.clean_path(path)
	if not l.is_dir:
		if sub:
			frappe.throw(_("That isn't here."), frappe.DoesNotExistError)
		return l.file_key
	return l.file_key.rstrip("/") + ("/" + sub if sub else "")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def items(ticket: str, path: str = "") -> dict:
	"""A folder link's contents (not for upload-only links)."""
	l, _c = _ticket(ticket)
	if not l or l.mode == "upload" or not l.is_dir:
		return {"state": "gone"}
	folder = _target(l, path).rstrip("/") + "/"
	out = store.list_folder(folder)
	for i in out:
		i["size_text"] = "" if i["is_dir"] else rules.human_size(i["size"])
		i["office"] = not i["is_dir"] and rules.editable(i["name"])
		i["path"] = "/".join(p for p in (rules.clean_path(path), i["name"]) if p)
	return {"items": out, "path": rules.clean_path(path)}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=600)
def get(ticket: str, path: str = "", dl: int = 0):
	"""A file through a link: shown in the browser, or downloaded (download links only, within their limit)."""
	l, c = _ticket(ticket)
	if not l or l.mode == "upload":
		return Response("This link has ended.", status=410)
	download = str(dl) in ("1", "true")
	key = _target(l, path)
	name = _title(key)
	if download:
		if fr.link_state(_dict(l), now_datetime(), "download") != "ok":
			return Response("Downloading isn't possible with this link.", status=403)
		frappe.db.set_value(LINK, l.name, "downloads", (l.downloads or 0) + 1, update_modified=False)
	elif rules.kind_of_file(name) not in INLINE and l.mode != "download":
		return Response("Open it in the viewer.", status=403)
	data = store.read(key)
	core.log(l.tenant, key, l.space, l.path, "link_download" if download else "link_view", c.get("e") or "guest", link=l.name, detail=name)
	frappe.db.commit()
	r = Response(data, mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream")
	from urllib.parse import quote

	r.headers["Content-Disposition"] = f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(name)}"
	r.headers["Cache-Control"] = "no-store"
	r.headers["X-Content-Type-Options"] = "nosniff"
	return r


@frappe.whitelist(allow_guest=True, methods=["POST"])
def view(ticket: str, path: str = "") -> dict:
	"""A document (Word, Excel, PowerPoint, PDF…) in the viewer — download, print and copy off for preview links."""
	l, c = _ticket(ticket)
	if not l or l.mode == "upload":
		return {"state": "gone"}
	key = _target(l, path)
	h = store.head(key)
	if not h or not rules.editable(_title(key)):
		return {"state": "gone"}
	from qtt_platform.api import workplace_docs

	core.log(l.tenant, key, l.space, l.path, "link_view", c.get("e") or "guest", link=l.name, detail=_title(key))
	return {"url": workplace_docs.guest_link(key, _title(key), str(h.get("ETag") or "").strip('"'), c.get("e") or "Guest", l.mode == "download")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=600)
def drop(ticket: str) -> dict:
	"""Upload a file through an upload-only link (File Drop): it goes into the shared folder; nothing there is shown.
	A file with the same name gets a number — nothing is replaced."""
	l, c = _ticket(ticket)
	if not l or l.mode != "upload" or fr.link_state(_dict(l), now_datetime(), "upload") != "ok":
		return {"state": "gone"}
	up = frappe.request.files.get("file") if frappe.request else None
	if not up:
		return {"state": "no_file"}
	data = up.stream.read(MAX_UPLOAD + 1)
	if len(data) > MAX_UPLOAD:
		return {"state": "too_big"}
	name = rules.clean_name(up.filename or "file") or "file"
	folder = l.file_key.rstrip("/") + "/"
	stem, dot, ext = name.rpartition(".") if "." in name else (name, "", "")
	n, final = 1, name
	while store.head(folder + final):
		n += 1
		final = f"{stem} ({n}).{ext}" if dot else f"{name} ({n})"
	parts = l.file_key.split("/")
	root = "/".join(parts[:3]) + "/" if len(parts) > 2 and parts[1] == "people" else "/".join(parts[:2]) + "/"
	quota = None
	from qtt_platform.api.workplace import _quota_gb

	quota = _quota_gb(l.space)
	if not rules.fits(store.used(root), quota, len(data)):
		return {"state": "full"}
	store.write(folder + final, data, up.mimetype or mimetypes.guess_type(final)[0])
	core.index_later(folder + final)
	core.automate(l.tenant, "upload", folder + final, l.created_by or "")
	frappe.db.set_value(LINK, l.name, "uploads", (l.uploads or 0) + 1, update_modified=False)
	who = c.get("e") or "guest"
	core.log(l.tenant, folder + final, l.space, f"{l.path}/{final}", "link_upload", who, link=l.name, detail=final)
	frappe.db.commit()
	try:
		from qtt_platform.push import notify

		notify([l.created_by], title=_("A file arrived in {0}").format(_title(l.file_key)), body=final, data={"kind": "files", "tenant": l.tenant, "space": l.space, "path": l.path})
	except Exception:
		pass
	return {"state": "ok", "name": final}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def page(k: str = "", id: str = ""):
	"""The page someone opens from a share link (app.queentouchtech.in/s/<key> or /sl/<id>)."""
	from qtt_platform.files_page import html

	r = Response(html(k=k, id=id), mimetype="text/html")
	r.headers["Cache-Control"] = "no-store"
	r.headers["Referrer-Policy"] = "no-referrer"
	r.headers["X-Robots-Tag"] = "noindex, nofollow"
	return r
