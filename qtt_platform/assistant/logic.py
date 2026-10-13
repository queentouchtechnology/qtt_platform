"""
QTT Assistant rules (pure — no frappe; qtt_platform.api.assistant runs them).

The assistant answers only about QTT OS customer software and services, for
this person in this business. It may point to app screens — only ones in the
registry (screens.json) that this person can open — and the app turns them
into "Open …" buttons. Contextual tips per screen need no AI at all.
"""

import json
import os
import re

HERE = os.path.dirname(__file__)
MAX_LINKS = 3
MAX_ANSWER = 1500
MAX_HISTORY = 6


def load_registry() -> list[dict]:
	with open(os.path.join(HERE, "screens.json"), encoding="utf-8") as f:
		return json.load(f)["screens"]


def load_catalog() -> dict:
	"""screens.json beyond the screens: feature names and the shift compatibility list."""
	with open(os.path.join(HERE, "screens.json"), encoding="utf-8") as f:
		doc = json.load(f)
	return {"features": doc.get("features") or {}, "shift_types": doc.get("shift_types") or [], "device_types": doc.get("device_types") or []}


def shift_rows(catalog: dict, features: set[str] | None) -> list[dict]:
	"""Each kind of shift for this business: ready (works now), on (its feature is on), off (switch
	on the feature in Business type) or no (not supported — `how` says what to do instead)."""
	names = catalog.get("features") or {}
	out = []
	for s in catalog.get("shift_types") or []:
		needs = s.get("needs")
		status = "ready" if not needs else "no" if needs == "no" else ("on" if needs in (features or set()) else "off")
		out.append({"name": s["name"], "example": s["example"], "how": s["how"], "status": status,
					"feature": names.get(needs) if needs and needs != "no" else None})
	return out


def device_rows(catalog: dict) -> list[dict]:
	"""Kinds of biometric device: ready (works), ask (QTT sets it up with you), no (not supported)."""
	return [{"name": s["name"], "example": s["example"], "how": s["how"], "status": s.get("status") or "ready", "feature": None}
			for s in catalog.get("device_types") or []]


def load_knowledge() -> str:
	with open(os.path.join(HERE, "knowledge.md"), encoding="utf-8") as f:
		return f.read()


def can_open(screen: dict, ctx: dict) -> bool:
	"""ctx: {"products": {key: role}, "owner": bool, "manager": bool}."""
	product = screen.get("product")
	roles = screen.get("roles") or ["*"]
	if product:
		if product not in (ctx.get("products") or {}):
			return False
		mine = ctx["products"][product]
	else:
		mine = None
	for r in roles:
		if r == "*":
			return True
		if r == "@owner" and ctx.get("owner"):
			return True
		if r == "@manager" and ctx.get("manager"):
			return True
		if mine and r == mine:
			return True
	return False


def allowed_screens(registry: list[dict], ctx: dict) -> list[dict]:
	return [s for s in registry if can_open(s, ctx)]


def tips_for(registry: list[dict], screen_id: str, ctx: dict, conditions: set[str]) -> list[dict]:
	"""Contextual tips for a screen — only ones whose condition holds and whose
	link this person can open."""
	allowed = {s["id"] for s in allowed_screens(registry, ctx)}
	screen = next((s for s in registry if s["id"] == screen_id), None)
	if not screen or screen_id not in allowed:
		return []
	out = []
	for t in screen.get("tips") or []:
		if t.get("when") and t["when"] not in conditions:
			continue
		link = t.get("link")
		out.append({"text": t["text"], "link": link if link in allowed else None, "label": t.get("label") if link in allowed else None})
	return out


def guide_for(registry: list[dict], screen_id: str, ctx: dict, industry: str | None = None, catalog: dict | None = None) -> dict | None:
	"""A screen's "How to set up" guide (screens.json) for someone who can open it: intro, steps,
	and suggestions — the ones for this business's type first, then the general ones ("*")."""
	allowed = {s["id"] for s in allowed_screens(registry, ctx)}
	screen = next((s for s in registry if s["id"] == screen_id), None)
	if not screen or screen_id not in allowed or not screen.get("guide"):
		return None
	g = screen["guide"]
	mine = [s for s in g.get("suggestions") or [] if industry and s.get("for") == industry]
	general = [s for s in g.get("suggestions") or [] if s.get("for") == "*"]
	if g.get("all_suggestions"):  # choosing a business type: every type's, theirs first
		general = [s for s in g.get("suggestions") or [] if s not in mine]
	out = {"title": screen["title"], "intro": g.get("intro") or "", "steps": list(g.get("steps") or []),
		   "suggestions": [{"for": s["for"], "text": s["text"]} for s in mine + general]}
	if g.get("shift_types"):
		out["shift_types"] = shift_rows(catalog or load_catalog(), set(ctx.get("features") or []))
	if g.get("device_types"):
		out["device_types"] = device_rows(catalog or load_catalog())
	if g.get("faq"):
		out["faq"] = [{"q": f["q"], "a": f["a"]} for f in g["faq"]]
	return out


