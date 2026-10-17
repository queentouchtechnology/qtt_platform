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
from qtt_platform.tenant.guards import require_tenant_role

DT = "QTT Business Knowledge"
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
	out = {k: doc.get(k) for k in (*rules.TEXT, "tone", *rules.COLORS, *rules.SOURCES)}
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
