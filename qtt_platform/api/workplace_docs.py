"""
Office Pulse documents: OnlyOffice Document Server (office.queentouchtech.in), talked to directly — no Nextcloud.

  editor_link   (workplace.open_doc) a link to the editor page for this person and file, good for a few hours
  editor        the page the app shows: OnlyOffice's editor with a set-up signed with the OnlyOffice secret
  file          OnlyOffice fetches the file here (a signed link, a few hours) — the store itself stays private
  saved         OnlyOffice's save call: checked with the OnlyOffice secret; the new file replaces the old one (the old
                one stays in the trash for 30 days)

The links carry a token signed with the site's own key: which file, who, whether they may edit, until when.
"""

import json
import secrets
import time
from html import escape

import frappe
import requests
from frappe import _
from werkzeug.wrappers import Response

from qtt_platform import file_store as store
from qtt_platform import workplace_rules as rules

SETTINGS = "QTT Workplace Settings"
LINK_TTL = 6 * 3600  # the editor page and its file link
SAVE_TTL = 7 * 24 * 3600  # OnlyOffice may save a while after the page closed


def _site_secret() -> str:
	from frappe.utils.password import get_encryption_key

	return "qtt-docs|" + get_encryption_key()


def _sign(claims: dict, ttl: int) -> str:
	return rules.jwt_hs256({**claims, "exp": int(time.time()) + ttl}, _site_secret())


def _check(token: str) -> dict:
	claims = rules.jwt_verify(token, _site_secret())
	if not claims:
		raise frappe.PermissionError
	return claims


def _office() -> tuple[str, str]:
	s = frappe.get_cached_doc(SETTINGS)
	secret = s.get_password("onlyoffice_jwt", raise_exception=False)
	if not s.onlyoffice_url or not secret:
		frappe.throw(_("Documents aren't set up yet."))
	return s.onlyoffice_url.rstrip("/"), secret


def _api(method: str, **params) -> str:
	from urllib.parse import urlencode

	return frappe.utils.get_url(f"/api/method/qtt_platform.api.workplace_docs.{method}?{urlencode(params)}")


def editor_link(ctx, key: str, name: str, etag: str, can_edit: bool) -> str:
	"""A link to the editor page: its set-up is made now (the person's name and language, what they may do)."""
	base, secret = _office()
	who = {"k": key, "u": ctx.user, "w": 1 if can_edit else 0}
	from qtt_platform.api import team

	names = team._names(ctx)
	cfg = rules.editor_config(name=name, key=key, etag=etag, file_url=_api("file", t=_sign(who, LINK_TTL)),
							  callback_url=_api("saved", t=_sign({**who, "e": etag}, SAVE_TTL)), can_edit=can_edit,
							  user_id=rules.person_id(ctx.user), user_name=names.get(ctx.user) or frappe.db.get_value("User", ctx.user, "full_name") or ctx.user,
							  lang=(frappe.db.get_value("User", ctx.user, "language") or "en")[:2])
	cfg["token"] = rules.jwt_hs256(cfg, secret)
	page = secrets.token_urlsafe(24)
	frappe.cache().set_value(f"qtt_doc_page|{page}", json.dumps({"cfg": cfg, "base": base}), expires_in_sec=LINK_TTL)
	return _api("editor", p=page)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def editor(p: str = ""):
	"""The editor page the app opens (a link made by open_doc for one person, a few hours)."""
	raw = frappe.cache().get_value(f"qtt_doc_page|{p}") if p else None
	if not raw:
		return Response("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><body style='font:16px sans-serif;padding:24px'>"
						"This link has ended — open the document again from Files.</body>", status=410, mimetype="text/html")
	d = json.loads(raw)
	cfg = json.dumps(d["cfg"]).replace("</", "<\\/")
	html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>{escape(d["cfg"]["document"]["title"])}</title>
<style>html,body{{margin:0;height:100%;background:#0b1220}}#ed{{height:100%}}</style></head>
<body><div id="ed"></div>
<script src="{escape(d["base"])}/web-apps/apps/api/documents/api.js"></script>
<script>
var cfg = {cfg};
cfg.type = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) ? "mobile" : "desktop";
cfg.width = "100%"; cfg.height = "100%";
new DocsAPI.DocEditor("ed", cfg);
</script></body></html>"""
	r = Response(html, mimetype="text/html")
	r.headers["Cache-Control"] = "no-store"
	r.headers["Referrer-Policy"] = "no-referrer"
	return r


@frappe.whitelist(allow_guest=True, methods=["GET"])
def file(t: str = ""):
	"""The file, for OnlyOffice (a signed link from editor_link)."""
	try:
		claims = _check(t)
	except frappe.PermissionError:
		return Response("forbidden", status=403)
	data = store.read(claims["k"])
	r = Response(data, mimetype="application/octet-stream")
	r.headers["Cache-Control"] = "no-store"
	return r


def _ok(error: int = 0) -> Response:
	return Response(json.dumps({"error": error}), mimetype="application/json")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def saved(t: str = ""):
	"""OnlyOffice's call: the document's state. On "save" (2) or "saved by a person" (6) the new file replaces the old
	one. Only a call signed with the OnlyOffice secret is believed; the new file is fetched only from OnlyOffice."""
	try:
		who = _check(t)
	except frappe.PermissionError:
		return _ok(1)
	base, secret = _office()
	try:
		body = json.loads(frappe.request.get_data() or b"{}")
	except ValueError:
		return _ok(1)
	signed = rules.jwt_verify(body.get("token") or frappe.get_request_header("Authorization") or "", secret)
	if not signed:
		return _ok(1)
	data = signed.get("payload") if isinstance(signed.get("payload"), dict) else signed
	status = int(data.get("status") or 0)
	if status not in rules.SAVE_STATUSES:
		return _ok(0)
	if not who.get("w"):
		return _ok(1)  # opened read-only: never written back
	url = str(data.get("url") or "")
	if not url.startswith(base + "/"):
		frappe.log_error(title="Documents: save from an unexpected address", message=url[:300])
		return _ok(1)
	try:
		r = requests.get(url, timeout=120)
		r.raise_for_status()
		frappe.set_user("Administrator")  # a guest call; the store write is the system's
		store.write(who["k"], r.content)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="Documents: couldn't save the edited file")
		return _ok(1)
	return _ok(0)
