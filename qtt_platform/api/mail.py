"""
Office Pulse Mail (PROJ-0016 C3; rules in mail_rules.py): each person's own mailbox in the app — the mail stays on
their mail server (IMAP to read, SMTP to send); QTT keeps only the settings and the password, encrypted.

  account / connect / disconnect      the settings (guessed from the address), checked by signing in before saving
  folders                             the mailbox's folders with unread counts
  messages                            a page of a folder (newest first), or a search (the server searches)
  message / attachment / to_files     read one (marked read); an attachment, or saved into Files
  send                                new, reply, reply all, forward — with attachments; a copy goes to their Sent folder
  act                                 read / unread, flag, move, delete (to their Trash)
"""

import imaplib
import re
import smtplib
import socket
import ssl

import frappe
from frappe import _
from frappe.utils import now_datetime

from qtt_platform import mail_rules as mr

ACCOUNT = "QTT Mail Account"
TIMEOUT = 25
PAGE = 30
MAX_ATTACH = 20 * 1024 * 1024


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


def _acc(ctx, need: bool = True):
	name = frappe.db.get_value(ACCOUNT, {"tenant": ctx.tenant, "user": ctx.user})
	if not name:
		if need:
			frappe.throw(_("Connect your mailbox first."))
		return None
	return frappe.get_doc(ACCOUNT, name)


# ---- connections -------------------------------------------------------------------------------------------------------
IMAP_PORTS, SMTP_PORTS = (993,), (465, 587, 2525, 25)


def _safe(host: str, port: int, ports: tuple) -> None:
	"""Only real mail servers: mail ports, and never an address inside QTT's own networks (the server would otherwise
	connect wherever a person points it)."""
	import ipaddress

	if int(port or 0) not in ports:
		frappe.throw(_("Use the mail port {0}.").format(" / ".join(str(p) for p in ports)))
	try:
		addrs = {i[4][0] for i in socket.getaddrinfo(str(host or ""), int(port), proto=socket.IPPROTO_TCP)}
	except OSError:
		frappe.throw(_("Couldn't find the mail server {0}.").format(host))
	for ip in addrs:
		x = ipaddress.ip_address(ip.split("%")[0])
		if x.is_private or x.is_loopback or x.is_link_local or x.is_reserved or x.is_multicast or x.is_unspecified:
			frappe.throw(_("That mail server address can't be used."))


