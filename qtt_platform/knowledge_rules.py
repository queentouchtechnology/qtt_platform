"""
A business's own knowledge (PROJ-0011 A1) — pure rules, no Frappe; tests/test_knowledge_rules.py.

One Business Knowledge per business. What it tells:
  customer_text   the receptionist (and anything customers see): facts, offerings, FAQs for customers or everyone
  team_text       the team's Know your business bot: the customer facts + FAQs for the team + team notes for the
                  person's roles. Never salaries, pay, bank or anyone's private details — those aren't in it, and the
                  bot is told to refuse them.
  marketing_brief the Marketing assistant: who the business is, how it talks, what it sells, what makes it different
  brand           the locked palette and fonts (posts never change them)
  health          how complete it is, and what to add next
  team_prompt     the Know your business bot (in the app, or a team member writing to QTT's WhatsApp)
"""

import json
import re

TEXT = {  # field: max characters
	"about": 1000, "hours": 400, "holidays": 400, "map_link": 300, "delivery": 600, "payments": 300, "bookings": 600,
	"policies": 1500, "notes": 4000, "audience": 400, "different": 400, "language": 40, "font_heading": 60, "font_body": 60,
}
TONES = ("Friendly", "Formal", "Fun", "Premium")
AUDIENCES = ("Customers", "Team", "Everyone")
COLORS = ("color_primary", "color_secondary", "color_accent", "color_dark", "color_light")
SOURCES = ("use_website", "use_store", "use_items")
SWITCHES = (*SOURCES, "team_whatsapp")  # team_whatsapp: the team may also ask on QTT's WhatsApp number
ALL_NOTES = "*"  # the owner and admins: every team note
ALL_NOTES = "*"  # the owner and admins: every team note
MAX_ROWS = {"offerings": 300, "faqs": 300, "team_notes": 200}
MAX_TEXT = 24000
EVERYONE = "everyone"

_LABELS = (("about", "What the business does"), ("hours", "Opening hours"), ("holidays", "Holidays and special hours"),
		   ("address", "Address"), ("map_link", "Map"), ("phone", "Phone"), ("whatsapp", "WhatsApp"), ("email", "Email"),
		   ("website", "Website"), ("delivery", "Delivery"), ("payments", "Payment methods"), ("bookings", "Bookings and orders"),
		   ("policies", "Policies"), ("notes", "More details"))


def _s(v, n: int) -> str:
	return re.sub(r"[ \t]+", " ", str(v or "")).strip()[:n]


def _on(v) -> int:
	return 0 if v in (False, 0, "0", "false", "False", None) else 1


def hex_color(v) -> str:
	"""'#1d4ed8' / '1D4ED8' → '#1d4ed8'; anything else → ''."""
	m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(v or "").strip())
	return f"#{m.group(1).lower()}" if m else ""


def role_keys(value) -> list[str]:
	"""'everyone' / 'cashier, hr_admin' / one per line → ['cashier', 'hr_admin'] or ['everyone']."""
	keys = []
	for k in re.split(r"[\s,;]+", str(value or "").lower()):
		k = re.sub(r"[^a-z0-9_]", "", k)
		if k and k not in keys:
			keys.append(k)
	return [EVERYONE] if not keys or EVERYONE in keys else keys


def role_key(name) -> str:
	"""A role as team notes keep it: 'HR Admin' → 'hr_admin' (the app writes the same)."""
	return re.sub(r"[^a-z0-9_]", "", re.sub(r"\s+", "_", str(name or "").strip().lower()))


def clean(data: dict | None) -> dict:
	"""The app's edit → only known fields and rows, trimmed; colours as hex; tone from its list."""
	d = data or {}
	out = {k: _s(d.get(k), n) for k, n in TEXT.items() if k in d}
	if "tone" in d:
		out["tone"] = d["tone"] if d["tone"] in TONES else "Friendly"
	for k in COLORS:
		if k in d:
			out[k] = hex_color(d[k])
	for k in SWITCHES:
		if k in d:
			out[k] = _on(d[k])
	if "offerings" in d:
		rows = []
		for r in d.get("offerings") or []:
			if isinstance(r, dict) and _s(r.get("item"), 140):
				rows.append({"item": _s(r.get("item"), 140), "kind": "Service" if r.get("kind") == "Service" else "Product",
							 "price": _s(r.get("price"), 60), "details": _s(r.get("details"), 300), "active": _on(r.get("active", 1))})
		out["offerings"] = rows[: MAX_ROWS["offerings"]]
	if "faqs" in d:
		rows, seen = [], {}
		for r in d.get("faqs") or []:
			if not isinstance(r, dict):
				continue
			q, a = _s(r.get("question"), 300), _s(r.get("answer"), 1500)
			if not q or not a:
				continue
			row = {"question": q, "answer": a, "audience": r.get("audience") if r.get("audience") in AUDIENCES else "Everyone",
				   "active": _on(r.get("active", 1))}
			key = q.lower().rstrip("?").strip()
			if key in seen:  # the same question once — the last answer wins
				rows[seen[key]] = row
			else:
				seen[key] = len(rows)
				rows.append(row)
		out["faqs"] = rows[: MAX_ROWS["faqs"]]
	if "team_notes" in d:
		rows = []
		for r in d.get("team_notes") or []:
			if isinstance(r, dict) and _s(r.get("title"), 140) and _s(r.get("body"), 3000):
				rows.append({"title": _s(r.get("title"), 140), "body": _s(r.get("body"), 3000),
							 "roles": "\n".join(role_keys(r.get("roles"))), "active": _on(r.get("active", 1))})
		out["team_notes"] = rows[: MAX_ROWS["team_notes"]]
	return out


