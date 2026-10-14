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


@frappe.whitelist(methods=["GET"])
def guides() -> list[dict]:
	"""Every set-up guide this person can act on (HR's Office Pulse guide, …), arranged."""
	user, tenant, _ctx = _who()
	out = []
	for path in frappe.get_hooks("qtt_setup_steps") or []:
		try:
			g = frappe.get_attr(path)(user, tenant)
		except Exception:
			frappe.log_error(title=f"qtt setup steps: {path}")
			continue
		if g:
			out.append({**{k: g[k] for k in ("product", "screen", "title", "intro", "explainers") if k in g}, **setup_rules.arrange(g["steps"])})
	return out


@frappe.whitelist(methods=["GET"])
def welcome() -> dict:
	"""What QTT OS does for this person: their apps (lines for their role), the everyday helpers,
	and — for owners — the apps they could add."""
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
	more = None
	if ctx.get("owner"):
		have = set(frappe.get_all("QTT Tenant Product Subscription Pointer", filters={"tenant": tenant}, pluck="product"))
		others = [{"product": p.name, "title": p.display_name or p.name, "description": p.description, "icon": p.icon}
				  for p in names.values() if p.name not in have and not any(w in p.name.upper() for w in HIDDEN_PRODUCT_WORDS)]
		if others:
			more = {**spec["more"], "apps": others}
	return {"intro": spec["intro"], "apps": apps, "everyday": everyday, "more": more}
