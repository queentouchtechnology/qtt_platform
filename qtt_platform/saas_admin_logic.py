"""
QTT Admin → SaaS: plan input rules, trial extension and revenue maths.
Pure (no frappe) so it can be unit-tested without a bench; the saving and
querying live in api/saas_admin.py.
"""

from __future__ import annotations

import re


class SaasInputError(ValueError):
	"""Message is shown to the platform owner as-is."""


BILLING_PERIODS = ("monthly", "yearly")
_PLAN_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_]{1,29}$")
_FEATURE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.]{1,59}$")
MAX_TRIAL_EXTENSION_DAYS = 90


def _number(value, label: str, *, lo: float = 0, hi: float = 10_000_000, integer: bool = False):
	try:
		number = int(str(value).strip()) if integer else float(str(value).strip())
	except (TypeError, ValueError) as exc:
		raise SaasInputError(f"{label} must be a number.") from exc
	if not lo <= number <= hi:
		raise SaasInputError(f"{label} must be between {lo:g} and {hi:g}.")
	return number


def clean_features(features) -> list[dict]:
	"""[{feature_key, limit_value}] — keys unique, values kept as text
	(the entitlement engine stores them as strings: '10', '1', '0')."""
	rows, seen = [], set()
	for row in features:
		key = str((row or {}).get("feature_key") or "").strip().lower()
		if not key:
			continue
		if not _FEATURE_KEY.match(key):
			raise SaasInputError(f"Feature keys use lowercase letters, digits, dots or underscores: {key}")
		if key in seen:
			raise SaasInputError(f"Feature listed twice: {key}")
		seen.add(key)
		value = str((row or {}).get("limit_value") if (row or {}).get("limit_value") is not None else "").strip()
		if not value or len(value) > 40:
			raise SaasInputError(f"Give {key} a value (a number, or 1/0 for on/off).")
		rows.append({"feature_key": key, "limit_value": value})
	return rows


def monthly_value(price, period: str, items=()) -> float:
	"""Recurring value per month: plan price (yearly ÷ 12) plus add-ons."""
	base = float(price or 0)
	if period == "yearly":
		base /= 12
	addons = sum(float(i.get("unit_price") or 0) * int(i.get("quantity") or 0) for i in items or ())
	return round(base + addons, 2)


def counts_as_revenue(sub: dict) -> bool:
	"""Revenue is only what a business is really billed for: not one of QTT's own (house) workspaces, and billed
	(razorpay or invoice). Free use, house workspaces and subscriptions never billed are not revenue (22 Nov 2026:
	₹39,985 'monthly revenue' was 15 house / never-billed app subscriptions at old list prices; ₹0 had been paid)."""
	return not sub.get("is_house") and (sub.get("billing_mode") or "") in ("razorpay", "invoice")


def revenue_summary(subscriptions: list[dict]) -> dict:
	"""subscriptions: current rows {product, status, base_price,
	billing_period, items}. MRR counts paying ones (active, past_due);
	trials are shown separately as potential revenue."""
	mrr = 0.0
	at_risk = 0.0
	trial_value = 0.0
	by_product: dict[str, float] = {}
	counts = {"active": 0, "trialing": 0, "past_due": 0}
	for s in subscriptions:
		value = monthly_value(s.get("base_price"), s.get("billing_period") or "monthly", s.get("items") or ())
		status = s.get("status")
		if status in counts:
			counts[status] += 1
		if status in ("active", "past_due"):
			mrr += value
			by_product[s.get("product") or ""] = round(by_product.get(s.get("product") or "", 0) + value, 2)
			if status == "past_due":
				at_risk += value
		elif status == "trialing":
			trial_value += value
	return {
		"mrr": round(mrr, 2),
		"arr": round(mrr * 12, 2),
		"at_risk_mrr": round(at_risk, 2),
		"trial_mrr": round(trial_value, 2),
		"mrr_by_product": by_product,
		"counts": counts,
	}


# --------------------------------------------------------------------------
# QTT Admin home: one ranked "needs attention" list
# --------------------------------------------------------------------------
_LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}
_KIND_ORDER = {"server": 0, "client_site": 1, "domain": 2, "setup": 3, "payment": 4, "client_request": 5, "trial": 6, "approval": 7, "automation": 8, "whatsapp": 8, "website_cache": 8, "domain_wait": 5, "build": 1, "snapshot": 9}


