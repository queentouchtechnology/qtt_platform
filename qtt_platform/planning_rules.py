"""
Office Pulse planning (PROJ-0016 D) — the pure rules behind Boards, Notes, Whiteboards, Forms and My work. No Frappe
here, so tests run without a bench (tests/test_planning.py).

  boards      templates, lists and labels checked, card positions, who sees a board, checklist progress
  notes       checklists in the text ("- [ ]" / "- [x]"), action items, a meeting-notes template, search snippets
  whiteboard  merging drawings from several people (each element kept at its newest version)
  forms       questions checked, answers checked, a summary per question, CSV, the contact a response gives
  my work     when something is due (overdue / today / tomorrow / this week / later)
"""

import csv
import io
import re
import secrets
from datetime import date, datetime, timedelta

# ---- boards --------------------------------------------------------------------------------------------------------------
LABEL_COLORS = ("#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#2f7bff", "#0891b2", "#db2777", "#64748b")

# key: (title, lists, the list that means done, labels)
TEMPLATES = {
	"simple": ("To do", ["To do", "Doing", "Done"], "Done", ["Urgent", "Waiting"]),
	"project": ("Project", ["Backlog", "This week", "In progress", "Review", "Done"], "Done", ["Urgent", "Blocked", "Idea"]),
	"sales": ("Sales pipeline", ["New lead", "Contacted", "Quote sent", "Won", "Lost"], "Won", ["Hot", "Follow up", "Big order"]),
	"hiring": ("Hiring", ["Applied", "Phone call", "Interview", "Offer", "Joined"], "Joined", ["Fresher", "Experienced", "Referral"]),
	"content": ("Content calendar", ["Ideas", "Writing", "Design", "Ready", "Posted"], "Posted", ["Instagram", "Facebook", "Blog", "WhatsApp"]),
	"support": ("Customer issues", ["New", "In progress", "Waiting on customer", "Solved"], "Solved", ["Urgent", "Billing", "Delivery"]),
}
MAX_LISTS = 20
MAX_LABELS = 20
MAX_CHECKS = 100


def new_id() -> str:
	return secrets.token_hex(4)


def from_template(key: str) -> dict:
	"""Lists (with ids), the done list's id and labels for a template (simple when unknown)."""
	title, lists, done, labels = TEMPLATES.get(key) or TEMPLATES["simple"]
	ls = [{"id": new_id(), "title": t} for t in lists]
	return {"title": title, "lists": ls, "done_list": next(x["id"] for x in ls if x["title"] == done),
			"labels": [{"id": new_id(), "name": n, "color": LABEL_COLORS[i % len(LABEL_COLORS)]} for i, n in enumerate(labels)]}


def clean_lists(lists) -> list[dict]:
	"""[{id, title}] — titles needed, ids kept (new ones made), at most 20, no repeated ids."""
	out, seen = [], set()
	for x in lists or []:
		title = str((x or {}).get("title") or "").strip()[:60]
		if not title:
			raise ValueError("Every list needs a name.")
		i = str(x.get("id") or "").strip()[:16] or new_id()
		if i in seen:
			i = new_id()
		seen.add(i)
		out.append({"id": i, "title": title})
	if not out:
		raise ValueError("A board needs at least one list.")
	if len(out) > MAX_LISTS:
		raise ValueError(f"A board can have up to {MAX_LISTS} lists.")
	return out


def clean_labels(labels) -> list[dict]:
	out, seen = [], set()
	for x in labels or []:
		name = str((x or {}).get("name") or "").strip()[:30]
		if not name:
			continue
		i = str(x.get("id") or "").strip()[:16] or new_id()
		if i in seen:
			i = new_id()
		seen.add(i)
		color = str(x.get("color") or "")
		out.append({"id": i, "name": name, "color": color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else LABEL_COLORS[len(out) % len(LABEL_COLORS)]})
	return out[:MAX_LABELS]


def between(before: float | None, after: float | None) -> float:
	"""A position between two cards (None = the start or the end of the list)."""
	if before is None and after is None:
		return 1024.0
	if before is None:
		return after / 2
	if after is None:
		return before + 1024.0
	return (before + after) / 2


