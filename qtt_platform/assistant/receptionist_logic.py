"""
QTT's own WhatsApp AI receptionist — the rules, pure (tested in
tests/test_receptionist_logic.py). The Chatwoot plumbing is
qtt_services.api.receptionist.

It knows: the company facts (company.md), the whole website
(site_knowledge — a map of every page plus the pages that match the
question), QTT OS (knowledge.md — the same pack as the in-app assistant and
the Hermes skill), and the live plans and Managed Services lists. It talks
like a knowledgeable member of the team, captures leads, and hands over to a
person when the customer is ready or it isn't sure.
"""

import json
import os
import re

HERE = os.path.dirname(__file__)
MAX_HISTORY = 12
MAX_REPLY = 1200

SYSTEM = """You are on Queen Touch Technology's WhatsApp — the friendly, knowledgeable first person a customer talks to at QTT, an IT and software company in Thoothukudi, Tamil Nadu that serves clients across India and abroad.
You know QTT inside out: every service, package, solution, product, case study and location on the website, QTT OS (QTT's business app) and its Managed Services.

How you talk:
- Like a helpful person on QTT's team, not a form or a FAQ: warm, natural, confident, plain words. Vary your wording; no robotic phrases like "As an AI" or "I'm here to assist you".
- Mirror the customer: their language and script (English, Tamil, Tanglish, Hindi, Arabic…), how formal they are, how long they write. Use their first name now and then if you know it.
- WhatsApp length: usually 1–4 short sentences; a few short bullets only when listing options. No headings, no tables, at most one emoji.
- Understand what they really need, then recommend the most relevant QTT service or package and say why it fits. Mention a matching case study when there is one. Share the page link (e.g. www.queentouchtech.com/packages/software-testing-qa/) when it helps.
- End with one natural question that moves things forward (their business, what they want to build, their timeline) — never a list of questions.
- For a greeting, greet back warmly and ask how you can help, mentioning two or three things QTT does.
- Don't say you're an AI unprompted. If they sincerely ask whether they're talking to a bot or a person, be honest: you're QTT's virtual assistant, and a person from the team can join anytime.

What you can say:
- Facts only from the company facts, website pages, site map, QTT OS knowledge, live plans and Managed Services below. If a detail isn't there (a price, a timeline, a feature), say the team will confirm it — never guess or promise.
- Prices: only as written on the website pages or live lists given to you. Custom work is quoted by the team after understanding the need.
- Never discuss QTT's own marketing system or campaigns, internal tools or automations, servers or hosting providers, staff beyond what the website says, other customers' private details, or anything unrelated to QTT. Politely bring it back to how QTT can help.
- Never ask for or repeat passwords, OTP codes, card or bank details. You can't take payments, change accounts or fix anything yourself.

Handing over to the team (handover true):
- Right away if they ask for a person, a call or a meeting, have a complaint or an account / payment problem, or you can't answer from what you know.
- For a quote, demo, custom project or to buy: first understand the need and recommend the fit; once you know their name or business and what they need — or they want to proceed — hand over so the team can follow up. Tell them the team will reply here.

Reply as JSON only: {"answer": "...", "handover": false, "reason": "", "lead": {"name": "", "business": "", "need": ""}}
handover true = a person from the team should take this conversation; reason = a few words for the team (e.g. "wants a quote for a bakery website").
lead = what the customer has told you so far (empty strings if unknown)."""

HANDOVER_REPLY = "Thank you! A person from our team will reply here soon."

# When the AI can't answer a plain hello, greet anyway — a greeting never needs the team.
WELCOME_REPLY = ("Hi! 👋 Welcome to Queen Touch Technology. We build websites, online stores, apps, AI and WhatsApp "
				 "automation — and QTT OS, our app to run a small business. What can I help you with today?")
_GREETING = re.compile(
	r"^\s*(hi+|hai+|hello+|helo+|hey+|hii+|vanakkam|vanakam|namaste|namaskar|good\s+(morning|afternoon|evening|day)|"
	r"hlo|hlw|hy|yo|greetings|salaam|assalamu?\s*alaikum|வணக்கம்|नमस्ते|مرحبا|السلام عليكم)"
	r"[\s!.,🙏👋😊]*(sir|madam|mam|maam|team|qtt|there|bro|anna|akka)?[\s!.,🙏👋😊]*$",
	re.I,
)
# Asked for a person again while the team hasn't replied yet: no new note, just this.
WAITING_REPLY = ("Our team has your message and will reply here soon. Meanwhile, I'm happy to help with "
				 "anything else — just ask.")

# Explicit "let me talk to a person" — handed over without asking the model.
_PERSON = re.compile(
	r"\b(talk|speak|chat|connect)( me)? (to|with) (a |an |the |your )?(human|person|someone|agent|staff|team|executive|sathish)\b"
	r"|\b(real person|human being|customer care|call me( back)?|please call|need a call)\b|^\s*(human|agent|person)\s*[.!?]*\s*$"
	r"|மனிதரிடம் பேச|ஆளிடம் பேச|கால் பண்ணுங்க|போன் பண்ணுங்க|इंसान से बात|किसी से बात|कॉल करें|मुझे कॉल|موظف|شخص حقيقي|اتصل بي",
	re.I,
)


def load_company() -> str:
	with open(os.path.join(HERE, "company.md"), encoding="utf-8") as f:
		return f.read()


def wants_person(text: str) -> bool:
	return bool(_PERSON.search(text or ""))


