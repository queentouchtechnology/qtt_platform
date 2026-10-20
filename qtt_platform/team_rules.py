"""
Team (free core of QTT OS, PROJ-0013 / PROJ-0014) — the rules, pure (no Frappe; tests/test_team.py).

Team chat runs on Raven (installed on the site): each business has its own private Raven workspace named
"qtt-<tenant>", a #general channel everyone in the business is in, more channels its members make, and direct messages
between members. The app talks only to qtt_platform.api.team / team_extras, which check the business and its
membership; customers never get Raven's role (it would give them Desk).

What people type is plain text with WhatsApp-style marks (*bold* _italic_ ~strike~ `code`), links and @mentions;
Raven keeps HTML (what its own screens show), and the app gets the plain text back.
"""

import html
import json
import re
from datetime import datetime, timedelta

PREFIX = "qtt-"
GENERAL = "general"
MAX_TEXT = 4000
MAX_FILE = 25 * 1024 * 1024
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
AUDIO_TYPES = (".wav", ".m4a", ".aac", ".mp3", ".ogg", ".opus", ".webm")
EVERYONE = "everyone"

# The reactions offered first (any emoji works).
QUICK_REACTIONS = ["👍", "❤️", "😂", "🎉", "🙏", "👀", "✅", "🔥"]

# AI extras (PROJ-0014 F) — paid with the business's AI credits; Team itself is free.
CREDITS = {"catch_up": 1, "task": 1}
CATCH_UP_MAX = 150  # messages read for one summary

ONLINE_SECONDS = 120  # seen this recently → online
AWAY_SECONDS = 15 * 60  # → away; older → offline ("Active 2 h ago")


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


# ---- text ------------------------------------------------------------------------------------------------------------
_LINK = re.compile(r"https?://[^\s<]+")
# WhatsApp-style marks: the mark hugs the words (no space inside), and isn't part of a word (snake_case, 2*3*4 stay)
_MARKS = [("*", "strong"), ("_", "em"), ("~", "s")]


def _mark(text: str, mark: str, tag: str) -> str:
	m = re.escape(mark)
	return re.sub(rf"(?<![\w{m}]){m}(?=\S)([^{m}\n]*?\S){m}(?![\w{m}])", rf"<{tag}>\1</{tag}>", text)


def mention_pattern(name: str) -> re.Pattern:
	return re.compile(r"(?<![\w@])@" + re.escape(html.escape(name)) + r"(?![\w])")


def text_to_html(text: str, mentions: dict[str, str] | None = None) -> str:
	"""What the app's composer sends (plain text) → the HTML Raven keeps: escaped, paragraphs, line breaks, links,
	*bold* _italic_ ~strike~ `code`, and @Name for the people in `mentions` ({user: name}) as Raven's mention spans."""
	text = str(text or "").strip()[:MAX_TEXT]
	paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
	out = []
	for p in paras:
		esc = html.escape(p.strip())
		keep: list[str] = []

		def hold(s: str) -> str:
			keep.append(s)
			return f"\x00{len(keep) - 1}\x00"

		esc = re.sub(r"`([^`\n]+)`", lambda m: hold(f"<code>{m.group(1)}</code>"), esc)
		esc = _LINK.sub(lambda m: hold(f'<a href="{m.group(0)}" target="_blank" rel="noopener">{m.group(0)}</a>'), esc)
		for user, name in sorted((mentions or {}).items(), key=lambda x: -len(x[1] or "")):
			if not name:
				continue
			span = (f'<span class="mention" data-type="userMention" data-id="{html.escape(user, quote=True)}" '
					f'data-label="{html.escape(name, quote=True)}">@{html.escape(name)}</span>')
			esc = mention_pattern(name).sub(lambda _m, s=span: hold(s), esc)
		for mark, tag in _MARKS:
			esc = _mark(esc, mark, tag)
		esc = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], esc)
		out.append("<p>" + esc.replace("\n", "<br>") + "</p>")
	return "".join(out)


def html_to_text(value: str) -> str:
	"""Raven's HTML (also messages written in Raven itself) → plain text with the same marks, for the app."""
	s = str(value or "")
	s = re.sub(r"(?i)<br\s*/?>", "\n", s)
	s = re.sub(r"(?i)</p>\s*<p[^>]*>", "\n\n", s)
	s = re.sub(r"(?i)<li[^>]*>", "• ", s)
	s = re.sub(r"(?i)</(li|div|h\d)>", "\n", s)
	s = re.sub(r"(?is)<(strong|b)>(.*?)</\1>", r"*\2*", s)
	s = re.sub(r"(?is)<(em|i)>(.*?)</\1>", r"_\2_", s)
	s = re.sub(r"(?is)<(s|del|strike)>(.*?)</\1>", r"~\2~", s)
	s = re.sub(r"(?is)<code>(.*?)</code>", r"`\1`", s)
	s = re.sub(r"<[^>]+>", "", s)
	s = html.unescape(s)
	return re.sub(r"\n{3,}", "\n\n", s).strip()