def needs_renumber(positions: list[float]) -> bool:
	"""True when two neighbours got too close to fit another card between them."""
	ps = sorted(positions)
	return any(b - a < 1e-6 for a, b in zip(ps, ps[1:]))


def renumber(n: int) -> list[float]:
	return [1024.0 * (i + 1) for i in range(n)]


def board_visible(board: dict, user: str, admin: bool, members: list[str]) -> bool:
	"""Team boards: everyone in the business. Members-only boards: who made it, its members, and owners / admins."""
	if board.get("visibility") == "team":
		return True
	return user == board.get("created_by_user") or user in members or admin


def board_may_manage(board: dict, user: str, admin: bool) -> bool:
	"""Rename, change lists, members, archive or delete: who made it, owners and admins."""
	return user == board.get("created_by_user") or admin


def clean_checklist(items) -> list[dict]:
	out = []
	for x in items or []:
		text = str((x or {}).get("text") or "").strip()[:200]
		if text:
			out.append({"text": text, "done": bool(x.get("done"))})
	return out[:MAX_CHECKS]


def progress(items) -> tuple[int, int]:
	items = items or []
	return sum(1 for x in items if x.get("done")), len(items)


# ---- notes ---------------------------------------------------------------------------------------------------------------
CHECK = re.compile(r"^(\s*[-*]\s+)\[( |x|X)\]\s?(.*)$")


def note_checks(body: str) -> tuple[int, int]:
	done = total = 0
	for line in (body or "").splitlines():
		m = CHECK.match(line)
		if m:
			total += 1
			done += m.group(2) in "xX"
	return done, total


def toggle_check(body: str, index: int) -> str:
	"""Tick or untick the index-th checkbox line (0-based); the text is unchanged otherwise."""
	lines, n = (body or "").split("\n"), -1
	for i, line in enumerate(lines):
		m = CHECK.match(line)
		if m:
			n += 1
			if n == index:
				lines[i] = f"{m.group(1)}[{' ' if m.group(2) in 'xX' else 'x'}] {m.group(3)}".rstrip()
				return "\n".join(lines)
	raise ValueError("That checkbox isn't in the note any more.")


def action_items(body: str) -> list[str]:
	"""The checkboxes not ticked yet — what's still to do (made into cards on a board)."""
	out = []
	for line in (body or "").splitlines():
		m = CHECK.match(line)
		if m and m.group(2) == " " and m.group(3).strip():
			out.append(m.group(3).strip()[:200])
	return out


def meeting_notes(title: str, when: str, where: str, people: list[str]) -> tuple[str, str]:
	"""A note for a meeting: who came, the agenda, notes, decisions and action items (as checkboxes)."""
	head = [f"**When:** {when}"] + ([f"**Where:** {where}"] if where else []) + ([f"**People:** {', '.join(people)}"] if people else [])
	body = "\n".join(head) + "\n\n## Agenda\n- \n\n## Notes\n\n\n## Decisions\n- \n\n## Action items\n- [ ] \n"
	return f"Meeting notes: {title}"[:140], body


