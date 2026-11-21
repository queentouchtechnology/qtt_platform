"""
QTT Admin › AI: every AI action QTT OS does — by business, person, action and model — and the AI accounts QTT pays:
what each is used for, its balance, where its key is set and how to top it up. QTT Platform Owners only.

  overview(days)                       totals; by action (its model, counts on the plan), business, person and model;
                                       the accounts (DeepSeek's balance from the usage collector)
  save_action(code, model, counts)     an action's own model (empty: the QTT Assistant model) and whether it counts
  save_account(key, fields)            an account's top-up details (what it's for, where its key is, pages, steps, login)
  save_price(model, provider, input, output)   a model's price per 1M tokens (input, output) — costs are worked out from it

Records: QTT AI Usage Record (one per AI call — qtt_platform.ai_actions), QTT AI Action, QTT AI Provider, QTT AI Model.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from qtt_platform import ai_actions
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_platform_owner

USAGE = "QTT AI Usage Record"


def _rows(days: int) -> list[dict]:
	return frappe.db.sql(
		f"""SELECT COALESCE(action, feature) AS action, tenant, user, provider, model, status,
		           COUNT(*) AS calls, SUM(COALESCE(total_tokens, 0)) AS tokens, SUM(COALESCE(input_tokens, 0)) AS input,
		           SUM(COALESCE(output_tokens, 0)) AS output, SUM(COALESCE(provider_cost, 0)) AS cost,
		           SUM(COALESCE(credits_used, 0)) AS credits, AVG(COALESCE(duration_ms, 0)) AS ms
		    FROM `tab{USAGE}` WHERE creation >= %(since)s
		    GROUP BY action, tenant, user, provider, model, status""",
		{"since": add_days(now_datetime(), -days)},
		as_dict=True,
	)


def _add(bucket: dict, key, r) -> None:
	b = bucket.setdefault(key, {"calls": 0, "tokens": 0, "cost": 0.0, "errors": 0, "credits": 0.0})
	b["calls"] += r.calls
	b["tokens"] += int(r.tokens or 0)
	b["cost"] += float(r.cost or 0)
	b["credits"] += float(r.credits or 0)
	if r.status != "success":
		b["errors"] += r.calls


def _sorted(bucket: dict, extra) -> list[dict]:
	return sorted(({**extra(k), **v, "cost": round(v["cost"], 4)} for k, v in bucket.items()), key=lambda x: (-x["tokens"], -x["calls"]))


@frappe.whitelist(methods=["GET"])
def overview(days=30) -> dict:
	"""QTT Admin › AI: the last `days` days of AI — totals; by action (with the model it uses and whether it counts on the
	plan), by business, by person and by model; and the AI accounts with balance, use, key place and how to top up."""
	require_platform_owner()
	days = max(1, min(int(days or 30), 365))
	rows = _rows(days)
	total = {"calls": 0, "tokens": 0, "cost": 0.0, "errors": 0}
	by_action, by_tenant, by_user, by_model = {}, {}, {}, {}
	for r in rows:
		total["calls"] += r.calls
		total["tokens"] += int(r.tokens or 0)
		total["cost"] += float(r.cost or 0)
		if r.status != "success":
			total["errors"] += r.calls
		_add(by_action, r.action, r)
		_add(by_tenant, r.tenant, r)
		_add(by_user, (r.user, r.tenant), r)
		_add(by_model, (r.provider, r.model), r)
	total["cost"] = round(total["cost"], 4)

	assistant_model = frappe.db.get_single_value("QTT App Settings", "assistant_model") or "deepseek-chat"
	actions = {a.name: a for a in frappe.get_all("QTT AI Action", fields=["name", "label", "area", "product", "counts_for_plan", "model"],
												limit=0)} if frappe.db.table_exists("QTT AI Action") else {}
	names = {t.name: t.tenant_name for t in frappe.get_all("QTT Tenant", fields=["name", "tenant_name"], limit=0)}
	people = {u.name: u.full_name for u in frappe.get_all("User", filters={"name": ["in", [k[0] for k in by_user] or [""]]},
														 fields=["name", "full_name"])}
	prices = {m.model_id: m for m in frappe.get_all("QTT AI Model", fields=["model_id", "provider", "cost_input_per_1m", "cost_output_per_1m"],
													 limit=0)}

	action_rows = []
	for code, a in sorted(actions.items()):
		used = by_action.pop(code, {"calls": 0, "tokens": 0, "cost": 0.0, "errors": 0, "credits": 0.0})
		action_rows.append({"code": code, "label": a.label, "area": a.area, "counts_for_plan": bool(a.counts_for_plan),
							"model": a.model or "", "model_used": a.model or assistant_model, **used, "cost": round(used["cost"], 4)})
	for code, used in by_action.items():  # older records (before action codes) by their feature name
		action_rows.append({"code": code, "label": code, "area": "", "counts_for_plan": True, "model": "", "model_used": "", **used,
							"cost": round(used["cost"], 4), "old": True})
	action_rows.sort(key=lambda x: (-x["tokens"], -x["calls"], x["code"]))

	models = _sorted(by_model, lambda k: {"provider": k[0], "model": k[1],
										  "price_in": float((prices.get(k[1]) or {}).get("cost_input_per_1m") or 0),
										  "price_out": float((prices.get(k[1]) or {}).get("cost_output_per_1m") or 0)})
	for m in models:
		m["priced"] = bool(m["price_in"] or m["price_out"])

	return {
		"days": days,
		"total": total,
		"assistant_model": assistant_model,
		"actions": action_rows,
		"businesses": _sorted(by_tenant, lambda k: {"tenant": k, "name": names.get(k, k)}),
		"people": _sorted(by_user, lambda k: {"user": k[0], "name": people.get(k[0], k[0]), "business": names.get(k[1], k[1])})[:100],
		"models": models,
		"accounts": _accounts(),
	}


def _accounts() -> list[dict]:
	"""The AI accounts with their top-up details and, for DeepSeek, its balance (usage collector, every 30 minutes)."""
	balance = {}
	try:
		from qtt_platform.api.usage_dashboard import dashboard

		d = dashboard()
		ds = d.get("deepseek") or {}
		if ds.get("balance") is not None:
			balance["deepseek"] = {"balance": ds.get("balance"), "currency": ds.get("currency") or "USD", "low": bool(ds.get("low")),
								   "taken_at": d.get("taken_at")}
		oa = d.get("openai") or {}
		if oa:
			balance["openai"] = {"spent_30d": oa.get("spent_30d"), "currency": "USD"}
	except Exception:
		pass
	out = []
	keys = list(ai_actions.ACCOUNTS) + [k for k in frappe.get_all("QTT AI Provider", pluck="name") if k not in ai_actions.ACCOUNTS]
	for key in keys:
		row = frappe.db.get_value("QTT AI Provider", key, ["name", "enabled", *[f for f in ai_actions.ACCOUNT_FIELDS
																			 if frappe.get_meta("QTT AI Provider").has_field(f)],
														  *(["account_login"] if frappe.get_meta("QTT AI Provider").has_field("account_login") else [])],
								  as_dict=True) if frappe.db.exists("QTT AI Provider", key) else None
		info = {**ai_actions.ACCOUNTS.get(key, {}), **{k: v for k, v in (row or {}).items() if v}}
		info.pop("base_url", None)
		out.append({"key": key, "label": info.get("label") or key.title(), **{f: info.get(f) or "" for f in ai_actions.ACCOUNT_FIELDS},
					"account_login": info.get("account_login") or "", "balance": balance.get(key)})
	return out


@frappe.whitelist(methods=["POST"])
def save_action(code: str, model: str | None = None, counts_for_plan=1) -> dict:
	"""An AI action's own model (empty: the QTT Assistant model) and whether it counts as an AI action on the plan."""
	require_platform_owner()
	if not frappe.db.exists("QTT AI Action", code):
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("QTT AI Action", code)
	before = {"model": doc.model, "counts_for_plan": doc.counts_for_plan}
	doc.model = " ".join(str(model or "").split())[:80] or None
	doc.counts_for_plan = 1 if str(counts_for_plan) in ("1", "true", "True") else 0
	doc.save(ignore_permissions=True)
	write_audit_event("ai.action_changed", target_doctype="QTT AI Action", target_name=code, before_state=before,
					  after_state={"model": doc.model, "counts_for_plan": doc.counts_for_plan})
	return {"code": code, "model": doc.model or "", "counts_for_plan": bool(doc.counts_for_plan)}