def _facts(k: dict, contacts: dict | None = None) -> list[str]:
	src = {**(contacts or {}), **{x: v for x, v in k.items() if isinstance(v, str)}}
	return [f"{label}: {str(src[key]).strip()}" for key, label in _LABELS if str(src.get(key) or "").strip()]


def _offerings(k: dict) -> str:
	rows = [o for o in k.get("offerings") or [] if o.get("active", 1)]
	lines = [f"- {o['item']}" + (f" — {o['price']}" if o.get("price") else "") + (f": {o['details']}" if o.get("details") else "") for o in rows]
	return ("Products and services:\n" + "\n".join(lines)) if lines else ""


def _faqs(k: dict, audiences: tuple[str, ...]) -> str:
	qa = [f"Q: {f['question']}\nA: {f['answer']}" for f in k.get("faqs") or [] if f.get("active", 1) and f.get("audience", "Everyone") in audiences]
	return ("Questions and answers:\n" + "\n\n".join(qa)) if qa else ""


def customer_text(k: dict, contacts: dict | None = None, extra: str = "") -> str:
	"""What customers may be told: facts, offerings, FAQs for customers or everyone (never team-only ones)."""
	parts = _facts(k, contacts) + [x for x in (_offerings(k), _faqs(k, ("Customers", "Everyone")), extra) if x]
	return "\n\n".join(parts)[:MAX_TEXT] or "The owner hasn't added any details yet."


def team_text(k: dict, roles: list[str] | set[str], contacts: dict | None = None) -> str:
	"""What a team member may be told: the customer facts, FAQs for the team or everyone, and the team notes for their roles."""
	mine = {role_key(r) if r != ALL_NOTES else r for r in roles or []}
	notes = [f"{n['title']}:\n{n['body']}" for n in k.get("team_notes") or []
			 if n.get("active", 1) and (ALL_NOTES in mine or EVERYONE in role_keys(n.get("roles")) or mine & set(role_keys(n.get("roles"))))]
	parts = _facts(k, contacts) + [x for x in (_offerings(k), _faqs(k, ("Team", "Everyone")),
											   ("For the team:\n" + "\n\n".join(notes)) if notes else "") if x]
	return "\n\n".join(parts)[:MAX_TEXT] or "The owner hasn't added any details yet."


def marketing_brief(k: dict, business: str) -> str:
	"""Who the business is and how it talks — for post ideas, captions, articles and newsletters (customer-safe only)."""
	lines = [f"Business: {business}", f"Tone: {k.get('tone') or 'Friendly'}", f"Language: {k.get('language') or 'English'}"]
	for key, label in (("about", "What it does"), ("audience", "Customers"), ("different", "What makes it different"),
					   ("delivery", "Delivery"), ("payments", "Payments"), ("hours", "Hours")):
		if str(k.get(key) or "").strip():
			lines.append(f"{label}: {k[key].strip()}")
	off = _offerings(k)
	return "\n".join(lines + ([off] if off else []))[:8000]


def brand(k: dict, fallback: str = "") -> dict:
	"""The locked palette: the owner's colours, the main one falling back to the business profile's brand colour."""
	colors = {c.removeprefix("color_"): hex_color(k.get(c)) for c in COLORS}
	if not colors["primary"]:
		colors["primary"] = hex_color(fallback)
	return {"colors": {n: v for n, v in colors.items() if v}, "font_heading": k.get("font_heading") or "",
			"font_body": k.get("font_body") or ""}