def plain(text: str) -> str:
	"""Without the marks — for previews, notifications and search."""
	s = re.sub(r"(?<![\w*])\*(\S[^*\n]*?)\*(?![\w*])", r"\1", str(text or ""))
	s = re.sub(r"(?<![\w_])_(\S[^_\n]*?)_(?![\w_])", r"\1", s)
	s = re.sub(r"(?<![\w~])~(\S[^~\n]*?)~(?![\w~])", r"\1", s)
	return s.replace("`", "")


def mentions_in(text: str, people: dict[str, str]) -> dict[str, str]:
	"""Which of the people ({user: name}) are @mentioned in the text — longest names first, so "@Ravi Kumar" isn't
	also "@Ravi"."""
	found: dict[str, str] = {}
	rest = html.escape(str(text or ""))
	for user, name in sorted(people.items(), key=lambda x: -len(x[1] or "")):
		if name and mention_pattern(name).search(rest):
			found[user] = name
			rest = mention_pattern(name).sub(" ", rest)
	return found


def mentions_everyone(text: str) -> bool:
	return bool(re.search(r"(?<![\w@])@" + EVERYONE + r"\b", str(text or ""), re.I))


def voice(file_name: str | None) -> int | None:
	"""A voice note's length in seconds (the app names them voice-<seconds>s-….wav); None for other files."""
	m = re.match(r"voice-(\d{1,4})s", str(file_name or "").rsplit("/", 1)[-1])
	return int(m.group(1)) if m and str(file_name).lower().endswith(AUDIO_TYPES) else None


def preview(message_type: str | None, content: str | None, file: str | None = None) -> str:
	"""One line for a list or a notification."""
	if message_type == "Image":
		return "📷 Photo"
	if message_type == "File":
		if voice(file) is not None:
			return "🎤 Voice note"
		return "📎 " + (str(file or "").rsplit("/", 1)[-1] or "File")
	if message_type == "Poll":
		return "📊 Poll"
	t = re.sub(r"\s+", " ", plain(html_to_text(content or ""))).strip()
	return t[:140] + ("…" if len(t) > 140 else "")


def kind_of(file_name: str) -> str:
	return "Image" if str(file_name or "").lower().endswith(IMAGE_TYPES) else "File"


def can_see(channel: dict, me_member: bool) -> bool:
	"""A business channel shows to a member when they're in it, or it's open to the whole business."""
	if channel.get("is_archived") or channel.get("is_thread"):
		return False
	return bool(me_member) or channel.get("type") in ("Public", "Open")


# ---- reactions -------------------------------------------------------------------------------------------------------
def reactions(raw, me: str, names: dict[str, str]) -> list[dict]:
	"""Raven's message_reactions JSON → [{emoji, count, mine, people}] in the order they were first used."""
	try:
		data = json.loads(raw) if isinstance(raw, str) else (raw or {})
	except ValueError:
		return []
	out = []
	for key, r in (data or {}).items():
		if not isinstance(r, dict) or r.get("is_custom"):
			continue
		users = list(r.get("users") or [])
		if not users:
			continue
		out.append({"emoji": r.get("reaction") or key, "count": len(users), "mine": me in users,
					"people": [names.get(u, u) for u in users][:12]})
	return out


def escaped(emoji: str) -> str:
	"""How Raven keys a reaction (its unique check per person)."""
	return str(emoji).encode("unicode-escape").decode("utf-8").replace("\\u", "")


# ---- presence --------------------------------------------------------------------------------------------------------
def presence(last_seen: float | None, now: float) -> str:
	if not last_seen:
		return "offline"
	gap = now - last_seen
	return "online" if gap <= ONLINE_SECONDS else ("away" if gap <= AWAY_SECONDS else "offline")


def status_live(until, now: datetime) -> bool:
	"""A status / Do not disturb with no end, or one that hasn't ended."""
	return until is None or until > now


def until_from(choice: str | None, now: datetime) -> datetime | None:
	"""Status / Do not disturb "for": 30m, 1h, 2h, today (end of the day), week (7 days), or none (until changed)."""
	match choice:
		case "30m":
			return now + timedelta(minutes=30)
		case "1h":
			return now + timedelta(hours=1)
		case "2h":
			return now + timedelta(hours=2)
		case "4h":
			return now + timedelta(hours=4)
		case "today":
			return now.replace(hour=23, minute=59, second=0, microsecond=0)
		case "tomorrow":
			return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
		case "week":
			return now + timedelta(days=7)
	return None