def attention_items(*, servers=(), trials=(), past_due=(), approvals=(), setup_errors=(), domains=(), snapshots=(), client_sites=(),
					 client_requests=(), automation=(), whatsapp=(), website_cache=(), domain_wait=(), builds=(),
					 studio=(), marketing=(), today_str: str) -> list[dict]:
	"""Everything a QTT admin should look at, most urgent first. Each item:
	{level, kind, title, area, target} plus facts the app turns into a
	translated sentence (product, days, count, status) and, where the server
	wrote one, a raw `detail`. `area` is the admin page the app opens,
	`target` the record in it."""
	items = []
	for s in servers:
		level = "critical" if s["status"] in ("critical", "offline") else "warning"
		items.append({"level": level, "kind": "server", "title": s["title"], "status": s["status"],
					  "detail": s.get("problems") or None, "area": "servers", "target": s["key"]})
	for d in domains:
		# {domain, level (warning|critical), days_left}: days < 0 = already expired.
		items.append({"level": d["level"], "kind": "domain", "title": d["domain"], "days": d.get("days_left"),
					  "area": "servers", "target": None})  # the Servers page lists domains
	for s in snapshots:
		# {key, title, days (since the last snapshot; None = never)}
		items.append({"level": "info", "kind": "snapshot", "title": s["title"], "days": s.get("days"),
					  "area": "servers", "target": s["key"]})
	for c in client_sites:
		# Managed Services: a client's website / server that is down. {label, tenant, tenant_name, problem}
		items.append({"level": "critical", "kind": "client_site", "title": c["label"], "detail": c.get("problem") or None,
					  "client": c.get("tenant_name"), "area": "clients", "target": c["tenant"]})
	for r in client_requests:
		# Managed Services: a client request nobody has answered yet. {subject, tenant, tenant_name, urgent}
		items.append({"level": "warning" if r.get("urgent") else "info", "kind": "client_request", "title": r["subject"],
					  "client": r.get("tenant_name"), "area": "clients", "target": r["tenant"]})
	for a in automation:
		# Usage collector: {what: deepseek_low | n8n_errors, value}
		items.append({"level": "warning", "kind": "automation", "title": "DeepSeek" if a["what"] == "deepseek_low" else "n8n",
					  "what": a["what"], "count": a["value"], "area": "usage", "target": None})
	for w in domain_wait:
		# An approved website still waiting for its domain after 3+ days: {label, tenant, tenant_name, domain, days, status}
		items.append({"level": "warning", "kind": "domain_wait", "title": w["label"], "client": w.get("tenant_name"), "days": w.get("days"),
					  "detail": w.get("domain"), "status": w.get("status"), "area": "clients", "target": w["tenant"]})
	for b in builds:
		# Frappe's build queue (qtt_services builds_admin.attention): {what (build_failed | domain_approval |
		# domain_payment_missing), label, client, tenant, kind?, deployment?, service?}
		items.append({"level": "critical" if b["what"] == "build_failed" else "warning", "kind": "build", "what": b["what"],
					  "title": b.get("label") or "", "client": b.get("client"), "status": b.get("kind"),
					  "area": "builds", "target": b.get("deployment") or b.get("service")})
	if studio:
		# QTT Studio's nightly check (studio_admin.attention): templates that didn't draw right — one item for all of them
		items.append({"level": "warning", "kind": "studio_templates", "count": len(studio), "title": studio[0]["title"],
					  "detail": studio[0].get("note") or None, "area": "studio", "target": None})
	for m in marketing:
		# Marketing assistant (qtt_services marketing_admin.attention): {level, what (renderer_down | cutout_down |
		# occasion_dates | series_failing), count, title, detail}
		items.append({"level": m["level"], "kind": "marketing", "what": m["what"], "count": m.get("count") or 1, "title": m.get("title") or "",
					  "detail": m.get("detail") or None, "area": "marketing_assistant", "target": m["what"]})
	for c in website_cache:
		# A live website whose CloudPanel cache staff haven't switched on yet: {label, tenant, tenant_name, task}
		items.append({"level": "info", "kind": "website_cache", "title": c["label"], "client": c.get("tenant_name"),
					  "detail": c.get("task"), "area": "clients", "target": c["tenant"]})
	for w in whatsapp:
		# QTT's WhatsApp number (qtt_services wa_rules.attention): {level, what (wa_quality | wa_template_rejected |
		# wa_template_paused | wa_template_disabled | wa_template_approved | wa_template_category), name, value}
		items.append({"level": w["level"], "kind": "whatsapp", "title": w.get("name") or "", "what": w["what"],
					  "detail": w.get("value"), "area": "whatsapp_number" if w["what"] == "wa_quality" else "whatsapp_templates",
					  "target": None})
	for p in past_due:
		items.append({"level": "critical", "kind": "payment", "title": p.get("tenant_name") or p["tenant"],
					  "product": p["product"], "area": "customers", "target": p["tenant"]})
	for t in trials:
		days = _days_between(today_str, t.get("trial_end"))
		level = "warning" if days is not None and days <= 2 else "info"
		items.append({"level": level, "kind": "trial", "title": t.get("tenant_name") or t["tenant"],
					  "product": t["product"], "days": days, "area": "customers", "target": t["tenant"]})
	for e in setup_errors:
		items.append({"level": "critical", "kind": "setup", "title": e.get("tenant_name") or e["tenant"],
					  "product": e["product"], "detail": (e.get("error") or "")[:160] or None,
					  "area": "customers", "target": e["tenant"]})
	if approvals:
		items.append({"level": "warning", "kind": "approval", "title": approvals[0].get("title") or "",
					  "count": len(approvals), "area": "marketing", "target": None})
	return sorted(items, key=lambda i: (_LEVEL_ORDER.get(i["level"], 9), _KIND_ORDER.get(i["kind"], 9),
										 i["days"] if i.get("days") is not None else 99, (i["title"] or "").lower()))


def _days_between(today_str: str, date_str) -> int | None:
	from datetime import date

	try:
		return (date.fromisoformat(str(date_str)[:10]) - date.fromisoformat(today_str[:10])).days
	except (TypeError, ValueError):
		return None