def snippet(body: str, words: list[str], width: int = 140) -> str:
	"""A short piece of the text around the first word searched for (the start when none is found)."""
	text = re.sub(r"\s+", " ", re.sub(r"[#*`>\[\]]", "", body or "")).strip()
	low = text.lower()
	at = min([p for p in (low.find(w.lower()) for w in words if w) if p >= 0] or [0])
	start = max(0, at - width // 3)
	piece = text[start:start + width]
	return ("…" if start else "") + piece + ("…" if start + width < len(text) else "")


def clean_collection(name: str) -> str:
	return re.sub(r"\s+", " ", str(name or "")).strip()[:60]


# ---- whiteboard ----------------------------------------------------------------------------------------------------------
MAX_ELEMENTS = 20000


def merge_elements(saved: list[dict], incoming: list[dict]) -> list[dict]:
	"""Drawings from several people put together: each element (by id) at its newest version — ties broken by the
	versionNonce so everyone ends with the same one. Order: the saved order, new elements after."""
	by_id = {e.get("id"): e for e in saved or [] if e.get("id")}
	order = [e.get("id") for e in saved or [] if e.get("id")]
	for e in incoming or []:
		i = e.get("id")
		if not i:
			continue
		old = by_id.get(i)
		if old is None:
			order.append(i)
			by_id[i] = e
		elif (e.get("version", 0), e.get("versionNonce", 0)) > (old.get("version", 0), old.get("versionNonce", 0)):
			by_id[i] = e
	out = [by_id[i] for i in order]
	if len(out) > MAX_ELEMENTS:
		raise ValueError("This whiteboard is full — start another one.")
	return out


def changed_since(elements: list[dict], known: dict[str, int]) -> list[dict]:
	"""Elements someone hasn't seen at this version (known: {id: version})."""
	return [e for e in elements if known.get(e.get("id")) != e.get("version")]


# ---- forms ---------------------------------------------------------------------------------------------------------------
QTYPES = {"short": "Short answer", "long": "Paragraph", "choice": "One choice", "checkboxes": "Several choices", "dropdown": "Dropdown",
		  "number": "Number", "date": "Date", "rating": "Rating (1–5)", "yesno": "Yes / No", "email": "Email", "phone": "Phone"}
WITH_OPTIONS = {"choice", "checkboxes", "dropdown"}
MAX_QUESTIONS = 60
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_questions(questions) -> list[dict]:
	"""[{id, type, label, help, required, options}] checked: a label each, known types, options for choice questions."""
	out, seen = [], set()
	for q in questions or []:
		q = q or {}
		kind = str(q.get("type") or "short")
		if kind not in QTYPES:
			raise ValueError(f"Unknown kind of question: {kind}")
		label = str(q.get("label") or "").strip()[:300]
		if not label:
			raise ValueError("Every question needs its text.")
		opts = []
		if kind in WITH_OPTIONS:
			opts = list(dict.fromkeys(str(o).strip()[:120] for o in q.get("options") or [] if str(o).strip()))[:50]
			if len(opts) < 2:
				raise ValueError(f"Give at least two choices for “{label}”.")
		i = re.sub(r"[^a-z0-9]", "", str(q.get("id") or "").lower())[:12] or new_id()
		if i in seen:
			i = new_id()
		seen.add(i)
		out.append({"id": i, "type": kind, "label": label, "help": str(q.get("help") or "").strip()[:300],
					"required": bool(q.get("required")), "options": opts})
	if not out:
		raise ValueError("Add at least one question.")
	if len(out) > MAX_QUESTIONS:
		raise ValueError(f"A form can have up to {MAX_QUESTIONS} questions.")
	return out


def _empty(v) -> bool:
	return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)


def check_answers(questions: list[dict], answers: dict) -> tuple[dict, dict]:
	"""(clean answers, {question id: what's wrong}). Unknown questions are dropped."""
	clean, errors = {}, {}
	answers = answers or {}
	for q in questions:
		v, kind = answers.get(q["id"]), q["type"]
		if _empty(v):
			if q.get("required"):
				errors[q["id"]] = "Please answer this."
			continue
		try:
			if kind in ("short", "long"):
				clean[q["id"]] = str(v).strip()[:300 if kind == "short" else 5000]
			elif kind in ("choice", "dropdown"):
				if str(v) not in q["options"]:
					raise ValueError("Choose one of the choices.")
				clean[q["id"]] = str(v)
			elif kind == "checkboxes":
				vs = [str(x) for x in (v if isinstance(v, list) else [v])]
				if any(x not in q["options"] for x in vs):
					raise ValueError("Choose from the choices.")
				clean[q["id"]] = [o for o in q["options"] if o in vs]
			elif kind == "number":
				n = float(str(v).replace(",", ""))
				clean[q["id"]] = int(n) if n.is_integer() else n
			elif kind == "date":
				clean[q["id"]] = date.fromisoformat(str(v)[:10]).isoformat()
			elif kind == "rating":
				n = int(v)
				if not 1 <= n <= 5:
					raise ValueError("Choose 1 to 5.")
				clean[q["id"]] = n
			elif kind == "yesno":
				if str(v).lower() not in ("yes", "no"):
					raise ValueError("Choose yes or no.")
				clean[q["id"]] = str(v).lower()
			elif kind == "email":
				if not EMAIL.match(str(v).strip()):
					raise ValueError("That doesn't look like an email address.")
				clean[q["id"]] = str(v).strip().lower()[:200]
			elif kind == "phone":
				digits = re.sub(r"[^\d+]", "", str(v))
				if len(re.sub(r"\D", "", digits)) < 7:
					raise ValueError("That doesn't look like a phone number.")
				clean[q["id"]] = digits[:20]
		except ValueError as e:
			msg = str(e)
			errors[q["id"]] = msg if msg and not msg.startswith(("could not", "invalid", "Invalid")) else "That answer doesn't fit this question."
	return clean, errors