def remind_at(choice: str, now: datetime) -> datetime | None:
	"""Remind me: 20m, 1h, 3h, tonight (19:00, or in an hour when that's past), tomorrow (9:00), next week (Monday 9:00)."""
	match choice:
		case "20m":
			return now + timedelta(minutes=20)
		case "1h":
			return now + timedelta(hours=1)
		case "3h":
			return now + timedelta(hours=3)
		case "tonight":
			t = now.replace(hour=19, minute=0, second=0, microsecond=0)
			return t if t > now + timedelta(minutes=10) else now + timedelta(hours=1)
		case "tomorrow":
			return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
		case "next_week":
			days = 7 - now.weekday() or 7
			return (now + timedelta(days=days)).replace(hour=9, minute=0, second=0, microsecond=0)
	return None


# ---- search ----------------------------------------------------------------------------------------------------------
def search_words(q: str) -> list[str]:
	"""The words to find (every one must be in the message), at most 6, 2+ letters, without LIKE wildcards."""
	words = [re.sub(r"[%_\\]", "", w) for w in re.split(r"\s+", str(q or "").strip())]
	return [w for w in words if len(w) >= 2][:6]


def snippet(text: str, words: list[str], width: int = 160) -> str:
	"""The part of a message around the first word found."""
	t = re.sub(r"\s+", " ", plain(text)).strip()
	low = t.lower()
	at = min([i for i in (low.find(w.lower()) for w in words) if i >= 0] or [0])
	start = max(0, at - width // 3)
	cut = t[start:start + width]
	return ("…" if start else "") + cut + ("…" if start + width < len(t) else "")


# ---- AI extras -------------------------------------------------------------------------------------------------------
def catch_up_prompt(chat: str, lines: list[str], language: str = "en") -> list[dict]:
	lang = {"ta": "Tamil", "hi": "Hindi", "ar": "Arabic"}.get(language, "English")
	return [
		{"role": "system", "content": (
			"You summarise a business's team chat for someone catching up. Use only what the messages say — never add facts, "
			"numbers, names or dates that aren't in them. Short, plain sentences. Answer in " + lang + ". Reply with JSON only: "
			'{"summary": ["…" up to 5 key points], "decisions": ["…"], "asks": ["questions or requests for the reader, with who asked"], '
			'"todos": ["things someone said they or others will do, with who"]}. Empty lists when there is nothing.')},
		{"role": "user", "content": f"Chat: {chat}\nMessages (oldest first, 'name: text'):\n" + "\n".join(lines)},
	]


def parse_catch_up(text: str) -> dict | None:
	data = _json(text)
	if not isinstance(data, dict):
		return None
	out = {k: [str(x).strip() for x in (data.get(k) or []) if str(x).strip()][:6] for k in ("summary", "decisions", "asks", "todos")}
	return out if any(out.values()) else None


def task_prompt(message: str, author: str, people: list[str], today: str) -> list[dict]:
	return [
		{"role": "system", "content": (
			"Turn a team chat message into one task. Use only what the message says. Reply with JSON only: "
			'{"title": "short task, starts with a verb, max 80 characters", "assignee": "one name from the list or empty", '
			'"due": "YYYY-MM-DD or empty"}. Today is ' + today + ". Work out dates like 'tomorrow' or 'Friday' from today; "
			"leave due empty when no date is said. Only pick an assignee when the message clearly names them.")},
		{"role": "user", "content": f"People: {', '.join(people)}\nMessage from {author}:\n{message}"},
	]


def parse_task(text: str, people: dict[str, str]) -> dict | None:
	"""The AI's task → {title, assign_to (a user of the business or None), due (YYYY-MM-DD or None)}."""
	data = _json(text)
	if not isinstance(data, dict) or not str(data.get("title") or "").strip():
		return None
	name = str(data.get("assignee") or "").strip().lower()
	user = next((u for u, n in people.items() if n and n.lower() == name), None) if name else None
	due = str(data.get("due") or "").strip()
	return {"title": str(data["title"]).strip()[:140], "assign_to": user, "due": due if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due) else None}


def _json(text: str):
	t = str(text or "").strip()
	t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
	try:
		return json.loads(t)
	except ValueError:
		m = re.search(r"\{.*\}", t, re.S)
		if m:
			try:
				return json.loads(m.group(0))
			except ValueError:
				return None
	return None
