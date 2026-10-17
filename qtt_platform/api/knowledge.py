"""
Business knowledge (PROJ-0011 A1): one per business — what the WhatsApp receptionist, the Marketing assistant and the
team's Know your business bot answer from. The owner and admins read and edit it (Business › Business knowledge); the
other apps read it through for_tenant / customer_text / team_text.
"""

import json

import frappe
from frappe import _

from qtt_platform import knowledge_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

DT = "QTT Business Knowledge"
QUESTION = "QTT Knowledge Question"
DAILY_LIMIT = 60  # Know your business questions per person per day
GOVERNANCE = ["Tenant Owner", "Tenant Admin"]
TABLES = ("offerings", "faqs", "team_notes")


def _tenant() -> str:
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."))
	return tenant


def for_tenant(tenant: str) -> dict:
	"""The business's knowledge as plain data ({} when there's none yet)."""
	name = frappe.db.get_value(DT, {"tenant": tenant})
	if not name:
		return {}
	doc = frappe.get_doc(DT, name)
	out = {k: doc.get(k) for k in (*rules.TEXT, "tone", *rules.COLORS, *rules.SWITCHES)}
	for t in TABLES:
		out[t] = [{k: r.get(k) for k in ("item", "kind", "price", "details", "question", "answer", "audience", "title", "body", "roles", "active")
				   if r.get(k) is not None} for r in doc.get(t) or []]
	return out


def contacts(tenant: str) -> dict:
	"""Address, phone, WhatsApp, email and website from the business profile (not repeated in the knowledge)."""
	p = frappe.db.get_value("QTT Business Profile", {"tenant": tenant},
							["address_line1", "address_line2", "city", "state", "pincode", "phone", "whatsapp", "email", "website", "brand_color"],
							as_dict=True) or {}
	address = ", ".join(x for x in (p.get("address_line1"), p.get("address_line2"), p.get("city"), p.get("state"), p.get("pincode")) if x)
	return {"address": address, "phone": p.get("phone") or "", "whatsapp": p.get("whatsapp") or "", "email": p.get("email") or "",
			"website": p.get("website") or "", "brand_color": p.get("brand_color") or ""}


def customer_text(tenant: str, extra: str = "") -> str:
	return rules.customer_text(for_tenant(tenant), contacts(tenant), extra)


def team_text(tenant: str, roles: list[str]) -> str:
	return rules.team_text(for_tenant(tenant), roles, contacts(tenant))


def marketing_brief(tenant: str) -> str:
	return rules.marketing_brief(for_tenant(tenant), frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or tenant)


def brand_kit(tenant: str) -> dict:
	"""The locked brand: the business's own logo (Business › Profile), colours and fonts."""
	from frappe.utils import get_url

	logo = frappe.db.get_value("QTT Tenant", tenant, "logo")
	return {"logo": (logo if str(logo or "").startswith("http") else get_url(logo)) if logo else None,
			**rules.brand(for_tenant(tenant), contacts(tenant).get("brand_color") or "")}


def save_for(tenant: str, data: dict, *, user: str | None = None) -> dict:
	"""Write the cleaned edit (only the fields sent) — makes the record the first time."""
	clean = rules.clean(data)
	name = frappe.db.get_value(DT, {"tenant": tenant})
	doc = frappe.get_doc(DT, name) if name else frappe.new_doc(DT)
	before = rules.health(for_tenant(tenant)) if name else None
	doc.tenant = tenant
	for k, v in clean.items():
		if k in TABLES:
			doc.set(k, [])
			for row in v:
				doc.append(k, row)
		else:
			doc.set(k, v)
	doc.save(ignore_permissions=True)
	write_audit_event("business_knowledge_saved", tenant=tenant, target_doctype=DT, target_name=doc.name,
					  metadata={"fields": sorted(clean), "health_before": before})
	return for_tenant(tenant)


def _out(tenant: str) -> dict:
	k = for_tenant(tenant)
	return {"knowledge": k, "contacts": contacts(tenant), "brand": brand_kit(tenant), "health": rules.health(k),
			"tones": list(rules.TONES), "audiences": list(rules.AUDIENCES)}


@frappe.whitelist(methods=["GET"])
def get() -> dict:
	"""The business's knowledge with its contacts (from the profile), brand kit and health (score, what to add next).
	Owner and admins."""
	tenant = _tenant()
	require_tenant_role(tenant, GOVERNANCE)
	return _out(tenant)


@frappe.whitelist(methods=["POST"])
def save(data=None) -> dict:
	"""Save what the owner changed (only the fields sent): facts, products and services, Q&A (each for customers, the
	team or everyone), team notes (for everyone or some roles), tone, brand colours and fonts, sources. Owner and admins."""
	tenant = _tenant()
	require_tenant_role(tenant, GOVERNANCE)
	data = json.loads(data) if isinstance(data, str) else (data or {})
	save_for(tenant, data)
	return _out(tenant)


# ---- Know your business: the team's bot (PROJ-0011 A3) ------------------------------------------------------------------
# Every member of the business asks in the app (Know your business), or on QTT's WhatsApp number from the phone number on
# their account or employee record. Answers come only from the knowledge the team may see: the customer facts, Q&A for the
# team or everyone, and the team notes for their roles (the owner and admins: every note). Pay, bank, ID and personal
# details are refused before the model is asked. Each question is kept, so the owner sees what the knowledge is missing.

