"""
Team (free core of QTT OS, PROJ-0013) — the rules, pure (no Frappe; tests/test_team.py).

Team chat runs on Raven (installed on the site): each business has its own private Raven workspace named
"qtt-<tenant>", a #general channel everyone in the business is in, more channels its members make, and direct messages
between members. The app talks only to qtt_platform.api.team, which checks the business and its membership; customers
never get Raven's role (it would give them Desk).
"""

import html
import re

PREFIX = "qtt-"
GENERAL = "general"
MAX_TEXT = 4000
MAX_FILE = 25 * 1024 * 1024
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def workspace_name(tenant: str) -> str:
	return f"{PREFIX}{tenant}"


def is_business_workspace(name: str | None) -> bool:
	return bool(name) and str(name).startswith(PREFIX)


def channel_id(workspace: str, name: str) -> str:
	"""Raven names a channel <workspace>-<name>, the name lowercased with spaces as hyphens."""
	return f"{workspace}-{clean_channel_name(name)}"


def clean_channel_name(name: str) -> str:
	"""A channel name as Raven keeps it: lowercase, spaces → hyphens, letters / digits / - and _ only, up to 50."""
	n = re.sub(r"\s+", "-", str(name or "").strip().lower())
	n = re.sub(r"[^a-z0-9_\-஀-௿ऀ-ॿ؀-ۿ]", "", n)
	return re.sub(r"-{2,}", "-", n).strip("-")[:50]


def dm_name(a: str, b: str) -> str:
	return f"{a} _ {b}"


def dm_peer(channel_name: str, me: str) -> str | None:
	"""The other person in a direct-message channel ("a _ b"); None for a note-to-self or a malformed name."""
	parts = [p.strip() for p in str(channel_name or "").split(" _ ")]
	if len(parts) != 2:
		return None
	others = [p for p in parts if p != me]
	return others[0] if len(others) == 1 else None


def text_to_html(text: str) -> str:
	"""What the app's composer sends (plain text) → the HTML Raven keeps: escaped, paragraphs, line breaks, links."""
	text = str(text or "").strip()[:MAX_TEXT]
	paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]

	def link(m):
		u = m.group(0)
		return f'<a href="{u}" target="_blank" rel="noopener">{u}</a>'

	out = []
	for p in paras:
		esc = html.escape(p.strip())
		esc = re.sub(r"https?://[^\s<]+", link, esc)
		out.append("<p>" + esc.replace("\n", "<br>") + "</p>")
	return "".join(out)


def html_to_text(value: str) -> str:
	"""Raven's HTML (also messages written in Raven itself) → plain text for the app."""
	s = str(value or "")
	s = re.sub(r"(?i)<br\s*/?>", "\n", s)
	s = re.sub(r"(?i)</p>\s*<p[^>]*>", "\n\n", s)
	s = re.sub(r"(?i)<li[^>]*>", "• ", s)
	s = re.sub(r"(?i)</(li|div|h\d)>", "\n", s)
	s = re.sub(r"<[^>]+>", "", s)
	s = html.unescape(s)
	return re.sub(r"\n{3,}", "\n\n", s).strip()


def preview(message_type: str | None, content: str | None, file: str | None = None) -> str:
	"""One line for a list or a notification."""
	if message_type == "Image":
		return "📷 Photo"
	if message_type == "File":
		return "📎 " + (str(file or "").rsplit("/", 1)[-1] or "File")
	if message_type == "Poll":
		return "📊 Poll"
	t = re.sub(r"\s+", " ", html_to_text(content or "")).strip()
	return t[:140] + ("…" if len(t) > 140 else "")


def kind_of(file_name: str) -> str:
	return "Image" if str(file_name or "").lower().endswith(IMAGE_TYPES) else "File"


def can_see(channel: dict, me_member: bool) -> bool:
	"""A business channel shows to a member when they're in it, or it's open to the whole business."""
	if channel.get("is_archived") or channel.get("is_thread"):
		return False
	return bool(me_member) or channel.get("type") in ("Public", "Open")
