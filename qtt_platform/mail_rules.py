"""
Office Pulse Mail (PROJ-0016 C3) — the rules, pure (no Frappe; tests/test_mail.py): mail server settings guessed from
the address, reading a message (text, safe HTML, attachments), writing one (with replies kept in their thread), and
IMAP folder names.
"""

import base64
import email
import email.policy
import re
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, make_msgid, parsedate_to_datetime

PRESETS = {
	"gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 465, False),
	"googlemail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 465, False),
	"outlook.com": ("outlook.office365.com", 993, "smtp.office365.com", 587, True),
	"hotmail.com": ("outlook.office365.com", 993, "smtp.office365.com", 587, True),
	"live.com": ("outlook.office365.com", 993, "smtp.office365.com", 587, True),
	"yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 465, False),
	"yahoo.in": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 465, False),
	"zoho.com": ("imap.zoho.com", 993, "smtp.zoho.com", 465, False),
	"zohomail.in": ("imap.zoho.in", 993, "smtp.zoho.in", 465, False),
	"zoho.in": ("imap.zoho.in", 993, "smtp.zoho.in", 465, False),
	"icloud.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587, True),
	"rediffmail.com": ("imap.rediffmail.com", 993, "smtp.rediffmail.com", 465, False),
}
NOTES = {
	"imap.gmail.com": "Gmail needs an app password (Google Account › Security › App passwords) — your usual password won't work.",
	"outlook.office365.com": "Microsoft accounts may need an app password, or IMAP turned on by your admin.",
	"imap.mail.yahoo.com": "Yahoo needs an app password (Account security › Generate app password).",
	"imap.mail.me.com": "iCloud needs an app-specific password (appleid.apple.com).",
}


def guess(address: str) -> dict:
	"""Server settings for an address: a known provider's, else mail.<domain> (most hosting, cPanel / CloudPanel)."""
	domain = str(address or "").rsplit("@", 1)[-1].strip().lower()
	if domain in PRESETS:
		ih, ip, sh, sp, tls = PRESETS[domain]
	else:
		ih, ip, sh, sp, tls = f"mail.{domain}", 993, f"mail.{domain}", 465, False
	return {"imap_host": ih, "imap_port": ip, "smtp_host": sh, "smtp_port": sp, "smtp_starttls": tls, "note": NOTES.get(ih, "")}


def decode(value) -> str:
	if value is None:
		return ""
	try:
		return str(make_header(decode_header(str(value))))
	except Exception:
		return str(value)


def addresses(value) -> list[dict]:
	return [{"name": decode(n), "email": a.lower()} for n, a in getaddresses([decode(value)]) if a]


# ---- reading -----------------------------------------------------------------------------------------------------------
_BAD_TAGS = r"script|iframe|object|embed|form|meta|link|base|style"


def safe_html(html: str) -> tuple[str, bool]:
	"""HTML safe to show: no scripts, frames, forms or event handlers; pictures from the internet held back (they can
	tell the sender you opened it). → (html, had remote pictures)."""
	h = re.sub(rf"<({_BAD_TAGS})\b[^>]*>.*?</\1\s*>", "", str(html or ""), flags=re.I | re.S)
	h = re.sub(rf"<\/?({_BAD_TAGS})\b[^>]*>", "", h, flags=re.I)
	h = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", h, flags=re.I)
	h = re.sub(r"(href|src)\s*=\s*([\"']?)\s*javascript:[^\"'>\s]*\2", r'\1=""', h, flags=re.I)
	remote = bool(re.search(r"<img\b[^>]*\bsrc\s*=\s*[\"']?https?:", h, flags=re.I))
	h = re.sub(r"(<img\b[^>]*?)\bsrc(\s*=\s*[\"']?https?:)", r"\1data-remote-src\2", h, flags=re.I)
	return h, remote


def read(raw: bytes) -> dict:
	"""A message → {subject, from, to, cc, date, message_id, references, text, html, remote_images, attachments:
	[{index, name, type, size, inline_cid}]}. Pictures attached inside the HTML (cid:) are put in place."""
	msg = email.message_from_bytes(raw, policy=email.policy.default)
	text, html, atts, cids = "", "", [], {}
	for part in msg.walk():
		if part.is_multipart():
			continue
		ctype = part.get_content_type()
		disp = part.get_content_disposition()
		name = decode(part.get_filename() or "")
		try:
			payload = part.get_payload(decode=True) or b""
		except Exception:
			payload = b""
		if disp == "attachment" or (name and ctype not in ("text/plain", "text/html")):
			cid = (part.get("Content-ID") or "").strip("<> ")
			atts.append({"index": len(atts), "name": name or f"attachment-{len(atts) + 1}", "type": ctype, "size": len(payload), "inline_cid": cid or None})
			if cid and ctype.startswith("image/") and len(payload) < 2_000_000:
				cids[cid] = f"data:{ctype};base64,{base64.b64encode(payload).decode()}"
			continue
		charset = part.get_content_charset() or "utf-8"
		body = payload.decode(charset, "replace") if isinstance(payload, bytes) else str(payload)
		if ctype == "text/plain" and not text:
			text = body
		elif ctype == "text/html" and not html:
			html = body
	for cid, data in cids.items():
		html = html.replace(f"cid:{cid}", data)
	safe, remote = safe_html(html) if html else ("", False)
	try:
		when = parsedate_to_datetime(msg["Date"]).astimezone().replace(tzinfo=None).isoformat(sep=" ", timespec="minutes") if msg["Date"] else ""
	except Exception:
		when = ""
	return {"subject": decode(msg["Subject"]), "from": addresses(msg["From"]), "to": addresses(msg["To"]), "cc": addresses(msg["Cc"]),
			"reply_to": addresses(msg["Reply-To"]), "date": when, "message_id": (msg["Message-ID"] or "").strip(),
			"references": (msg["References"] or "").strip(), "text": text, "html": safe, "remote_images": remote,
			"attachments": [a for a in atts if not (a["inline_cid"] and a["inline_cid"] in cids and a["type"].startswith("image/"))]}