def guide_text(screen: dict) -> str:
	"""A screen's guide as plain text for the assistant (every suggestion, with whom it suits)."""
	g = screen.get("guide") or {}
	lines = [g.get("intro", "")] + [f"{i}. {s}" for i, s in enumerate(g.get("steps") or [], 1)]
	lines += [f"- Suggestion ({'any business' if s['for'] == '*' else s['for']}): {s['text']}" for s in g.get("suggestions") or []]
	if g.get("shift_types"):
		lines.append("Which kinds of shift work (needs = a feature to switch on in Business type):")
		for s in shift_rows(load_catalog(), None):
			need = "" if s["status"] == "no" else (f"needs {s['feature']}. " if s["feature"] else "works for every business. ")
			lines.append(f"- {s['name']} ({s['example']}): {need}{s['how']}")
	if g.get("device_types"):
		lines.append("Which devices work:")
		for s in device_rows(load_catalog()):
			lines.append(f"- {s['name']} ({s['example']}): {dict(ready='works', ask='QTT sets it up', no='not supported')[s['status']]}. {s['how']}")
	for f in g.get("faq") or []:
		lines.append(f"Q: {f['q']} — A: {f['a']}")
	return "\n".join(x for x in lines if x)


SYSTEM = """You are QTT Assistant inside the QTT OS app by Queen Touch Technology.
You help the person use QTT OS customer software and services: the app, Office Pulse, Orbitra, Onbox and Managed Services, their plans and how to do things.

Rules:
- Use ONLY the knowledge, live plans, services and screen list below. If something isn't there, say you're not sure and suggest Account › Help and support.
- Never discuss Queen Touch Technology's own marketing system or campaigns, internal tools, automations, servers, staff, other businesses, or anything outside QTT OS. Politely say you can only help with QTT OS.
- Never ask for or reveal passwords, codes, keys or personal data. You cannot change anything yourself — explain the steps and point to the screen.
- Respect the person's role: only suggest screens from the "Screens this person can open" list; if their role can't do something, say who can (e.g. "ask your HR admin").
- Be short and practical: 1–5 sentences or a few numbered steps, plain words, in the language of the question.
- Reply as JSON only: {"answer": "...", "links": [{"label": "Open Leave", "screen": "<screen id>"}]} — at most 3 links, ids exactly from the list, or [] if none fits."""


def build_messages(*, knowledge: str, plans: str, services: str, screens: list[dict], who: str, screen_id: str | None,
				   history: list[dict] | None, question: str) -> list[dict]:
	screen_lines = "\n".join(f"- {s['id']}: {s['path']} — {s['what']}" for s in screens)
	current = next((s for s in screens if s["id"] == screen_id), None)
	context = (f"{who}\nThey are on: {current['path']} ({current['id']})." if current else who)
	if current and current.get("guide"):
		context += "\n\nHow to set up this screen (use it for set-up questions; suggest what fits their business type):\n" + guide_text(current)
	system = "\n\n".join([
		SYSTEM,
		"## Knowledge\n" + knowledge,
		"## Live plans (per app)\n" + (plans or "Not available."),
		"## Managed Services offered\n" + (services or "Not available."),
		"## Screens this person can open\n" + screen_lines,
		"## This person\n" + context,
	])
	msgs = [{"role": "system", "content": system}]
	for h in (history or [])[-MAX_HISTORY:]:
		if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
			msgs.append({"role": h["role"], "content": h["content"][:MAX_ANSWER]})
	msgs.append({"role": "user", "content": question.strip()[:1000]})
	return msgs


def parse_reply(text: str, allowed_ids: set[str]) -> dict:
	"""The model's JSON → {answer, links}; links only to screens this person can open."""
	data = None
	raw = (text or "").strip()
	m = re.search(r"\{.*\}", raw, re.S)
	if m:
		try:
			data = json.loads(m.group(0))
		except ValueError:
			data = None
	if not isinstance(data, dict):
		data = {"answer": raw, "links": []}
	answer = str(data.get("answer") or "").strip()[:MAX_ANSWER] or "Sorry, I couldn't answer that. Try asking another way."
	links, seen = [], set()
	for link in data.get("links") or []:
		if not isinstance(link, dict):
			continue
		sid = str(link.get("screen") or "")
		if sid in allowed_ids and sid not in seen:
			seen.add(sid)
			links.append({"label": str(link.get("label") or "Open")[:40], "screen": sid})
		if len(links) >= MAX_LINKS:
			break
	return {"answer": answer, "links": links}


def plans_text(plans: list[dict], products: dict[str, str]) -> str:
	"""plans: [{product, plan_code, display_name, base_price, billing_period, trial_days, features: [{feature_key, limit_value}]}]."""
	lines = []
	for p in plans:
		name = products.get(p["product"], p["product"])
		price = p.get("base_price")
		period = p.get("billing_period") or "month"
		# A plan without a price set isn't free — the price simply isn't published yet.
		cost = "price on request (contact Queen Touch Technology)" if not price else "₹%g per %s" % (price, period.rstrip("ly") if period.endswith("ly") else period)
		trial = ", %s-day free trial" % p["trial_days"] if p.get("trial_days") else ""
		feats = ", ".join("%s: %s" % (f["feature_key"], f["limit_value"]) for f in p.get("features") or [] if f.get("feature_key"))
		label = p.get("display_name") or p["plan_code"]
		lines.append("- %s — %s: %s%s%s" % (name, label, cost, trial, " (%s)" % feats if feats else ""))
	return "\n".join(lines)


def services_text(services: list[dict]) -> str:
	lines = []
	for s in services:
		monthly, setup = s.get("monthly_price") or 0, s.get("setup_price") or 0
		parts = (["₹%g setup" % setup] if setup else []) + (["₹%g/month" % monthly] if monthly else [])
		# No price set means it isn't published yet — never "free".
		price = " + ".join(parts) or "price on request (contact Queen Touch Technology)"
		lines.append("- %s (%s): %s — %s" % (s["title"], s.get("category") or "service", s.get("summary") or "", price))
	return "\n".join(lines)
