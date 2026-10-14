"""
Roles and access across apps: each app's spec (the `qtt_role_access` hook) plus the owner's
changes (QTT Role Access), so the app, the owner's table and the assistant all read one answer.
The rules themselves are in role_access_rules (pure, tested without a bench).

An app asks `areas(tenant, product, role)` on every request — the owner's change applies at once.
"""

import json

import frappe

from qtt_platform import role_access_rules as rules

DT = "QTT Role Access"
_CACHE = "qtt_role_access"


def specs() -> dict[str, dict]:
	"""{product: spec} for every installed app that describes its roles."""
	out = {}
	for path in frappe.get_hooks("qtt_role_access") or []:
		try:
			spec = frappe.get_attr(path)()
		except Exception:
			frappe.log_error(title=f"qtt_role_access: {path}")
			continue
		out[spec["product"]] = spec
	return out


def spec(product: str) -> dict | None:
	return specs().get(product)


def overrides(tenant: str) -> dict[str, dict[str, list[str]]]:
	"""{product: {role: [areas]}} — the owner's changes in this business (cached until the next change)."""
	cached = frappe.cache().hget(_CACHE, tenant)
	if cached is not None:
		return cached
	out: dict = {}
	if frappe.db.table_exists(DT):
		for row in frappe.get_all(DT, filters={"tenant": tenant}, fields=["product", "product_role", "areas"]):
			try:
				out.setdefault(row.product, {})[row.product_role] = list(json.loads(row.areas or "[]"))
			except ValueError:
				continue
	frappe.cache().hset(_CACHE, tenant, out)
	return out


def areas(tenant: str, product: str, role: str, product_spec: dict | None = None) -> list[str]:
	"""What this role may use in this app, in this business (owner's change or the default)."""
	product_spec = product_spec or spec(product)
	if not product_spec:
		return []
	return rules.effective(product_spec, role, overrides(tenant).get(product, {}).get(role))


def save(tenant: str, product: str, role: str, chosen: list[str] | None) -> None:
	"""Store a role's areas (None = back to the app's defaults) and tell everyone's app."""
	name = frappe.db.get_value(DT, {"tenant": tenant, "product": product, "product_role": role})
	if chosen is None:
		if name:
			frappe.delete_doc(DT, name, ignore_permissions=True, force=True)
	elif name:
		frappe.db.set_value(DT, name, "areas", json.dumps(chosen))
	else:
		frappe.get_doc({"doctype": DT, "tenant": tenant, "product": product, "product_role": role,
						"areas": json.dumps(chosen)}).insert(ignore_permissions=True)
	frappe.cache().hdel(_CACHE, tenant)
	from qtt_platform.realtime import notify_users, tenant_users

	notify_users(tenant_users(tenant), tenant=tenant, reason="role_access")


def tenant_products(tenant: str) -> list[dict]:
	"""The business's open apps that describe roles: [{product, display_name}]."""
	from qtt_platform.api.app_context import _workspace_products

	known = specs()
	return [{"product": p["product"], "display_name": p["display_name"]}
			for p in _workspace_products(tenant) if p["product"] in known]


def tables(tenant: str) -> list[dict]:
	"""The owner's Roles and access page: one table per app the business has."""
	known, changed = specs(), overrides(tenant)
	out = []
	for p in tenant_products(tenant):
		s = known[p["product"]]
		out.append({**rules.matrix(s, changed.get(p["product"], {})), "display_name": p["display_name"],
					"note": s.get("note")})
	return out


def describe(tenant: str, my_roles: dict[str, str] | None = None) -> str:
	"""For the assistant: every app's roles in this business and what each can do (owner's
	changes included), then what this person's own role can do."""
	known, changed = specs(), overrides(tenant)
	parts = []
	for p in tenant_products(tenant):
		s = known[p["product"]]
		line = f"{p['display_name']} roles — " + rules.describe(s, changed.get(p["product"], {}))
		if s.get("editable"):
			line += f". The owner can change: {', '.join(s['editable'])} (Business › Roles and access)"
		else:
			line += ". These are fixed"
		if s.get("note"):
			line += f". {s['note']}"
		parts.append(line + ".")
	for product, role in (my_roles or {}).items():
		s = known.get(product)
		if s and role in s["grants"]:
			labels = {a["key"]: a["label"] for a in s["areas"]}
			mine = areas(tenant, product, role, s)
			missing = [labels[a["key"]] for a in s["areas"] if a["key"] not in mine]
			parts.append(f"This person's role in {product_name(product)} is {role}: they can use "
						 f"{', '.join(labels[a] for a in mine) or 'nothing'}"
						 + (f"; they can't use {', '.join(missing)}" if missing else "") + ".")
	return " ".join(parts)


def product_name(product: str) -> str:
	return frappe.db.get_value("QTT Product", product, "display_name") or product