def summary(questions: list[dict], responses: list[dict]) -> list[dict]:
	"""Per question: how many answered, and counts (choices, yes / no, ratings with the average), number range and
	average, or the latest few written answers."""
	out = []
	for q in questions:
		vals = [r[q["id"]] for r in responses if not _empty(r.get(q["id"]))]
		s = {"id": q["id"], "label": q["label"], "type": q["type"], "answered": len(vals)}
		if q["type"] in WITH_OPTIONS:
			counts = {o: 0 for o in q["options"]}
			for v in vals:
				for x in v if isinstance(v, list) else [v]:
					if x in counts:
						counts[x] += 1
			s["counts"] = [{"option": o, "count": c} for o, c in counts.items()]
		elif q["type"] == "yesno":
			s["counts"] = [{"option": o, "count": sum(1 for v in vals if v == o.lower())} for o in ("Yes", "No")]
		elif q["type"] == "rating":
			s["counts"] = [{"option": str(n), "count": sum(1 for v in vals if v == n)} for n in range(1, 6)]
			s["average"] = round(sum(vals) / len(vals), 2) if vals else None
		elif q["type"] == "number":
			s.update({"min": min(vals) if vals else None, "max": max(vals) if vals else None,
					  "average": round(sum(vals) / len(vals), 2) if vals else None})
		else:
			s["latest"] = [str(v) for v in vals[-5:]][::-1]
		out.append(s)
	return out


def to_csv(questions: list[dict], responses: list[dict]) -> str:
	"""Responses as a spreadsheet: when, who (when known), then one column per question."""
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(["Submitted", "Name", "Email"] + [q["label"] for q in questions])
	for r in responses:
		row = [r.get("_at", ""), r.get("_name", ""), r.get("_email", "")]
		for q in questions:
			v = r.get(q["id"])
			row.append("; ".join(v) if isinstance(v, list) else "" if v is None else v)
		w.writerow([_safe_cell(x) for x in row])
	return buf.getvalue()


def _safe_cell(v):
	"""Stops a spreadsheet treating an answer as a formula (=, +, -, @ at the start)."""
	s = str(v)
	return "'" + s if s[:1] in ("=", "+", "-", "@") and not re.fullmatch(r"[+-]?\d[\d.]*", s) else s


def contact_from(questions: list[dict], answers: dict) -> dict | None:
	"""Name / email / phone a response gives (a question about the name, the first email and phone answers); None
	when it gives no way to reach them."""
	name = email = phone = ""
	for q in questions:
		v = answers.get(q["id"])
		if _empty(v):
			continue
		if q["type"] == "email" and not email:
			email = str(v)
		elif q["type"] == "phone" and not phone:
			phone = str(v)
		elif q["type"] == "short" and not name and re.search(r"\bname\b", q["label"], re.I):
			name = str(v)[:140]
	if not (email or phone):
		return None
	return {"name": name or email or phone, "email": email, "phone": phone}


def form_open(form: dict, count: int, now: datetime) -> str | None:
	"""Why it doesn't take answers now (None = it does)."""
	if not form.get("accepting"):
		return "closed"
	if form.get("closes_at") and now >= form["closes_at"]:
		return "ended"
	if form.get("max_responses") and count >= int(form["max_responses"]):
		return "full"
	return None


# ---- my work -------------------------------------------------------------------------------------------------------------
BUCKETS = ("overdue", "today", "tomorrow", "week", "later", "someday")


def bucket(due: date | None, today: date) -> str:
	if due is None:
		return "someday"
	if due < today:
		return "overdue"
	if due == today:
		return "today"
	if due == today + timedelta(days=1):
		return "tomorrow"
	if due <= today + timedelta(days=6 - today.weekday()):  # to Sunday
		return "week"
	return "later"