@frappe.whitelist(methods=["POST"])
def save_account(key: str, fields) -> dict:
	"""An AI account's top-up details: label, used_for, key_where, account_login, dashboard_url, topup_url, topup_steps."""
	require_platform_owner()
	if isinstance(fields, str):
		fields = json.loads(fields or "{}")
	if not frappe.db.exists("QTT AI Provider", key):
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("QTT AI Provider", key)
	allowed = (*ai_actions.ACCOUNT_FIELDS, "account_login")
	for f, v in (fields or {}).items():
		if f not in allowed:
			frappe.throw(_("{0} can't be changed here.").format(f))
		v = str(v or "").strip()
		if f.endswith("_url") and v and not v.startswith("https://"):
			frappe.throw(_("Links start with https://"))
		doc.set(f, v[:2000] or None)
	doc.save(ignore_permissions=True)
	write_audit_event("ai.account_changed", target_doctype="QTT AI Provider", target_name=key, after_state={k: fields[k] for k in fields})
	return next(a for a in _accounts() if a["key"] == key)


@frappe.whitelist(methods=["POST"])
def save_price(model: str, provider: str, price_in=0, price_out=0) -> dict:
	"""A model's price per 1M tokens (input, output) — the cost of every AI call on it is worked out from this."""
	require_platform_owner()
	model = " ".join(str(model or "").split())[:80]
	if not model:
		frappe.throw(_("Which model?"))
	try:
		p_in, p_out = max(0.0, float(price_in or 0)), max(0.0, float(price_out or 0))
	except (TypeError, ValueError):
		frappe.throw(_("Prices are numbers."))
	name = frappe.db.get_value("QTT AI Model", {"model_id": model})
	if name:
		frappe.db.set_value("QTT AI Model", name, {"cost_input_per_1m": p_in, "cost_output_per_1m": p_out})
	else:
		frappe.get_doc({"doctype": "QTT AI Model", "model_id": model, "provider": provider if frappe.db.exists("QTT AI Provider", provider) else None,
						"cost_input_per_1m": p_in, "cost_output_per_1m": p_out}).insert(ignore_permissions=True, ignore_mandatory=True)
	write_audit_event("ai.price_changed", target_doctype="QTT AI Model", target_name=model, after_state={"in": p_in, "out": p_out})
	return {"model": model, "price_in": p_in, "price_out": p_out}