def is_greeting(text: str) -> bool:
	"""Just a hello ("Hai", "Hello sir", "Vanakkam 🙏") — nothing else asked yet."""
	return bool(_GREETING.match(text or ""))


def assist_while_waiting(*, handed_over_at: float | None, team_replied: bool, assigned: bool) -> bool:
	"""Keep answering in an open chat until a person takes it: the chat stays the team's (open), but the
	customer is never left without a reply. Stops once someone is assigned or replies.

	handed_over_at may be unknown — the remembered time is cleared by a deploy and the handover note drops
	out of the latest messages Chatwoot returns once a chat is long — and that must never mean silence:
	nobody assigned and no reply from a person (since the handover, or in the messages we can see) is
	enough. (Until 2026-10-17 an unknown time meant "never handed over" and the customer got no answer.)"""
	return not team_replied and not assigned


def history_from_chatwoot(messages: list[dict], upto_id: int | None = None) -> list[dict]:
	"""Chatwoot conversation messages (oldest first) → chat turns.
	message_type 0 = customer, 1 = us (bot or staff); notes, activity and
	template sends (e.g. sign-up codes) are left out. Stops before `upto_id`
	(the message being answered)."""
	turns = []
	for m in messages:
		if upto_id is not None and m.get("id") == upto_id:
			break
		if m.get("private") or m.get("message_type") not in (0, 1):
			continue
		if (m.get("additional_attributes") or {}).get("template_params") or (m.get("content_attributes") or {}).get("template_params"):
			continue
		text = str(m.get("content") or "").strip()
		if not text:
			continue
		turns.append({"role": "user" if m["message_type"] == 0 else "assistant", "content": text[:MAX_REPLY]})
	return turns[-MAX_HISTORY:]


def search_text(history: list[dict], question: str) -> str:
	"""What to look up on the website: this message plus the customer's last two (follow-ups like "how much?")."""
	asked = [h["content"] for h in history if h.get("role") == "user"][-2:]
	return " ".join([*asked, question or ""])


def build_messages(*, company: str, knowledge: str, plans: str, services: str, history: list[dict], question: str,
				   customer: str | None = None, site_map: str = "", site_pages: str = "") -> list[dict]:
	system = "\n\n".join([
		SYSTEM,
		"## Company facts\n" + company,
		"## Website — every page (site map)\n" + (site_map or "Not available."),
		"## Website pages that match this conversation\n" + (site_pages or "None — use the facts and site map above."),
		"## QTT OS knowledge\n" + knowledge,
		"## Live QTT OS plans\n" + (plans or "Not published yet — the team will share prices."),
		"## Managed Services offered\n" + (services or "Not published yet."),
		"## The customer\n" + ("WhatsApp name: " + customer if customer else "Unknown name."),
	])
	msgs = [{"role": "system", "content": system}]
	for h in history[-MAX_HISTORY:]:
		if h.get("role") == "user" and isinstance(h.get("content"), str):
			msgs.append({"role": "user", "content": h["content"][:MAX_REPLY]})
		elif h.get("role") == "assistant" and isinstance(h.get("content"), str):
			# Our earlier replies in the same JSON shape — plain-text turns make DeepSeek's JSON mode reply blank.
			msgs.append({"role": "assistant", "content": json.dumps({"answer": h["content"][:MAX_REPLY], "handover": False}, ensure_ascii=False)})
	msgs.append({"role": "user", "content": (question or "").strip()[:1500]})
	return msgs


def parse_reply(text: str, *, plain_ok: bool = False) -> dict:
	"""The model's JSON → {answer, handover, reason, lead}. Anything unreadable hands over —
	unless `plain_ok` (the retry without JSON mode), where plain text is the answer itself."""
	data = None
	raw = (text or "").strip()
	m = re.search(r"\{.*\}", raw, re.S)
	if m:
		try:
			data = json.loads(m.group(0))
		except ValueError:
			data = None
	if not isinstance(data, dict) and plain_ok and raw and not raw.startswith("{"):
		data = {"answer": raw, "handover": False}
	if not isinstance(data, dict):
		return {"answer": HANDOVER_REPLY, "handover": True, "reason": "the assistant couldn't answer", "lead": {}}
	answer = str(data.get("answer") or "").strip()[:MAX_REPLY]
	handover = data.get("handover") in (True, 1, "true", "yes") or not answer
	lead = data.get("lead") if isinstance(data.get("lead"), dict) else {}
	lead = {k: str(lead.get(k) or "").strip()[:200] for k in ("name", "business", "need") if str(lead.get(k) or "").strip()}
	return {"answer": answer or HANDOVER_REPLY, "handover": handover, "reason": str(data.get("reason") or "").strip()[:200], "lead": lead}


HANDOVER_MARK = "🤖 Receptionist handed this chat to the team"


def last_handover_at(messages: list[dict]) -> float | None:
	"""When the receptionist last handed this chat over — from its own private note in the chat
	(Chatwoot messages, any order). None when it never did."""
	times = [float(m.get("created_at") or 0) for m in messages
			 if m.get("private") and str(m.get("content") or "").startswith(HANDOVER_MARK)]
	return max(times) if times else None


def staff_note(*, reason: str, lead: dict, question: str) -> str:
	"""The private note the team sees in Onbox when the receptionist hands over."""
	lines = [HANDOVER_MARK + (f" — {reason}" if reason else "") + "."]
	labels = {"name": "Name", "business": "Business", "need": "Needs"}
	lines += [f"{labels[k]}: {v}" for k, v in lead.items() if k in labels]
	lines.append(f"Last message: {question.strip()[:300]}")
	return "\n".join(lines)