def member(tenant: str, user: str) -> dict | None:
	"""{name, roles} for an active member: their app roles as role keys, or ['*'] for the owner and admins."""
	m = frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": user, "status": "active"}, ["name", "tenant_role"], as_dict=True)
	if not m:
		return None
	roles = [r for r in frappe.get_all("QTT Product Access", filters={"membership": m.name, "status": "active"}, pluck="product_role") if r]
	keys = [rules.ALL_NOTES] if m.tenant_role in GOVERNANCE else sorted({rules.role_key(r) for r in roles})
	return {"name": frappe.db.get_value("User", user, "full_name") or user, "roles": keys, "labels": sorted(set(roles))}


def answer_team(tenant: str, user: str, question: str, *, history: list | None = None, channel: str = "App") -> dict:
	"""A team member's question → {answer, known}, kept for the owner. Private things are refused without the model."""
	from qtt_platform.api.assistant import complete_json

	question = (question or "").strip()[:500]
	who = member(tenant, user) or {"name": user, "roles": [], "labels": []}
	if rules.is_private(question):
		out = {"answer": rules.PRIVATE_ANSWER, "known": True}
	else:
		business = frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or ""
		msgs = rules.team_prompt(business=business, facts=team_text(tenant, who["roles"]), question=question, name=who["name"],
								 roles=who["labels"], history=history)
		text = ""
		for json_mode in (True, False):  # a blank JSON-mode reply gets one plain try
			try:
				text = complete_json(msgs, max_tokens=500, json_mode=json_mode, temperature=0.2, timeout=25)
			except Exception:
				frappe.log_error(title=f"Know your business: no answer for {tenant}")
			if (text or "").strip():
				break
		out = rules.team_answer(text) if (text or "").strip() else {"answer": "Sorry, I couldn't look that up just now. Please try again in a minute.",
																	"known": True, "failed": True}
	if not out.get("failed"):
		frappe.get_doc({"doctype": QUESTION, "tenant": tenant, "user": user, "channel": channel, "roles": ", ".join(who["labels"])[:140],
						"question": question, "answer": out["answer"], "known": int(out["known"])}).insert(ignore_permissions=True)
	return {"answer": out["answer"], "known": out["known"]}


def _digits(field: str) -> str:
	return f"replace(replace(replace(replace(replace({field}, ' ', ''), '-', ''), '+', ''), '(', ''), ')', '')"


def team_by_phone(phone) -> tuple[str, str] | None:
	"""(business, user) for a team member writing to QTT's WhatsApp: the number on their account or employee record, an
	active membership, and the business lets its team ask on WhatsApp. None otherwise."""
	import re

	digits = re.sub(r"[^0-9]", "", str(phone or ""))
	if len(digits) < 10:
		return None
	like = "%" + digits[-10:]
	users = frappe.db.sql(f"select name from `tabUser` where enabled=1 and {_digits('mobile_no')} like %s", (like,), pluck=True)
	if frappe.db.table_exists("Employee"):
		users += frappe.db.sql(f"select user_id from `tabEmployee` where status='Active' and ifnull(user_id, '') != '' "
							   f"and {_digits('cell_number')} like %s", (like,), pluck=True)
	for user in dict.fromkeys(users):
		for tenant in frappe.get_all("QTT Tenant Membership", filters={"user": user, "status": "active"}, pluck="tenant", order_by="modified desc"):
			if frappe.db.get_value(DT, {"tenant": tenant}, "team_whatsapp"):
				return tenant, user
	return None


def _count_today(user: str) -> int:
	from frappe.utils import today

	key = f"qtt_kyb:{user}:{today()}"
	n = int(frappe.cache.get_value(key) or 0) + 1
	frappe.cache.set_value(key, n, expires_in_sec=2 * 86400)
	return n


@frappe.whitelist(methods=["GET"])
def team_intro() -> dict:
	"""Know your business: the business's name, a few questions to start with (the team's own Q&A first) and, when the team
	may ask on WhatsApp and this person has a number on file, QTT's WhatsApp number. Any member."""
	tenant = _tenant()
	require_tenant_membership(tenant)
	k = for_tenant(tenant)
	starters = [f["question"] for f in k.get("faqs") or [] if f.get("active", 1) and f.get("audience") in ("Team", "Everyone")][:3]
	whatsapp = None
	if k.get("team_whatsapp") and frappe.db.get_value("User", frappe.session.user, "mobile_no"):
		whatsapp = frappe.db.get_single_value("QTT App Settings", "support_whatsapp") or None
	return {"business": frappe.db.get_value("QTT Tenant", tenant, "tenant_name") or "", "ready": bool(k), "starters": starters,
			"whatsapp": whatsapp}


@frappe.whitelist(methods=["POST"])
def ask(question: str, history=None) -> dict:
	"""Know your business: a team member's question about how the business works, answered from its knowledge (only what
	their roles may see; never pay, bank or personal details). {answer, known}. Any member; 60 a day each."""
	tenant = _tenant()
	require_tenant_membership(tenant)
	if len((question or "").strip()) < 2:
		frappe.throw(_("Type your question first."))
	if _count_today(frappe.session.user) > DAILY_LIMIT:
		frappe.throw(_("You've asked a lot today — try again tomorrow, or ask your manager."))
	if isinstance(history, str):
		try:
			history = json.loads(history)
		except ValueError:
			history = []
	return answer_team(tenant, frappe.session.user, question, history=history if isinstance(history, list) else [], channel="App")