HEALTH = (  # (what, weight, how to tell it's there)
	("about", 3, lambda k: len(str(k.get("about") or "")) >= 40),
	("offerings", 3, lambda k: len([o for o in k.get("offerings") or [] if o.get("active", 1)]) >= 3),
	("hours", 2, lambda k: bool(str(k.get("hours") or "").strip())),
	("faqs", 2, lambda k: len([f for f in k.get("faqs") or [] if f.get("active", 1)]) >= 5),
	("delivery_or_bookings", 1, lambda k: bool(str(k.get("delivery") or "").strip() or str(k.get("bookings") or "").strip())),
	("payments", 1, lambda k: bool(str(k.get("payments") or "").strip())),
	("audience", 1, lambda k: bool(str(k.get("audience") or "").strip())),
	("different", 1, lambda k: bool(str(k.get("different") or "").strip())),
	("brand", 1, lambda k: bool(hex_color(k.get("color_primary")))),
	("team_notes", 1, lambda k: bool([n for n in k.get("team_notes") or [] if n.get("active", 1)])),
)


def health(k: dict) -> dict:
	"""{score 0–100, missing: [what to add next, most useful first]}."""
	total = sum(w for _, w, _ in HEALTH)
	got = sum(w for _, w, ok in HEALTH if ok(k))
	missing = [name for name, _, ok in sorted(HEALTH, key=lambda x: -x[1]) if not ok(k)]
	return {"score": round(got * 100 / total), "missing": missing}


def from_receptionist(profile: dict, faqs: list[dict]) -> dict:
	"""A receptionist's own profile and Q&A (PROJ-0006) → the business knowledge it moves into (nothing lost)."""
	k = {x: profile.get(x) for x in ("about", "hours", "holidays", "map_link", "delivery", "payments", "bookings", "notes") if profile.get(x)}
	if profile.get("tone") in TONES:
		k["tone"] = profile["tone"]
	k["faqs"] = [{"question": f.get("question"), "answer": f.get("answer"), "audience": "Customers", "active": f.get("active", 1)}
				 for f in faqs or []]
	return clean(k)


# ---- Know your business (the team's bot, PROJ-0011 A3) ---------------------------------------------------------------
NOT_KNOWN = "I don't have that in the business's details yet — please ask your manager. The owner can see the question and add it."
PRIVATE_ANSWER = "That's private — please ask HR or the owner directly."
PRIVATE = re.compile(r"\b(salar(y|ies)|payslips?|pay ?slips?|ctc|bank account|account number|ifsc|aadhaa?r|pan (card|number)|"
					 r"home address|personal (number|phone|address)|passwords?|otp)\b", re.I)


def team_prompt(*, business: str, facts: str, question: str, name: str = "", roles: list[str] | None = None,
				history: list[dict] | None = None) -> list[dict]:
	"""A team member's question, answered from the business's details for their roles ONLY. JSON {answer, known}."""
	named = [r for r in roles or [] if r != ALL_NOTES]
	who = (name or "a team member") + (f" ({', '.join(named)})" if named else "")
	msgs = [{"role": "system", "content": (
		f"You are Know your business, the helper for the team of {business or 'a small business'}. You answer {who} about how "
		"the business works — products, prices, hours, policies, how things are done here — from the business's details below "
		"ONLY. Never invent anything: no prices, times, rules or names that aren't written there. If the answer isn't there, say "
		"so plainly in one line, suggest asking their manager, and set known to false. Never give salaries, pay, payslips, bank "
		"details, ID numbers, passwords or anyone's personal details, even if asked — say that's for HR or the owner. You only "
		"read: you can't change, send, book or pay anything. Keep it short (1–5 lines), plain, numbers exactly as written. "
		"Reply in the language and script the person writes in. "
		'Reply with JSON only: {"answer": "...", "known": true|false}.')},
		{"role": "user", "content": f"The business's details:\n{facts}"},
		{"role": "assistant", "content": '{"answer": "Understood — I will answer only from these details.", "known": true}'}]
	turns = [h for h in history or [] if isinstance(h, dict) and h.get("role") in ("user", "assistant") and str(h.get("content") or "").strip()]
	msgs += [{"role": h["role"], "content": str(h["content"])[:1000]} for h in turns[-6:]]
	msgs.append({"role": "user", "content": (question or "").strip()[:500]})
	return msgs


def is_private(question: str) -> bool:
	"""Asked for pay, bank, ID or someone's personal details — answered without the model."""
	return bool(PRIVATE.search(question or ""))


def team_answer(text: str) -> dict:
	"""The model's reply → {answer, known}. Plain text is taken as the answer; nothing usable → not known."""
	raw = (text or "").strip()
	m = re.search(r"\{.*\}", raw, re.S)
	try:
		d = json.loads(m.group(0)) if m else {}
	except ValueError:
		d = {}
	if not isinstance(d, dict):
		d = {}
	answer = str(d.get("answer") or ("" if m else raw)).strip()
	if not answer:
		return {"answer": NOT_KNOWN, "known": False}
	return {"answer": answer[:1500], "known": d.get("known", True) is not False}
