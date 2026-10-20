"""
Team calls and the Office Pulse Workplace (PROJ-0014 / PROJ-0015) — the rules, pure (no Frappe; tests/test_workplace.py).

  Calls        LiveKit (self-hosted, meet.queentouchtech.in): a call's room is the chat's id; a person joins with a
               short token naming what they may send — microphone and camera for everyone, screen sharing only with
               Office Pulse. LiveKit tells Frappe what happened (signed webhooks): who joined / left, when it ended.
  Files        One private S3 bucket (Garage on QTT-AI-OS, reached only by Frappe): each business's spaces are folders
               in it (space_prefix) — Team files, Company, HR, each person's own files; Frappe decides who may see
               and change what, and keeps the quotas. Deleted and replaced files go to a trash for 30 days.
  Documents    OnlyOffice Document Server (office.queentouchtech.in), talked to directly: a signed editor set-up
               (editor_config) and a signed save call back to Frappe.
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
TRASH = "trash/"  # trash/<YYYY-MM-DD>/<key>: deleted and replaced files, kept TRASH_DAYS
TRASH_DAYS = 30
SPACES = ("team", "mine", "company", "hr", "mydocs")


def person_id(user: str) -> str:
	"""A short, stable id for a person's own folder (not their e-mail in the store)."""
	return hashlib.sha1(str(user).strip().lower().encode()).hexdigest()[:12]


def space_prefix(tenant: str, space: str, user: str = "", hr_folder: str = "") -> str:
	"""Where a space starts in the bucket: <business>/team/, /company/, /hr/, /people/<person>/; an employee's
	"My documents from HR" is their folder inside HR (\"\" when HR hasn't made one)."""
	t = re.sub(r"[^A-Za-z0-9_-]", "", str(tenant or ""))
	if not t:
		raise ValueError("tenant")
	if space == "mine":
		return f"{t}/people/{person_id(user)}/"
	if space == "mydocs":
		return f"{t}/hr/{clean_path(hr_folder)}/" if clean_path(hr_folder) else ""
	if space in ("team", "company", "hr"):
		return f"{t}/{space}/"
	raise ValueError(space)


def object_key(prefix: str, path: str = "") -> str:
	"""A file's key: the space's prefix + its cleaned path (never outside the space)."""
	return prefix + clean_path(path)


def listing(prefix: str, folders: list[str], files: list[dict]) -> list[dict]:
	"""One folder of an S3 listing (Delimiter "/") → items, folders first: name, is_dir, size, modified, type.
	folders: CommonPrefixes; files: Contents ({Key, Size, LastModified}) — the folder's own marker is left out."""
	out = []
	for f in folders:
		name = f[len(prefix):].strip("/")
		if name and "/" not in name:
			out.append({"name": name, "is_dir": True, "size": 0, "modified": None, "type": "folder"})
	for o in files:
		name = str(o.get("Key", ""))[len(prefix):]
		if not name or "/" in name:
			continue  # the folder's marker, or something deeper
		mod = o.get("LastModified")
		if hasattr(mod, "astimezone"):
			mod = mod.astimezone().replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
		out.append({"name": name, "is_dir": False, "size": int(o.get("Size") or 0), "modified": mod, "type": kind_of_file(name)})
	out.sort(key=lambda i: (not i["is_dir"], i["name"].lower()))
	return out


def trash_key(key: str, day: str) -> str:
	return f"{TRASH}{day}/{key}"


def trash_days_to_purge(days: list[str], today: str) -> list[str]:
	"""The trash's day folders older than TRASH_DAYS (YYYY-MM-DD strings)."""
	from datetime import date, timedelta

	cut = (date.fromisoformat(today) - timedelta(days=TRASH_DAYS)).isoformat()
	return sorted(d for d in days if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d < cut)


def fits(used: int, quota_gb: int | None, adding: int) -> bool:
	return not quota_gb or used + adding <= quota_gb * 1024 ** 3


def free_bytes(used: int, quota_gb: int | None) -> int | None:
	return None if not quota_gb else max(0, quota_gb * 1024 ** 3 - used)


# ---- documents (OnlyOffice) --------------------------------------------------------------------------------------------
def doc_key(key: str, etag: str) -> str:
	"""OnlyOffice's document key: the same while the file is unchanged (so people edit together), new once saved."""
	return hashlib.sha256(f"{key}|{etag}".encode()).hexdigest()[:40]


def editor_config(*, name: str, key: str, etag: str, file_url: str, callback_url: str, can_edit: bool, user_id: str,
				  user_name: str, lang: str = "en", allow_download: bool = True) -> dict:
	"""The editor's set-up (signed with the OnlyOffice secret before it goes to the page)."""
	e = ext(name)
	kind = OFFICE_TYPES.get(e, ("", "word"))[1]
	edit = bool(can_edit) and kind != "pdf"
	return {
		"document": {"fileType": e, "key": doc_key(key, etag), "title": name[:120], "url": file_url,
					 "permissions": {"edit": edit, "download": bool(allow_download), "print": bool(allow_download), "copy": bool(allow_download),
									 "comment": edit}},
		"documentType": kind,
		"editorConfig": {"mode": "edit" if edit else "view", "callbackUrl": callback_url, "lang": lang or "en",
						 "user": {"id": user_id, "name": user_name[:60]},
						 "customization": {"forcesave": True, "compactHeader": True, "hideRightMenu": True}},
	}


SAVE_STATUSES = (2, 6)  # 2: everyone closed it — save; 6: saved by a person (Ctrl+S)


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
