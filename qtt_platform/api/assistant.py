"""
QTT Assistant for the app (rules and prompt in qtt_platform.assistant.logic):

  tips(screen)                    contextual tips for a screen — instant, no AI,
                                  only what applies here (e.g. "work from home"
                                  on Leave when the business allows it)
  ask(question, screen, history)  an answer about QTT OS for this person, with
                                  "Open …" links to screens they can open

Knows only QTT OS customer software and services: the knowledge pack, live
plans and the Managed Services catalogue — never QTT's marketing system or
internal operations. Model, key and daily limit: QTT App Settings › QTT
Assistant (OpenAI-compatible API, DeepSeek by default). Free for customers.
"""

import json

import frappe
import requests
from frappe.rate_limiter import rate_limit
from frappe.utils import today

from qtt_platform.assistant import logic
from qtt_platform.errors import fail, ok
from qtt_platform.tenant.context import resolve_active_tenant

SETTINGS = "QTT App Settings"
OWNER_ROLES = ("Tenant Owner", "Tenant Admin")
HIDDEN_PRODUCT_WORDS = ("MARKETING",)  # never part of the customer assistant


def _settings():
	return frappe.get_cached_doc(SETTINGS)


def _enabled() -> bool:
	v = _settings().get("assistant_enabled")
	return True if v is None else bool(int(v))


# Office Pulse capability switches (Office Pulse Workspace) — which kinds of shift work for this business.
CAPABILITY_FIELDS = ("cap_flexible_cycles", "cap_sites", "cap_requests", "cap_split_shifts", "cap_overtime_pay", "cap_coverage", "cap_offline")


def _context(user: str, tenant: str) -> tuple[dict, set[str], str]:
	"""(ctx for screen access, true conditions, a sentence about the person)."""
	m = frappe.db.get_value("QTT Tenant Membership", {"user": user, "tenant": tenant, "status": "active"},
							["name", "tenant_role"], as_dict=True)
	if not m:
		frappe.throw("Not a member of this business.", frappe.PermissionError)
	products = {r.product: r.product_role for r in frappe.get_all(
		"QTT Product Access", filters={"tenant": tenant, "membership": m.name, "status": "active"}, fields=["product", "product_role"])}
	manager, conditions, industry, features = False, set(), None, []
	if "QTT_OFFICE_PULSE" in products and frappe.db.table_exists("Office Pulse Workspace"):
		caps = [c for c in CAPABILITY_FIELDS if frappe.db.has_column("Office Pulse Workspace", c)]
		fields = ["company", "allow_outside"] + (["industry"] if frappe.db.has_column("Office Pulse Workspace", "industry") else []) + caps
		ws = frappe.db.get_value("Office Pulse Workspace", {"tenant": tenant}, fields, as_dict=True)
		if ws:
			industry = ws.get("industry") or None
			features = [c.removeprefix("cap_") for c in caps if ws.get(c)]
			if ws.allow_outside:
				conditions.add("pulse.allow_outside")
			emp = frappe.db.get_value("Employee", {"user_id": user, "company": ws.company, "status": "Active"}, "name")
			manager = bool(emp and frappe.db.count("Employee", {"reports_to": emp, "status": "Active"}))
	names = {p.name: p.display_name for p in frappe.get_all("QTT Product", fields=["name", "display_name"])}
	business = frappe.db.get_value("QTT Tenant", tenant, "tenant_name")
	who = (f"Name: {frappe.utils.get_fullname(user)}. Business: {business} — their role: {m.tenant_role}. "
		   f"Apps and roles: {', '.join(f'{names.get(k, k)} ({v})' for k, v in products.items()) or 'none yet'}. "
		   f"Manages people: {'yes' if manager else 'no'}." + (f" Business type (Office Pulse): {industry}." if industry else ""))
	return {"products": products, "owner": m.tenant_role in OWNER_ROLES, "manager": manager, "industry": industry,
			"features": features}, conditions, who


def _catalogue() -> tuple[str, str]:
	products = {p.name: p.display_name for p in frappe.get_all("QTT Product", filters={"status": "active"}, fields=["name", "display_name"])
				if not any(w in p.name.upper() for w in HIDDEN_PRODUCT_WORDS)}
	plans = frappe.get_all("QTT Plan", filters={"product": ["in", list(products) or [""]]},
						   fields=["name", "product", "plan_code", "display_name", "base_price", "billing_period", "trial_days"],
						   order_by="product asc, base_price asc")
	feats = frappe.get_all("QTT Plan Feature", filters={"parent": ["in", [p.name for p in plans] or [""]]},
						   fields=["parent", "feature_key", "limit_value"])
	for p in plans:
		p["features"] = [f for f in feats if f.parent == p.name]
	services = []
	if frappe.db.table_exists("Managed Service Type"):
		services = frappe.get_all("Managed Service Type", filters={"active": 1},
								  fields=["title", "category", "summary", "monthly_price", "setup_price"], order_by="sort_order asc")
	return logic.plans_text(plans, products), logic.services_text(services)


