"""
Office Pulse Files — sharing and file control (PROJ-0016 A), the rules, pure (no Frappe; tests/test_files.py).

  rights        what a person may do in a space / folder: read, write, create, delete, share
                  space defaults → folder rules (deepest matching folder; a person's rule beats a role's, a role's
                  beats everyone's) → a lock by someone else takes write / delete away
  shares        a file or folder shared with a person: view (read) or edit (read, write, create, delete)
  links         a secret key per link (only its hash is kept), optional password, expiry, view / download limits,
                listed emails (a code sent to the email), approval, preview only, upload only (File Drop)
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

RIGHTS = ("read", "write", "create", "delete", "share")
FULL = frozenset(RIGHTS)
SHARE_PERMS = {"view": frozenset({"read"}), "edit": frozenset({"read", "write", "create", "delete"})}
LINK_MODES = ("preview", "download", "upload")  # preview: view only, no download; upload: File Drop
EXPIRY = {"1h": timedelta(hours=1), "1d": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
KEEP_DAYS = 30  # versions and the recycle bin
LOCK_HOURS = 24


# ---- rights ------------------------------------------------------------------------------------------------------------
def space_rights(space: str, *, hr: bool, admin: bool) -> frozenset:
	"""What a space gives before any folder rule."""
	if space in ("team", "mine"):
		return FULL
	if space == "company":
		return FULL if (hr or admin) else frozenset({"read"})
	if space == "hr":
		return FULL if (hr or admin) else frozenset()
	if space == "mydocs":
		return frozenset({"read"})
	return frozenset()


def parse_rights(text: str) -> frozenset:
	return frozenset(r for r in re.split(r"[,\s]+", str(text or "").lower()) if r in RIGHTS)


def folder_rights(base: frozenset, rules: list[dict], path: str, *, user: str, roles: set[str]) -> frozenset:
	"""rules: [{path, who_type: everyone | role | user, who, rights}] of the space. The deepest folder with a rule for
	this person decides (person > role > everyone there); no rule → the space's rights."""
	path = clean(path)
	best, best_depth, best_rank = None, -1, -1
	for r in rules:
		rp = clean(r.get("path"))
		if rp and not (path == rp or path.startswith(rp + "/")):
			continue
		wt = r.get("who_type")
		if wt == "user" and r.get("who") != user:
			continue
		if wt == "role" and r.get("who") not in roles:
			continue
		if wt not in ("user", "role", "everyone"):
			continue
		depth = rp.count("/") + 1 if rp else 0
		rank = {"everyone": 0, "role": 1, "user": 2}[wt]
		if depth > best_depth or (depth == best_depth and rank > best_rank):
			best, best_depth, best_rank = r, depth, rank
	return parse_rights(best["rights"]) if best else base


def without_lock(rights: frozenset, locked_by: str | None, locked_until: datetime | None, user: str, now: datetime) -> frozenset:
	"""A file locked by someone else can be read, not changed."""
	if locked_by and locked_by != user and (not locked_until or locked_until > now):
		return rights - {"write", "delete"}
	return rights


def clean(path) -> str:
	return "/".join(p for p in re.split(r"[\\/]+", str(path or "")) if p and p not in (".", ".."))


# ---- links -------------------------------------------------------------------------------------------------------------
def new_key() -> str:
	"""A link's secret key — random, unguessable (192 bits)."""
	return secrets.token_urlsafe(24)


def key_hash(key: str) -> str:
	return hashlib.sha256(str(key or "").encode()).hexdigest()


def hash_password(pw: str, salt: str | None = None) -> str:
	salt = salt or secrets.token_hex(8)
	return f"{salt}${hashlib.pbkdf2_hmac('sha256', str(pw).encode(), salt.encode(), 120_000).hex()}"


def check_password(pw: str, stored: str) -> bool:
	if not stored or "$" not in stored:
		return False
	salt = stored.split("$", 1)[0]
	return hmac.compare_digest(hash_password(pw, salt), stored)


def expires_at(choice: str, now: datetime, date: str | None = None) -> datetime | None:
	"""1h / 1d / 7d / 30d, a date (end of that day), or never ("")."""
	if choice in EXPIRY:
		return now + EXPIRY[choice]
	if choice == "date" and date:
		d = datetime.fromisoformat(str(date)[:10])
		if d.date() < now.date():
			raise ValueError("past")
		return d.replace(hour=23, minute=59, second=59)
	return None


def emails(text: str) -> list[str]:
	return sorted({e.lower() for e in re.findall(r"[^\s,;<>]+@[^\s,;<>]+\.[^\s,;<>]+", str(text or ""))})


def link_state(link: dict, now: datetime, want: str = "view") -> str:
	"""ok | revoked | expired | used_up (its view / download limit reached) | no (this link can't do that)."""
	if link.get("status") == "Revoked":
		return "revoked"
	exp = link.get("expires_at")
	if exp and exp <= now:
		return "expired"
	mode = link.get("mode")
	if want == "download" and mode != "download":
		return "no"
	if want == "upload" and mode != "upload":
		return "no"
	if want in ("view", "download") and mode == "upload":
		return "no"
	if want == "view" and link.get("max_views") and int(link.get("views") or 0) >= int(link["max_views"]):
		return "used_up"
	if want == "download" and link.get("max_downloads") and int(link.get("downloads") or 0) >= int(link["max_downloads"]):
		return "used_up"
	return "ok"


def needs_email(link: dict) -> bool:
	return bool(link.get("require_approval") or emails(link.get("allowed_emails")))


def email_allowed(link: dict, email: str) -> bool:
	"""With listed emails only those; with approval anyone may ask."""
	listed = emails(link.get("allowed_emails"))
	return (not listed) or str(email or "").strip().lower() in listed


def new_code() -> str:
	return f"{secrets.randbelow(10 ** 6):06d}"
