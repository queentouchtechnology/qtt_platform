"""
Team calls and the Office Pulse Workplace (PROJ-0014 / PROJ-0015) — the rules, pure (no Frappe; tests/test_workplace.py).

  Calls        LiveKit (self-hosted, meet.queentouchtech.in): a call's room is the chat's id; a person joins with a
               short token naming what they may send — microphone and camera for everyone, screen sharing only with
               Office Pulse. LiveKit tells Frappe what happened (signed webhooks): who joined / left, when it ended.
  Files        Nextcloud (cloud.queentouchtech.in): every person a Nextcloud user of their own ("qtt-…"), every
               business a group and a group folder ("Team files", its quota) — plus "Company" (everyone reads, owners /
               admins / HR write) for Office Pulse's company documents. The app reaches them over WebDAV as the person.
  Documents    OnlyOffice Document Server (office.queentouchtech.in), opened through Nextcloud's direct editing.
  Remote       RustDesk ID / relay server (remote.queentouchtech.in): the standard RustDesk app, set to QTT's server.
"""

import base64
import hashlib
import json
import re
import time
from datetime import datetime

PULSE = "QTT_OFFICE_PULSE"
TOKEN_TTL = 6 * 3600
RING_SECONDS = 45

OFFICE_TYPES = {
	"docx": ("Word document", "word"), "doc": ("Word document", "word"), "odt": ("Document", "word"), "rtf": ("Document", "word"),
	"txt": ("Text", "word"),
	"xlsx": ("Excel sheet", "cell"), "xls": ("Excel sheet", "cell"), "ods": ("Spreadsheet", "cell"), "csv": ("CSV", "cell"),
	"pptx": ("PowerPoint", "slide"), "ppt": ("PowerPoint", "slide"), "odp": ("Presentation", "slide"),
	"pdf": ("PDF", "pdf"),
}
NEW_DOCS = {"word": "docx", "cell": "xlsx", "slide": "pptx"}
IMAGE = ("png", "jpg", "jpeg", "gif", "webp", "heic")


# ---- calls -----------------------------------------------------------------------------------------------------------
def call_sources(screen_share: bool) -> list[str]:
	"""What a person may send in a call: microphone and camera; screen (and its sound) with Office Pulse."""
	return ["microphone", "camera"] + (["screen_share", "screen_share_audio"] if screen_share else [])


def _b64(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def jwt_hs256(claims: dict, secret: str) -> str:
	"""A signed token (HS256) — LiveKit's access tokens and webhook signatures."""
	head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
	body = _b64(json.dumps(claims, separators=(",", ":")).encode())
	import hmac

	sig = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
	return f"{head}.{body}.{_b64(sig)}"


def jwt_verify(token: str, secret: str, now: float | None = None) -> dict | None:
	"""The claims of an HS256 token signed with `secret` that hasn't expired; None otherwise."""
	import hmac

	try:
		head, body, sig = str(token or "").replace("Bearer ", "").strip().split(".")
		want = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
		if not hmac.compare_digest(want, sig):
			return None
		claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
		if claims.get("exp") and float(claims["exp"]) < (now or time.time()):
			return None
		return claims
	except (ValueError, TypeError):
		return None


def call_token(*, key: str, secret: str, room: str, user: str, name: str, screen_share: bool, now: float | None = None,
			   metadata: dict | None = None) -> str:
	now = int(now or time.time())
	return jwt_hs256({
		"iss": key, "sub": user, "nbf": now - 10, "exp": now + TOKEN_TTL, "name": name, "metadata": json.dumps(metadata or {}),
		"video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True, "canPublishData": True,
				  "canPublishSources": call_sources(screen_share)},
	}, secret)


def webhook_ok(body: bytes, auth: str, secret: str) -> bool:
	"""LiveKit signs each webhook: a token whose sha256 claim is the body's hash."""
	claims = jwt_verify(auth, secret)
	if not claims:
		return False
	digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
	return claims.get("sha256") == digest


def call_minutes(started: float | None, ended: float | None) -> int:
	if not started or not ended or ended <= started:
		return 0
	return max(1, round((ended - started) / 60))


def call_summary(video: bool, minutes: int, names: list[str]) -> str:
	"""The line a call leaves in its chat when it ends."""
	kind = "📹 Video call" if video else "📞 Call"
	who = ", ".join(names[:4]) + (f" +{len(names) - 4}" if len(names) > 4 else "")
	if not names:
		return f"{kind} · missed"
	return f"{kind} · {minutes} min · {who}"


# ---- files -----------------------------------------------------------------------------------------------------------
def cloud_user(user: str) -> str:
	"""A person's Nextcloud user name (the same in every business): qtt- and a short, stable hash of their login."""
	return "qtt-" + hashlib.sha1(str(user).strip().lower().encode()).hexdigest()[:12]


def cloud_group(tenant: str, kind: str = "") -> str:
	return f"qtt-{tenant}" + (f"-{kind}" if kind else "")


def folder_name(business: str, kind: str = "team") -> str:
	"""A group folder's name in each member's files: "<Business> · Team files" / "<Business> · Company"."""
	b = re.sub(r"\s+", " ", re.sub(r"[\\/:*?\"<>|]+", " ", str(business or "Business"))).strip()[:60] or "Business"
	return f"{b} · {'Company' if kind == 'company' else 'Team files'}"


