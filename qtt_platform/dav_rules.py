"""
Office Pulse Files over WebDAV (PROJ-0016 E2; api/dav.py, the gateway in ops/dav_gateway) — the pure rules: the
folders a computer or phone sees, sync passwords, desktop clutter. No Frappe here (tests/test_dav.py).

  /Team files/…   /My files/…   /Company/…   /HR/… (HR and owners)   /From HR/…   /Shared with me/<name>/…
"""

import hashlib
import hmac
import re
import secrets

# what the folder is called on the computer → the Files space
SPACES = {"Team files": "team", "My files": "mine", "Company": "company", "HR": "hr", "From HR": "mydocs", "Shared with me": "shared"}
NAMES = {v: k for k, v in SPACES.items()}

# what desktops write next to every file — never stored
JUNK = re.compile(r"^(\._.*|\.DS_Store|\.localized|Thumbs\.db|desktop\.ini|\.~lock\..*#|~\$.*|\.TemporaryItems|\.Trashes|\.fseventsd|\.Spotlight-V100)$", re.I)

PBKDF2_ROUNDS = 120_000
PASSWORD_GROUPS = 4  # xxxx-xxxx-xxxx-xxxx


def split(dav_path: str) -> tuple[str, str]:
	"""'/Team files/Plans/a.xlsx' → ('team', 'Plans/a.xlsx'); '/' → ('', ''). An unknown top folder → ('?', '')."""
	parts = [p for p in (dav_path or "").replace("\\", "/").split("/") if p and p != "."]
	if any(p == ".." for p in parts):
		raise ValueError("bad path")
	if not parts:
		return "", ""
	space = SPACES.get(parts[0])
	if not space:
		return "?", ""
	return space, "/".join(parts[1:])


def join(space: str, path: str) -> str:
	return "/" + "/".join(p for p in (NAMES[space], path) if p)


def top_folders(hr: bool) -> list[str]:
	"""The folders at the top, in order (HR only for HR people, owners and admins)."""
	return [n for n, s in SPACES.items() if s != "hr" or hr]


def is_junk(name: str) -> bool:
	return bool(JUNK.match(name or ""))


def new_password() -> str:
	"""A sync password to type once into a computer or phone: four groups of four, no look-alike letters."""
	alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
	return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(PASSWORD_GROUPS))


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
	"""(hash, salt) — only these are kept."""
	salt = salt or secrets.token_hex(16)
	h = hashlib.pbkdf2_hmac("sha256", normalise(password).encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
	return h, salt


def check_password(password: str, stored_hash: str, salt: str) -> bool:
	return hmac.compare_digest(hash_password(password, salt)[0], stored_hash or "")


def normalise(password: str) -> str:
	"""Typed with or without the dashes, in any case, with stray spaces."""
	return re.sub(r"[\s-]", "", password or "").lower()


def hint(password: str) -> str:
	return "…" + normalise(password)[-4:]


def unique_names(names: list[str]) -> list[str]:
	"""Two shares called the same get ' (2)', ' (3)' so each has its own folder."""
	seen, out = {}, []
	for n in names:
		k = n.lower()
		seen[k] = seen.get(k, 0) + 1
		if seen[k] == 1:
			out.append(n)
		else:
			stem, dot, ext = n.rpartition(".") if "." in n.strip(".") else (n, "", "")
			out.append(f"{stem} ({seen[k]}){dot}{ext}" if dot else f"{n} ({seen[k]})")
	return out
