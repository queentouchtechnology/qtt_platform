"""
QTT's own WhatsApp AI receptionist — the rules, pure (tested in
tests/test_receptionist_logic.py). The Chatwoot plumbing is
qtt_services.api.receptionist.

It knows two packs: the company (company.md, from queentouchtech.com) and
QTT OS (knowledge.md — the same pack as the in-app assistant and the Hermes
skill), plus the live plans and Managed Services lists. It answers, captures
leads, and hands over to a person whenever it isn't sure.
"""

import json
import os
import re

HERE = os.path.dirname(__file__)
MAX_HISTORY = 12
MAX_REPLY = 1200

SYSTEM = """You are the WhatsApp receptionist of Queen Touch Technology (QTT), an IT and software company in Thoothukudi, Tamil Nadu.
You answer people who message QTT on WhatsApp: about the company and its services, its own products, QTT OS (the business app) and its Managed Services.

Rules:
- Use ONLY the company facts, QTT OS knowledge, live plans and Managed Services below. Never invent prices, discounts, timelines, clients, team size or promises.
- Never discuss QTT's own marketing system or campaigns, internal tools or automations, servers or hosting providers, staff (beyond the founder named in the facts), other customers or their data. Say you can help with QTT's services and products.
- Never ask for or repeat passwords, OTP codes, card or bank details. You cannot take payments, change accounts or fix anything yourself.
- If someone wants a quote, a custom project, a demo, to buy, a call, has a complaint or account problem, or you aren't sure: answer what you can, ask for what's missing (name, business, what they need — one short question), and hand over to the team.
- If they ask for a person, hand over right away.
- WhatsApp style: short and friendly, 1–4 sentences or a few short bullet points, no markdown headings. Reply in the language and script the customer writes in (English, Tamil, Hindi, Arabic…).
- Reply as JSON only: {"answer": "...", "handover": false, "reason": "", "lead": {"name": "", "business": "", "need": ""}}
  handover true = a person from the team should take this conversation; reason = a few words for the team (e.g. "wants a quote for a website").
  lead = what the customer has told you so far (empty strings if unknown)."""

HANDOVER_REPLY = "Thank you! A person from our team will reply here soon."

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


def build_messages(*, company: str, knowledge: str, plans: str, services: str, history: list[dict], question: str,
				   customer: str | None = None) -> list[dict]:
	system = "\n\n".join([
		SYSTEM,
		"## Company facts\n" + company,
		"## QTT OS knowledge\n" + knowledge,
		"## Live QTT OS plans\n" + (plans or "Not published yet — the team will share prices."),
		"## Managed Services offered\n" + (services or "Not published yet."),
		"## The customer\n" + ("WhatsApp name: " + customer if customer else "Unknown name."),
	])
	msgs = [{"role": "system", "content": system}]
	for h in history[-MAX_HISTORY:]:
		if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
			msgs.append({"role": h["role"], "content": h["content"][:MAX_REPLY]})
	msgs.append({"role": "user", "content": (question or "").strip()[:1500]})
	return msgs


def parse_reply(text: str) -> dict:
	"""The model's JSON → {answer, handover, reason, lead}. Anything unreadable hands over."""
	data = None
	m = re.search(r"\{.*\}", (text or "").strip(), re.S)
	if m:
		try:
			data = json.loads(m.group(0))
		except ValueError:
			data = None
	if not isinstance(data, dict):
		return {"answer": HANDOVER_REPLY, "handover": True, "reason": "the assistant couldn't answer", "lead": {}}
	answer = str(data.get("answer") or "").strip()[:MAX_REPLY]
	handover = data.get("handover") in (True, 1, "true", "yes") or not answer
	lead = data.get("lead") if isinstance(data.get("lead"), dict) else {}
	lead = {k: str(lead.get(k) or "").strip()[:200] for k in ("name", "business", "need") if str(lead.get(k) or "").strip()}
	return {"answer": answer or HANDOVER_REPLY, "handover": handover, "reason": str(data.get("reason") or "").strip()[:200], "lead": lead}


def staff_note(*, reason: str, lead: dict, question: str) -> str:
	"""The private note the team sees in Onbox when the receptionist hands over."""
	lines = ["🤖 Receptionist handed this chat to the team" + (f" — {reason}" if reason else "") + "."]
	labels = {"name": "Name", "business": "Business", "need": "Needs"}
	lines += [f"{labels[k]}: {v}" for k, v in lead.items() if k in labels]
	lines.append(f"Last message: {question.strip()[:300]}")
	return "\n".join(lines)