def api_key() -> str | None:
	s = _settings()
	return s.get_password("assistant_api_key", raise_exception=False) if s.get("assistant_api_key") else None


def complete_json(messages: list[dict], *, max_tokens: int = 700, json_mode: bool = True, temperature: float = 0.2) -> str:
	"""One JSON reply from the assistant model (QTT App Settings › QTT Assistant). Raises on any failure.
	Also used by QTT's WhatsApp receptionist (qtt_services.api.receptionist), which retries with
	json_mode=False when DeepSeek's JSON mode comes back blank."""
	s = _settings()
	key = api_key()
	if not key:
		raise RuntimeError("QTT Assistant has no API key.")
	base = (s.get("assistant_base_url") or "https://api.deepseek.com").rstrip("/")
	body = {"model": s.get("assistant_model") or "deepseek-chat", "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
	if json_mode:
		body["response_format"] = {"type": "json_object"}
	r = requests.post(f"{base}/chat/completions", timeout=45, headers={"Authorization": f"Bearer {key}"}, json=body)
	r.raise_for_status()
	return r.json()["choices"][0]["message"]["content"]


def catalogue() -> tuple[str, str]:
	"""(live plans, Managed Services) as text — also for the receptionist."""
	return _catalogue()


def _who_and_where():
	user = frappe.session.user
	tenant = resolve_active_tenant(user)
	if not tenant:
		frappe.throw("Choose your business first.", frappe.PermissionError)
	return user, tenant


@frappe.whitelist(methods=["GET"])
def tips(screen: str) -> list[dict]:
	user, tenant = _who_and_where()
	ctx, conditions, _who = _context(user, tenant)
	return logic.tips_for(logic.load_registry(), screen, ctx, conditions)


@frappe.whitelist(methods=["GET"])
def questions(screen: str) -> list[str]:
	"""Suggested questions for the screen the person is on (screens.json "ask")."""
	user, tenant = _who_and_where()
	ctx, _conditions, _who = _context(user, tenant)
	return logic.questions_for(logic.load_registry(), screen, ctx)


@frappe.whitelist(methods=["GET"])
def guide(screen: str) -> dict | None:
	"""A screen's "How to set up" guide, suggestions for this business's type first (no AI)."""
	user, tenant = _who_and_where()
	ctx, _conditions, _who = _context(user, tenant)
	return logic.guide_for(logic.load_registry(), screen, ctx, ctx.get("industry"))


def _count_today(user: str) -> int:
	key = f"qtt_assistant:{user}:{today()}"
	n = int(frappe.cache.get_value(key) or 0) + 1
	frappe.cache.set_value(key, n, expires_in_sec=2 * 86400)
	return n


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=3600)
def ask(question: str, screen: str | None = None, history=None) -> dict:
	if not _enabled():
		return fail("ASSISTANT_OFF", "The assistant is switched off. Use Account › Help and support.")
	question = (question or "").strip()
	if len(question) < 2:
		return fail("EMPTY", "Ask a question about QTT OS.")
	s = _settings()
	if not api_key():
		return fail("ASSISTANT_OFF", "The assistant isn't set up yet. Use Account › Help and support.")
	user, tenant = _who_and_where()
	limit = int(s.get("assistant_daily_limit") or 30)
	if _count_today(user) > limit:
		return fail("LIMIT", "You've asked a lot today — try again tomorrow, or use Account › Help and support.")

	ctx, _conditions, who = _context(user, tenant)
	registry = logic.load_registry()
	screens = logic.allowed_screens(registry, ctx)
	plans, services = _catalogue()
	if isinstance(history, str):
		try:
			history = json.loads(history)
		except ValueError:
			history = []
	messages = logic.build_messages(knowledge=logic.load_knowledge(), plans=plans, services=services, screens=screens,
									who=who, screen_id=screen, history=history if isinstance(history, list) else [], question=question)
	try:
		text = complete_json(messages)
	except Exception:
		frappe.log_error(title="QTT Assistant: model call failed", message=frappe.get_traceback())
		return fail("UNAVAILABLE", "The assistant is busy right now. Please try again in a minute.")
	return ok(logic.parse_reply(text, {x["id"] for x in screens}))