def clean_path(path: str | None) -> str:
	"""A path inside one of the person's spaces: no .., no leading / trailing slash, no empty parts."""
	parts = [p for p in re.split(r"[\\/]+", str(path or "")) if p and p not in (".", "..")]
	return "/".join(parts)


def clean_name(name: str) -> str:
	n = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", str(name or "")).strip().strip(".")
	return n[:120]


def ext(name: str) -> str:
	return str(name or "").rsplit(".", 1)[-1].lower() if "." in str(name or "") else ""


def kind_of_file(name: str, is_dir: bool = False) -> str:
	if is_dir:
		return "folder"
	e = ext(name)
	if e in IMAGE:
		return "image"
	if e in OFFICE_TYPES:
		return OFFICE_TYPES[e][1]
	if e in ("mp4", "mov", "webm", "mkv"):
		return "video"
	if e in ("mp3", "wav", "m4a", "ogg", "aac"):
		return "audio"
	if e in ("zip", "rar", "7z"):
		return "archive"
	return "file"


def editable(name: str) -> bool:
	"""Opens in OnlyOffice (Word, Excel, PowerPoint, their open formats, text, CSV, PDF)."""
	return ext(name) in OFFICE_TYPES


def new_doc_name(kind: str, title: str | None) -> str:
	e = NEW_DOCS.get(kind)
	if not e:
		raise ValueError(kind)
	base = clean_name(title or "") or {"word": "Document", "cell": "Sheet", "slide": "Presentation"}[kind]
	return base if base.lower().endswith("." + e) else f"{base}.{e}"


def parse_propfind(xml: str, base: str) -> list[dict]:
	"""WebDAV PROPFIND (depth 1) → the folder's items (not the folder itself): name, path (under `base`), is_dir, size,
	modified (ISO), type, etag, fileid."""
	import xml.etree.ElementTree as ET
	from email.utils import parsedate_to_datetime
	from urllib.parse import unquote

	ns = {"d": "DAV:", "oc": "http://owncloud.org/ns", "nc": "http://nextcloud.org/ns"}
	root = ET.fromstring(xml)
	base = "/" + base.strip("/") + "/"
	out = []
	for r in root.findall("d:response", ns):
		href = unquote(r.findtext("d:href", default="", namespaces=ns))
		if base not in href:
			continue
		rel = href.split(base, 1)[1].strip("/")
		prop = r.find("d:propstat/d:prop", ns)
		if prop is None:
			continue
		is_dir = prop.find("d:resourcetype/d:collection", ns) is not None
		if not rel:
			continue  # the folder itself
		if "/" in rel:
			rel_name = rel.rsplit("/", 1)[-1]
		else:
			rel_name = rel
		mod = prop.findtext("d:getlastmodified", default="", namespaces=ns)
		try:
			mod = parsedate_to_datetime(mod).astimezone().replace(tzinfo=None).isoformat(sep=" ", timespec="seconds") if mod else None
		except (TypeError, ValueError):
			mod = None
		size = prop.findtext("oc:size", default="", namespaces=ns) or prop.findtext("d:getcontentlength", default="0", namespaces=ns)
		out.append({"name": rel_name, "path": rel, "is_dir": is_dir, "size": int(size or 0), "modified": mod,
					"type": kind_of_file(rel_name, is_dir), "fileid": prop.findtext("oc:fileid", default="", namespaces=ns),
					"etag": (prop.findtext("d:getetag", default="", namespaces=ns) or "").strip('"')})
	out.sort(key=lambda i: (not i["is_dir"], i["name"].lower()))
	return out


def human_size(n: int) -> str:
	for unit in ("B", "KB", "MB", "GB"):
		if n < 1024 or unit == "GB":
			return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
		n /= 1024
	return f"{n:.1f} GB"


# ---- remote control (RustDesk) ---------------------------------------------------------------------------------------
def rustdesk_config(host: str, key: str) -> str:
	"""The string RustDesk's "Import server config" takes (what its "Export server config" makes): the settings as
	JSON, base64, reversed."""
	data = json.dumps({"host": host, "relay": host, "api": "", "key": key}, separators=(",", ":"))
	return base64.b64encode(data.encode()).decode().rstrip("=")[::-1]


def rustdesk_id(value: str) -> str | None:
	"""A RustDesk ID as people read it out ("123 456 789") → digits; None when it isn't one (6–12 digits)."""
	digits = re.sub(r"[\s-]", "", str(value or ""))
	return digits if re.fullmatch(r"\d{6,12}", digits) else None


def rustdesk_uri(device_id: str, password: str | None = None) -> str:
	"""Open a remote control session in the RustDesk app on this computer."""
	from urllib.parse import quote

	uri = f"rustdesk://connection/new/{device_id}"
	return uri + (f"?password={quote(password)}" if password else "")


def can_manage_devices(role: str | None, pulse_role: str | None) -> bool:
	"""Owners, admins and HR Admins add / edit Company computers and connect to any of them."""
	return role in ("Tenant Owner", "Tenant Admin") or pulse_role in ("HR Admin",)


def stamp(ts: float | None) -> str | None:
	return datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds") if ts else None
