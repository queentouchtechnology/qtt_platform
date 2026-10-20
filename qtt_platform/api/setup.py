"""
Getting started: the welcome every new person sees once, and each app's set-up guide (what to do
first, what next, what's optional — with live status). Content: assistant/welcome.json and each
app's `qtt_setup_steps` hook (pure ordering: setup_rules.py).
"""

import json
import os

import frappe

from qtt_platform import setup_rules
from qtt_platform.assistant import logic

_WELCOME = None
HIDDEN_PRODUCT_WORDS = ("LMS", "QMP")


def _welcome_spec() -> dict:
	global _WELCOME
	if _WELCOME is None:
		with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assistant", "welcome.json"), encoding="utf-8") as f:
			_WELCOME = json.load(f)
	return _WELCOME


def _who():
	from qtt_platform.api.assistant import _context
	from qtt_platform.tenant.context import resolve_active_tenant

	user = frappe.session.user
	tenant = resolve_active_tenant(user)
	if not tenant:
		frappe.throw("Choose your business first.")
	ctx, _conditions, _who_text = _context(user, tenant)
	return user, tenant, ctx


def _for_me(item: dict, product: str | None, ctx: dict) -> bool:
	return logic.can_open({"product": product, "roles": item.get("for") or ["*"]}, ctx)


def _roles(tenant: str, product: str) -> dict | None:
	"""Who can do what in this app, in this business (the owner's changes included) — every role,
	what it can and can't use, and whether the owner can change it."""
	from qtt_platform import role_access, role_access_rules

	spec = role_access.spec(product)
	if not spec:
		return None
	m = role_access_rules.matrix(spec, role_access.overrides(tenant).get(product, {}))
	roles = []
	for i, r in enumerate(m["roles"]):
		roles.append({"role": r["key"], "label": r.get("label") or r["key"], "about": r.get("about"),
					  "can": [row["label"] for row in m["rows"] if row["cells"][i]["on"]],
					  "cant": [row["label"] for row in m["rows"] if not row["cells"][i]["on"]],
					  "changeable": r["key"] in spec.get("editable", [])})
	return {"roles": roles, "editable": m["editable"], "note": spec.get("note")}


def build(user: str, tenant: str, with_roles: bool = True) -> list[dict]:
	"""Every set-up guide this person can act on, arranged (each app decides who gets its guide)."""
	out = []
	for path in frappe.get_hooks("qtt_setup_steps") or []:
		try:
			g = frappe.get_attr(path)(user, tenant)
		except Exception:
			frappe.log_error(title=f"qtt setup steps: {path}")
			continue
		if not g:
			continue
		guide = {**{k: g[k] for k in ("product", "screen", "title", "intro", "explainers") if k in g}, **setup_rules.arrange(g["steps"])}
		if with_roles:
			try:
				guide["roles"] = _roles(tenant, g["product"])
			except Exception:
				frappe.log_error(title=f"qtt setup roles: {g['product']}")
		out.append(guide)
	return out


@frappe.whitelist(methods=["GET"])
def guides() -> list[dict]:
	"""Every set-up guide this person can act on (HR's Office Pulse guide, the owner's Services guide, …)."""
	user, tenant, _ctx = _who()
	return build(user, tenant)


def home_cards(user: str, tenant: str) -> list[dict]:
	"""Home (`qtt_home_cards`): for each unfinished guide, how far along it is and the next step."""
	out = []
	for g in build(user, tenant, with_roles=False):
		if g["complete"] or not g.get("next"):
			continue
		out.append({"key": f"setup:{g['product']}", "product": g["product"], "priority": 82, "tone": "info", "icon": "rocket",
					"title": "{guide}: {done} of {total} done", "body": "Next: {step}",
					"args": {"guide": g["title"], "done": g["done"], "total": g["total"], "step": g["next"]["title"]},
					"action": {"label": "Open the set-up guide", "kind": "screen", "target": g["screen"]}})
	return out


@frappe.whitelist(methods=["GET"])
def welcome() -> dict:
	"""What QTT OS does for this person: their apps (lines for their role), the everyday helpers,
	and — for owners — the separate companies QTT OS replaces and the apps they could add."""
	user, tenant, ctx = _who()
	spec = _welcome_spec()
	names = {p.name: p for p in frappe.get_all("QTT Product", filters={"status": "active"}, fields=["name", "display_name", "description", "icon"])}
	apps = []
	for product in ctx["products"]:
		a = spec["apps"].get(product)
		if not a:
			continue
		lines = [l["text"] for l in a["lines"] if _for_me(l, product, ctx)]
		apps.append({"product": product, "title": a["title"], "icon": names[product].icon if product in names else None, "lines": lines})
	everyday = [{"title": e["title"], "body": e["body"]} for e in spec["everyday"] if _for_me(e, None, ctx)]
	more = replaces = None
	if ctx.get("owner"):
		from qtt_platform.api.explore import NOT_OFFERED  # the inbox comes with the services, not on its own

		r = spec["replaces"]
		rows = [{**{k: row[k] for k in ("product", "need", "instead")}, "app": names[row["product"]].display_name or row["product"], "have": row["product"] in ctx["products"]}
				for row in r["rows"] if row["product"] in names]
		replaces = {"title": r["title"], "body": r["body"], "footer": r["footer"], "rows": rows}
		have = set(frappe.get_all("QTT Tenant Product Subscription Pointer", filters={"tenant": tenant}, pluck="product"))
		others = [{"product": p.name, "title": p.display_name or p.name, "description": p.description, "icon": p.icon}
				  for p in names.values() if p.name not in have and p.name not in NOT_OFFERED and not any(w in p.name.upper() for w in HIDDEN_PRODUCT_WORDS)]
		if others:
			more = {**spec["more"], "apps": others}
	return {"intro": spec["intro"], "apps": apps, "everyday": everyday, "replaces": replaces, "more": more}