def attachment(raw: bytes, index: int) -> tuple[str, str, bytes] | None:
	"""The index-th attachment (the same order read() lists them, inline pictures included) → (name, type, bytes)."""
	msg = email.message_from_bytes(raw, policy=email.policy.default)
	n = 0
	for part in msg.walk():
		if part.is_multipart():
			continue
		ctype, name = part.get_content_type(), decode(part.get_filename() or "")
		if part.get_content_disposition() == "attachment" or (name and ctype not in ("text/plain", "text/html")):
			if n == index:
				return name or f"attachment-{n + 1}", ctype, part.get_payload(decode=True) or b""
			n += 1
	return None


def text_of_html(html: str) -> str:
	t = re.sub(r"<(br|/p|/div|/li|/tr)\b[^>]*>", "\n", str(html or ""), flags=re.I)
	t = re.sub(r"<[^>]+>", "", t)
	from html import unescape

	return re.sub(r"\n{3,}", "\n\n", unescape(t)).strip()


# ---- writing -----------------------------------------------------------------------------------------------------------
def reply_subject(subject: str, forward: bool = False) -> str:
	s = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", str(subject or ""), flags=re.I)
	return ("Fwd: " if forward else "Re: ") + s


def compose(*, from_email: str, from_name: str, to: list[str], cc: list[str], bcc: list[str], subject: str, text: str,
			signature: str = "", in_reply_to: str = "", references: str = "", attachments: list[tuple[str, str, bytes]] | None = None,
			domain: str = "") -> EmailMessage:
	"""The message to send (text, and a simple HTML version). Replies carry In-Reply-To / References so they stay in the
	thread."""
	from html import escape

	m = EmailMessage()
	m["From"] = formataddr((from_name, from_email)) if from_name else from_email
	m["To"] = ", ".join(to)
	if cc:
		m["Cc"] = ", ".join(cc)
	if bcc:
		m["Bcc"] = ", ".join(bcc)
	m["Subject"] = subject
	m["Message-ID"] = make_msgid(domain=domain or (from_email.rsplit("@", 1)[-1] if "@" in from_email else None))
	m["Date"] = email.utils.formatdate(localtime=True)
	if in_reply_to:
		m["In-Reply-To"] = in_reply_to
		m["References"] = (references + " " + in_reply_to).strip()
	body = text + (("\n\n-- \n" + signature) if signature else "")
	m.set_content(body)
	m.add_alternative("<div style='font-family:Arial,sans-serif;font-size:14px;white-space:pre-wrap'>" + escape(body) + "</div>", subtype="html")
	for name, ctype, data in attachments or []:
		maintype, _s, subtype = (ctype or "application/octet-stream").partition("/")
		m.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=name)
	return m


def clean_list(value) -> list[str]:
	"""Addresses typed in To / Cc / Bcc (a list or text separated by commas / semicolons) → valid ones."""
	items = value if isinstance(value, list) else re.split(r"[,;\n]+", str(value or ""))
	out = []
	for v in items:
		for _n, a in getaddresses([str(v)]):
			if re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", a or ""):
				out.append(a.strip())
	return list(dict.fromkeys(out))


# ---- IMAP folder names (modified UTF-7, RFC 3501) ----------------------------------------------------------------------
def folder_name(raw: str) -> str:
	def dec(m):
		s = m.group(1)
		if not s:
			return "&"
		b = s.replace(",", "/")
		b += "=" * (-len(b) % 4)
		return base64.b64decode(b).decode("utf-16-be")

	return re.sub(r"&([^-]*)-", dec, str(raw))


def folder_encode(name: str) -> str:
	out, buf = [], ""

	def flush():
		nonlocal buf
		if buf:
			out.append("&" + base64.b64encode(buf.encode("utf-16-be")).decode().rstrip("=").replace("/", ",") + "-")
			buf = ""

	for ch in str(name):
		if 0x20 <= ord(ch) <= 0x7E:
			flush()
			out.append("&-" if ch == "&" else ch)
		else:
			buf += ch
	flush()
	return "".join(out)


SPECIAL = {"\\Sent": "sent", "\\Trash": "trash", "\\Drafts": "drafts", "\\Junk": "junk", "\\Archive": "archive", "\\All": "all", "\\Flagged": "flagged"}


def parse_list_line(line: str) -> dict | None:
	"""One IMAP LIST answer → {name, flags, role}."""
	m = re.match(r'\((?P<flags>[^)]*)\)\s+(?P<delim>"[^"]*"|NIL)\s+(?P<name>.+)$', str(line).strip())
	if not m:
		return None
	name = m.group("name").strip()
	if name.startswith('"') and name.endswith('"'):
		name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
	flags = m.group("flags").split()
	role = next((SPECIAL[f] for f in flags if f in SPECIAL), None)
	if not role:
		low = folder_name(name).lower().rsplit("/", 1)[-1].rsplit(".", 1)[-1]
		role = {"inbox": "inbox", "sent": "sent", "sent items": "sent", "sent mail": "sent", "trash": "trash", "deleted items": "trash",
				"bin": "trash", "drafts": "drafts", "spam": "junk", "junk": "junk", "junk e-mail": "junk", "archive": "archive"}.get(low)
	return {"raw": name, "name": folder_name(name), "flags": flags, "role": role, "selectable": "\\Noselect" not in flags}