def _imap(a, password: str | None = None) -> imaplib.IMAP4_SSL:
	_safe(a.imap_host, int(a.imap_port or 993), IMAP_PORTS)
	try:
		c = imaplib.IMAP4_SSL(a.imap_host, int(a.imap_port or 993), ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
		c.login(a.login or a.email, password if password is not None else a.get_password("password"))
		return c
	except imaplib.IMAP4.error:
		frappe.throw(_("Your mail server refused the email or password. (Gmail, Outlook and Yahoo need an app password.)"))
	except (OSError, socket.timeout, ssl.SSLError):
		frappe.throw(_("Couldn't reach {0} — check the server name and port.").format(a.imap_host))


def _smtp(a, password: str | None = None):
	_safe(a.smtp_host, int(a.smtp_port or 465), SMTP_PORTS)
	try:
		port = int(a.smtp_port or 465)
		if a.smtp_starttls or port == 587:
			s = smtplib.SMTP(a.smtp_host, port, timeout=TIMEOUT)
			s.starttls(context=ssl.create_default_context())
		else:
			s = smtplib.SMTP_SSL(a.smtp_host, port, context=ssl.create_default_context(), timeout=TIMEOUT)
		s.login(a.login or a.email, password if password is not None else a.get_password("password"))
		return s
	except smtplib.SMTPAuthenticationError:
		frappe.throw(_("Your mail server refused to send with this email and password."))
	except (OSError, socket.timeout, ssl.SSLError, smtplib.SMTPException):
		frappe.throw(_("Couldn't reach {0} to send — check the server name and port.").format(a.smtp_host))


def _q(name: str) -> str:
	"""A folder name for an IMAP command (encoded and quoted)."""
	return '"' + mr.folder_encode(name).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _select(c, folder: str, readonly: bool = True) -> None:
	typ, _d = c.select(_q(folder), readonly=readonly)
	if typ != "OK":
		frappe.throw(_("That folder isn't there any more."), frappe.DoesNotExistError)


def _logout(c) -> None:
	try:
		c.logout()
	except Exception:
		pass


# ---- the account -------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def account(email: str = "") -> dict:
	"""This person's mailbox settings (never the password) — or suggested settings for an address."""
	ctx = _ctx()
	a = _acc(ctx, need=False)
	if a:
		return {"connected": True, "email": a.email, "display_name": a.display_name or "", "login": a.login or "", "imap_host": a.imap_host,
				"imap_port": a.imap_port, "smtp_host": a.smtp_host, "smtp_port": a.smtp_port, "smtp_starttls": bool(a.smtp_starttls),
				"signature": a.signature or "", "checked": str(a.verified_at or "")}
	from qtt_platform.api.team import _names

	return {"connected": False, "email": email, "display_name": _names(ctx).get(ctx.user, ""), **(mr.guess(email) if email else {})}


@frappe.whitelist(methods=["POST"])
def connect(data=None) -> dict:
	"""Connect (or change) your mailbox. data: {email, password (empty: keep the saved one), display_name, login,
	imap_host, imap_port, smtp_host, smtp_port, smtp_starttls, signature}. Signs in to both servers before saving."""
	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	email = str(d.get("email") or "").strip().lower()
	if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
		frappe.throw(_("Enter your email address."))
	g = mr.guess(email)
	a = _acc(ctx, need=False) or frappe.get_doc({"doctype": ACCOUNT, "tenant": ctx.tenant, "user": ctx.user})
	a.email = email
	a.display_name = str(d.get("display_name") or "").strip()[:80]
	a.login = str(d.get("login") or "").strip()[:200] or email
	a.imap_host = str(d.get("imap_host") or g["imap_host"]).strip()[:120]
	a.imap_port = int(d.get("imap_port") or g["imap_port"])
	a.smtp_host = str(d.get("smtp_host") or g["smtp_host"]).strip()[:120]
	a.smtp_port = int(d.get("smtp_port") or g["smtp_port"])
	a.smtp_starttls = 1 if str(d.get("smtp_starttls", g["smtp_starttls"])).lower() in ("1", "true") else 0
	a.signature = str(d.get("signature") or "")[:1000]
	pw = str(d.get("password") or "")
	if not pw and a.name:
		pw = a.get_password("password")
	if not pw:
		frappe.throw(_("Enter the password (or app password) for this mailbox."))
	c = _imap(a, pw)
	_logout(c)
	s = _smtp(a, pw)
	s.quit()
	a.password = pw
	a.verified_at = now_datetime()
	a.save(ignore_permissions=True)
	return account()


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	"""Remove your mailbox from QTT (your mail stays on your mail server)."""
	ctx = _ctx()
	a = _acc(ctx, need=False)
	if a:
		frappe.delete_doc(ACCOUNT, a.name, ignore_permissions=True, force=True)
	return {"connected": False}


# ---- reading -----------------------------------------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def folders() -> dict:
	"""The mailbox's folders (Inbox, Sent, Drafts, Trash, Spam first) with unread counts."""
	ctx = _ctx()
	a = _acc(ctx)
	c = _imap(a)
	try:
		typ, rows = c.list()
		out = []
		for r in rows or []:
			f = mr.parse_list_line(r.decode("utf-8", "replace") if isinstance(r, bytes) else str(r))
			if not f or not f["selectable"]:
				continue
			if f["raw"].upper() == "INBOX":
				f["role"], f["name"] = "inbox", "INBOX"
			try:
				_t, st = c.status(_q(f["name"]), "(UNSEEN)")
				f["unread"] = int(re.search(rb"UNSEEN (\d+)", st[0]).group(1))
			except Exception:
				f["unread"] = 0
			out.append({"name": f["name"], "role": f["role"], "unread": f["unread"]})
		order = {"inbox": 0, "sent": 2, "drafts": 1, "junk": 4, "trash": 5, "archive": 3}
		out.sort(key=lambda f: (order.get(f["role"], 9), f["name"].lower()))
		return {"folders": out, "email": a.email}
	finally:
		_logout(c)


def _header_rows(c, uids: list[bytes]) -> list[dict]:
	if not uids:
		return []
	typ, data = c.uid("fetch", b",".join(uids), "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE CONTENT-TYPE)])")
	out = []
	for item in data or []:
		if not isinstance(item, tuple):
			continue
		meta, head = item[0].decode("utf-8", "replace"), item[1]
		uid = re.search(r"UID (\d+)", meta)
		flags = re.search(r"FLAGS \(([^)]*)\)", meta)
		h = mr.read(head)
		ctype = re.search(rb"Content-Type:\s*([^;\r\n]+)", head, flags=re.I)
		out.append({"uid": uid.group(1) if uid else "", "from": h["from"][0] if h["from"] else {"name": "", "email": ""}, "to": h["to"],
					"subject": h["subject"] or "", "date": h["date"], "seen": "\\Seen" in (flags.group(1) if flags else ""),
					"flagged": "\\Flagged" in (flags.group(1) if flags else ""),
					"attachments": bool(ctype and ctype.group(1).strip().lower() == b"multipart/mixed")})
	out.sort(key=lambda r: int(r["uid"] or 0), reverse=True)
	return out


@frappe.whitelist(methods=["GET"])
def messages(folder: str = "INBOX", page: int = 0, q: str = "") -> dict:
	"""A page of a folder, newest first (30 at a time) — or what matches q (the mail server searches subject, people and text)."""
	ctx = _ctx()
	a = _acc(ctx)
	c = _imap(a)
	try:
		_select(c, folder)
		q = str(q or "").strip()[:100]
		if q:
			typ, data = c.uid("search", "CHARSET", "UTF-8", "TEXT", q.encode("utf-8"))
			if typ != "OK":
				typ, data = c.uid("search", None, "TEXT", '"' + q.encode("ascii", "ignore").decode().replace('"', "") + '"')
		else:
			typ, data = c.uid("search", None, "ALL")
		uids = (data[0] or b"").split() if typ == "OK" and data else []
		uids.reverse()
		p = max(0, int(page or 0))
		chunk = uids[p * PAGE:(p + 1) * PAGE]
		return {"messages": _header_rows(c, chunk), "total": len(uids), "page": p, "has_more": len(uids) > (p + 1) * PAGE, "folder": folder}
	finally:
		_logout(c)


def _raw(c, uid: str) -> bytes:
	typ, data = c.uid("fetch", str(uid).encode(), "(BODY.PEEK[])")
	for item in data or []:
		if isinstance(item, tuple):
			return item[1]
	frappe.throw(_("That message isn't there any more."), frappe.DoesNotExistError)


@frappe.whitelist(methods=["GET"])
def message(folder: str, uid: str) -> dict:
	"""One message (marked read): who, when, the text and safe HTML, attachments."""
	ctx = _ctx()
	a = _acc(ctx)
	c = _imap(a)
	try:
		_select(c, folder, readonly=False)
		raw = _raw(c, uid)
		c.uid("store", str(uid).encode(), "+FLAGS", "(\\Seen)")
		r = mr.read(raw)
		if not r["text"] and r["html"]:
			r["text"] = mr.text_of_html(r["html"])
		return {**r, "uid": str(uid), "folder": folder, "me": a.email}
	finally:
		_logout(c)


@frappe.whitelist(methods=["GET"])
def attachment(folder: str, uid: str, index: int):
	"""An attachment's bytes (to open or save)."""
	ctx = _ctx()
	a = _acc(ctx)
	c = _imap(a)
	try:
		_select(c, folder)
		got = mr.attachment(_raw(c, uid), int(index))
	finally:
		_logout(c)
	if not got:
		frappe.throw(_("That attachment isn't there any more."), frappe.DoesNotExistError)
	frappe.local.response.filename = got[0]
	frappe.local.response.filecontent = got[2]
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(methods=["POST"])
def to_files(folder: str, uid: str, index: int, space: str = "mine", path: str = "") -> dict:
	"""Save an attachment into Files (your files by default) — kept as a version if the name is already there."""
	from qtt_platform import files_core as core
	from qtt_platform import workplace_rules as rules
	from qtt_platform.api.workplace import _at, _quota_gb, _quota_root

	ctx = _ctx()
	a = _acc(ctx)
	c = _imap(a)
	try:
		_select(c, folder)
		got = mr.attachment(_raw(c, uid), int(index))
	finally:
		_logout(c)
	if not got:
		frappe.throw(_("That attachment isn't there any more."), frappe.DoesNotExistError)
	name, ctype, data = got
	at = _at(ctx, space, path)
	core.need(at, "create")
	from qtt_platform import file_store as store

	if not rules.fits(store.used(_quota_root(at)), _quota_gb(space), len(data)):
		frappe.throw(_("This space is full — delete something, or ask QTT for more room."))
	name = rules.clean_name(name) or "attachment"
	base = at.key if at.path else at.prefix
	key = (base.rstrip("/") + "/" if base else "") + name
	core.save(ctx.tenant, key, data, ctx.user, ctype)
	core.log(ctx.tenant, key, space, "/".join(p for p in (at.path, name) if p), "upload", ctx.user, detail="from mail")
	core.automate(ctx.tenant, "upload", key, ctx.user)
	return {"space": space, "path": at.path, "name": name}


# ---- writing -----------------------------------------------------------------------------------------------------------
def _sent_folder(c) -> str | None:
	typ, rows = c.list()
	for r in rows or []:
		f = mr.parse_list_line(r.decode("utf-8", "replace") if isinstance(r, bytes) else str(r))
		if f and f["role"] == "sent" and f["selectable"]:
			return f["name"]
	return None


@frappe.whitelist(methods=["POST"])
def send(data=None) -> dict:
	"""Send mail. data: {to, cc, bcc, subject, text, reply: {folder, uid, all} or forward: {folder, uid}}; files: multipart
	`files` (up to 20 MB together). A forward carries the original's attachments. A copy goes into the Sent folder."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	a = _acc(ctx)
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	to, cc, bcc = mr.clean_list(d.get("to")), mr.clean_list(d.get("cc")), mr.clean_list(d.get("bcc"))
	if not (to or cc or bcc):
		frappe.throw(_("Add who it's for."))
	subject = str(d.get("subject") or "").strip()[:250]
	text = str(d.get("text") or "")[:200000]
	files, size = [], 0
	for up in (frappe.request.files.getlist("files") if frappe.request and frappe.request.files else []):
		blob = up.stream.read(MAX_ATTACH + 1)
		size += len(blob)
		if size > MAX_ATTACH:
			frappe.throw(_("Attachments can be up to 20 MB together."))
		files.append((up.filename or "file", up.mimetype or "application/octet-stream", blob))
	in_reply, refs = "", ""
	src = d.get("reply") or d.get("forward")
	c = _imap(a)
	try:
		if src:
			_select(c, src.get("folder") or "INBOX")
			raw = _raw(c, src.get("uid"))
			orig = mr.read(raw)
			if d.get("reply"):
				in_reply, refs = orig["message_id"], orig["references"]
				subject = subject or mr.reply_subject(orig["subject"])
				quote = "\n\n" + _("On {0}, {1} wrote:").format(orig["date"], (orig["from"][0]["name"] or orig["from"][0]["email"]) if orig["from"] else "") + "\n" + "\n".join("> " + l for l in (orig["text"] or "").splitlines()[:400])
				text += quote
			else:
				subject = subject or mr.reply_subject(orig["subject"], forward=True)
				text += "\n\n---------- " + _("Forwarded message") + " ----------\n" + _("From: {0}").format(", ".join(x["email"] for x in orig["from"])) + "\n" + \
						_("Date: {0}").format(orig["date"]) + "\n" + _("Subject: {0}").format(orig["subject"]) + "\n\n" + (orig["text"] or "")
				for att in orig["attachments"]:
					got = mr.attachment(raw, att["index"])
					if got and size + len(got[2]) <= MAX_ATTACH:
						size += len(got[2])
						files.append(got)
		msg = mr.compose(from_email=a.email, from_name=a.display_name or _names(ctx).get(ctx.user, ""), to=to, cc=cc, bcc=bcc, subject=subject or _("(no subject)"),
						 text=text, signature=a.signature or "", in_reply_to=in_reply, references=refs, attachments=files)
		s = _smtp(a)
		try:
			s.send_message(msg)
		finally:
			try:
				s.quit()
			except Exception:
				pass
		if d.get("reply") and src:
			try:
				_select(c, src.get("folder") or "INBOX", readonly=False)
				c.uid("store", str(src.get("uid")).encode(), "+FLAGS", "(\\Answered)")
			except Exception:
				pass
		sent = _sent_folder(c)
		if sent and "gmail.com" not in (a.imap_host or ""):  # Gmail files sent mail itself
			try:
				del msg["Bcc"]
				c.append(_q(sent), "(\\Seen)", imaplib.Time2Internaldate(now_datetime().timestamp()), msg.as_bytes())
			except Exception:
				pass
	finally:
		_logout(c)
	return {"sent": True}


@frappe.whitelist(methods=["POST"])
def act(folder: str, uids, action: str, to: str = "") -> dict:
	"""On messages: read | unread | flag | unflag | delete (to Trash; in Trash, for good) | move (to a folder)."""
	ctx = _ctx()
	a = _acc(ctx)
	ids = [str(u) for u in (frappe.parse_json(uids) if isinstance(uids, str) and uids.strip().startswith("[") else str(uids).split(",")) if str(u).strip().isdigit()]
	if not ids or action not in ("read", "unread", "flag", "unflag", "delete", "move"):
		frappe.throw(_("Choose messages and what to do."))
	c = _imap(a)
	try:
		_select(c, folder, readonly=False)
		seq = ",".join(ids).encode()
		if action in ("read", "unread"):
			c.uid("store", seq, "+FLAGS" if action == "read" else "-FLAGS", "(\\Seen)")
		elif action in ("flag", "unflag"):
			c.uid("store", seq, "+FLAGS" if action == "flag" else "-FLAGS", "(\\Flagged)")
		else:
			target = to
			if action == "delete":
				typ, rows = c.list()
				trash = next((f["name"] for f in (mr.parse_list_line(r.decode("utf-8", "replace")) for r in rows or []) if f and f["role"] == "trash"), None)
				target = None if (not trash or trash == folder) else trash
			if target:
				typ, _d = c.uid("move", seq, _q(target)) if b"MOVE" in b" ".join(c.capabilities) else ("NO", None)
				if typ != "OK":
					c.uid("copy", seq, _q(target))
					c.uid("store", seq, "+FLAGS", "(\\Deleted)")
					c.expunge()
			else:
				c.uid("store", seq, "+FLAGS", "(\\Deleted)")
				c.expunge()
		return {"ok": True}
	finally:
		_logout(c)
