"""
Free use (PROJ-0024): all 8 apps without a plan until one simple amount per app; then one plan for everything — with fair
use each month and top-ups (owner, 15 Nov 2026). Rules in qtt_platform.free_use; every amount and price in Desk ›
QTT App Settings › Free use and the one plan / The plan's fair use / Top-ups.

  status()                     for the app: the free amounts (used / limit / left, at a time or in total), the gate, the
                               plan's prices — and, for a business on the plan or waiting to pay, `on_plan` / `awaiting`
  usage(tenant)                the free amounts' counts (hook `qtt_free_use`: (tenant) -> {key: n}, plus Studio's designs)
  plan_usage(tenant, since)    the plan's counts this month (hook `qtt_plan_use`: (tenant, since) -> {key: n}, plus AI)
  check(tenant, key, adding)   the gate for code that makes something new: past a free amount → FreeLimitReached
                               (free_limit:<key>, the one-plan sheet); on the plan past a fair-use amount → (plan_limit:<key>,
                               the top-up sheet)
  check_plan(tenant, key, n)   the plan's fair-use gate alone (offer messages, AI actions, stores…)
  subscribe(period)            the owner subscribes: an invoice and its payment link
  topup(pack)                  the owner buys a top-up pack: an invoice; paid → added for the rest of the plan month
  switch_period(period)        monthly ↔ yearly from the next renewal
  stop_plan(stop)              stop at the end of what's paid (or keep it going again)
  home_cards                   Needs you: a fair-use amount nearly or fully used (80%) → Top up

One app failing to count never stops anyone: its count is just 0.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from qtt_platform import free_use as rules
from qtt_platform.house import ONE_PLAN_PRODUCT, is_house  # the one plan for all 8 apps (qtt_platform.one_plan)
from qtt_platform.tenant.context import resolve_active_tenant

_OPEN = ("trialing", "active", "past_due")
SUB = "QTT Product Subscription"
TOPUP = "QTT Plan Top Up"
#: A free app's key → the plan's fair-use item it counts against (others are unlimited on the plan)
_PLAN_KEY = {"hr": "hr", "website": "website", "social": "social", "articles": "articles", "newsletters": "newsletters"}


class FreeLimitReached(frappe.ValidationError):
	"""Past a free amount (or the plan's fair use): the app shows the one plan / a top-up instead of an error (HTTP 402)."""

	http_status_code = 402


def _settings() -> dict:
	try:
		return frappe.get_cached_doc("QTT App Settings").as_dict()
	except Exception:
		return {}


def is_subscribed(tenant: str) -> bool:
	if is_house(tenant):
		return True
	return bool(frappe.db.exists(SUB, {"tenant": tenant, "product": ONE_PLAN_PRODUCT, "status": ["in", list(_OPEN)]}))


def _studio(tenant: str) -> dict:
	return {"studio": frappe.db.count("QTT Design", {"tenant": tenant})}


def usage(tenant: str) -> dict:
	used = {}
	for source in [_studio] + [frappe.get_attr(path) for path in frappe.get_hooks("qtt_free_use") or []]:
		try:
			for key, n in (source(tenant) or {}).items():
				if key in rules.KEYS:
					used[key] = used.get(key, 0) + int(n or 0)
		except Exception:
			frappe.log_error(title=f"qtt free use: {getattr(source, '__module__', source)}", message=frappe.get_traceback())
	return used


def _ai_used(tenant: str, since) -> dict:
	"""AI actions this plan month — everything the business asks AI for (succeeded); the AI that answers its customers or
	writes its daily report doesn't count (unlimited)."""
	if not frappe.db.table_exists("QTT AI Usage Record"):
		return {}
	# Every AI call is recorded under its action code (qtt_platform.ai_actions); the ones QTT marks as not counting
	# (QTT AI Action › Counts as an AI action on the plan — replies to customers, daily reports) are left out.
	free = frappe.get_all("QTT AI Action", filters={"counts_for_plan": 0}, pluck="name") if frappe.db.table_exists("QTT AI Action") else []
	n = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabQTT AI Usage Record`
		   WHERE tenant = %(t)s AND creation >= %(s)s AND status = 'success' AND feature NOT LIKE 'receptionist%%'
		     AND (action IS NULL OR action NOT IN %(free)s)""",
		{"t": tenant, "s": since, "free": tuple(free) or ("",)},
	)[0][0]
	return {"ai": n}


def plan_usage(tenant: str, since) -> dict:
	used = {}
	for source in [_ai_used] + [frappe.get_attr(path) for path in frappe.get_hooks("qtt_plan_use") or []]:
		try:
			for key, n in (source(tenant, since) or {}).items():
				if key in rules.PLAN_KEYS:
					used[key] = used.get(key, 0) + int(n or 0)
		except Exception:
			frappe.log_error(title=f"qtt plan use: {getattr(source, '__module__', source)}", message=frappe.get_traceback())
	return used


def _state(tenant: str) -> dict:
	s = _settings()
	return {"settings": s, "enabled": bool(s.get("free_use_enabled", 1)), "subscribed": is_subscribed(tenant),
			"limits": rules.limits_from(s)}


# ---------------------------------------------------------------- the plan


def _plan_sub(tenant: str):
	"""The business's one-plan subscription (paid, waiting for its first payment, or suspended), else None."""
	rows = frappe.get_all(SUB, filters={"tenant": tenant, "product": ONE_PLAN_PRODUCT, "status": ["!=", "cancelled"]},
						  fields=["name", "plan", "status", "creation", "current_period_start", "paid_until", "cancel_at_period_end",
								  "scheduled_plan"], order_by="creation desc", limit=1)
	return rows[0] if rows else None


def _period_of(plan: str | None) -> str:
	return "yearly" if plan and frappe.db.get_value("QTT Plan", plan, "billing_period") == "yearly" else "monthly"


def _month(sub) -> tuple:
	"""This plan month (from the plan's first day)."""
	start = getdate(sub.current_period_start or sub.creation)
	first = frappe.db.get_value(SUB, sub.name, "trial_start") or start
	return rules.month_window(getdate(first), getdate(today()))


def _topups(tenant: str, start) -> dict:
	out = {}
	for t in frappe.get_all(TOPUP, filters={"tenant": tenant, "status": "active", "period_start": start}, fields=["adds", "amount"]) \
			if frappe.db.table_exists(TOPUP) else []:
		out[t.adds] = out.get(t.adds, 0) + int(t.amount or 0)
	return out


def _plan_now(tenant: str) -> dict | None:
	"""The plan's use this month for a business on the plan (None: not on it, or QTT's own — never limited)."""
	if is_house(tenant) or not is_subscribed(tenant):
		return None
	sub = _plan_sub(tenant)
	if not sub:
		return None
	start, end = _month(sub)
	limits = rules.plan_limits_from(_settings())
	tops = _topups(tenant, start)
	return {"sub": sub, "start": start, "end": end, "limits": limits, "topups": tops,
			"status": rules.plan_status(plan_usage(tenant, start), limits, tops)}


def check_plan(tenant: str, key: str, adding: int = 1) -> None:
	"""On the plan: past this month's fair-use amount (with top-ups) → FreeLimitReached plan_limit:<key> (the app shows
	the top-up sheet). Off the plan, QTT's own, or unlimited: nothing."""
	if key not in rules.PLAN_KEYS or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
		return
	now = _plan_now(tenant)
	if not now:
		return
	used = next((i["used"] for i in now["status"]["items"] if i["key"] == key), 0)
	if rules.plan_blocked(key, used, now["limits"], now["topups"], adding=adding):
		label = next((name for k, name, _u, _p in rules.PLAN_ITEMS if k == key), key)
		frappe.throw(_("You've used this month's {0} on your plan. Top up to keep going — it's added straight away.").format(label),
					 FreeLimitReached, title=f"plan_limit:{key}")


def check(tenant: str, key: str, adding: int = 1) -> None:
	"""Call before making something new in an app (a person, a bill, a website, a post…). Past the free amount: raises
	FreeLimitReached, which the app turns into the one-plan sheet; on the plan, its fair use (the top-up sheet)."""
	st = _state(tenant)
	if st["subscribed"]:
		if key in _PLAN_KEY:
			check_plan(tenant, _PLAN_KEY[key], adding)
		return
	if not rules.limited(st["enabled"], st["subscribed"]):
		return
	used = usage(tenant).get(key, 0)
	if rules.blocked(key, used, st["limits"], enabled=st["enabled"], subscribed=st["subscribed"], adding=adding):
		label = next((name for k, name, _u in rules.APPS if k == key), key)
		frappe.throw(_("You've used the free {0}. Subscribe to keep going — one plan for all 8 apps.").format(label),
					 FreeLimitReached, title=f"free_limit:{key}")


def _invoices(tenant: str, sub_name: str | None) -> list[dict]:
	"""The plan's and its top-ups' invoices, newest first (open ones with their payment link)."""
	from qtt_platform.billing import paylink

	names = set()
	if sub_name:
		names |= set(frappe.get_all("QTT Invoice Item", filters={"subscription": sub_name, "parenttype": "QTT Invoice"}, pluck="parent"))
	if frappe.db.table_exists(TOPUP):
		names |= {i for i in frappe.get_all(TOPUP, filters={"tenant": tenant, "invoice": ["is", "set"]}, pluck="invoice") if i}
	rows = frappe.get_all("QTT Invoice", filters={"name": ["in", list(names) or [""]], "tenant": tenant, "status": ["!=", "draft"]},
						  fields=["name", "amount", "status", "creation", "due_date"], order_by="creation desc", limit=8)
	return [{"invoice": r.name, "amount": float(r.amount or 0), "status": r.status, "date": str(getdate(r.creation)),
			 "pay_url": paylink.payment_url(r.name) if r.status == "open" else None} for r in rows]


@frappe.whitelist(methods=["GET"])
def status() -> dict:
	"""What the app shows about free use and the plan for the signed-in person's business.

	Returns {limited, gate, reached, apps: [{key, label, unit, period (at_a_time | in_total), used, limit, left, reached}],
	plan: {monthly, yearly}, subscribed, packs: {pack: {name, adds, amount, price}}, plan_amounts: {item: amount (0 = unlimited)},
	on_plan: {period, renews_on, stopping, switching_to, month: {start, end}, items: [{key, label, unit, period (month |
	at_a_time), used, limit, topup, left, near, reached}], invoices: [...]} | null,
	awaiting: {invoice, amount, pay_url, period} | null}. `limit`/`left` are null when unlimited."""
	empty = {"limited": False, "gate": False, "reached": [], "apps": [], "plan": rules.plan_prices({}), "subscribed": False,
			 "packs": {}, "on_plan": None, "awaiting": None}
	tenant = resolve_active_tenant(frappe.session.user)
	if not tenant:
		return empty
	st = _state(tenant)
	out = rules.status(usage(tenant), st["limits"], enabled=st["enabled"], subscribed=st["subscribed"])
	result = {**out, "plan": rules.plan_prices(st["settings"]), "subscribed": st["subscribed"],
			  "packs": rules.topups_from(st["settings"]), "plan_amounts": rules.plan_limits_from(st["settings"]),
			  "on_plan": None, "awaiting": None}
	if is_house(tenant):
		return result
	sub = _plan_sub(tenant)
	now = _plan_now(tenant)
	if now:
		s = now["sub"]
		result["on_plan"] = {"period": _period_of(s.plan), "renews_on": str(s.paid_until) if s.paid_until else None,
							 "stopping": bool(s.cancel_at_period_end),
							 "switching_to": _period_of(s.scheduled_plan) if s.scheduled_plan else None,
							 "month": {"start": str(now["start"]), "end": str(now["end"])},
							 "items": now["status"]["items"], "invoices": _invoices(tenant, s.name)}
	elif sub and sub.status == "suspended":
		from qtt_platform import invoice_billing
		from qtt_platform.billing import paylink

		inv = invoice_billing.open_invoice(sub.name)
		if inv:
			result["awaiting"] = {"invoice": inv, "amount": float(frappe.db.get_value("QTT Invoice", inv, "amount") or 0),
								  "pay_url": paylink.payment_url(inv), "period": _period_of(sub.plan),
								  "renewal": bool(sub.paid_until)}  # renewal: paid before, this one is overdue
	return result


def guard_new_design(doc, method=None) -> None:
	"""doc_events QTT Design before_insert — past the free designs, a new one asks to subscribe (designs are unlimited
	on the plan)."""
	if doc.get("tenant") and not (frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch):
		check(doc.tenant, "studio")


def _owner_tenant() -> str:
	from qtt_platform.tenant.guards import require_tenant_role

	tenant = resolve_active_tenant(frappe.session.user)
	if not tenant:
		frappe.throw(_("Choose a business first."))
	require_tenant_role(tenant, ["Tenant Owner"])
	return tenant


@frappe.whitelist(methods=["POST"])
def subscribe(period: str = "monthly") -> dict:
	"""The owner subscribes to the one plan for all 8 apps (`period`: monthly | yearly). It starts once the first
	invoice is paid. Asking again while unpaid gives the same invoice (or replaces it when the period changed).
	Returns {status: awaiting_payment | active, invoice, pay_url}."""
	from qtt_platform import invoice_billing, one_plan
	from qtt_platform import invoice_billing_rules as billing_rules
	from qtt_platform.audit import write_audit_event
	from qtt_platform.billing import paylink
	from qtt_platform.subscription import service as subscription_service

	tenant = _owner_tenant()
	if is_subscribed(tenant):
		return {"status": "active", "invoice": None, "pay_url": None}
	one_plan.sync_prices()
	plan = one_plan.plan_name("yearly" if period == "yearly" else "monthly")
	if not plan:
		frappe.throw(_("The plan isn't ready yet. Please try again in a minute."))
	current = subscription_service.get_current_subscription(tenant, ONE_PLAN_PRODUCT)
	if current and current.status == "suspended" and current.plan == plan:
		invoice = invoice_billing.open_invoice(current.name)
		if invoice:
			return {"status": "awaiting_payment", "invoice": invoice, "pay_url": paylink.payment_url(invoice)}
	if current and current.status in ("suspended",) and current.plan != plan:
		old = invoice_billing.open_invoice(current.name)
		if old:
			frappe.db.set_value("QTT Invoice", old, "status", "void")  # replaced by the new period's invoice
		current.db_set("status", "cancelled")  # switching monthly ↔ yearly before paying: the new one replaces it
	sub = subscription_service.create_subscription(tenant, ONE_PLAN_PRODUCT, plan)
	start = getdate(today())
	# Off until the first invoice is paid — paying turns it on (invoice_billing.on_invoice_update).
	sub.db_set({"status": "suspended", "billing_mode": "invoice", "trial_start": None, "trial_end": None, "paid_until": None,
				"current_period_start": start, "current_period_end": start})
	invoice = invoice_billing.invoice_period(sub.name, start)
	write_audit_event("one_plan_subscribe", tenant=tenant, product=ONE_PLAN_PRODUCT, target_doctype=SUB,
					  target_name=sub.name, metadata={"plan": plan, "invoice": invoice})
	months = billing_rules.months_for("yearly" if period == "yearly" else "monthly")
	return {"status": "awaiting_payment" if invoice else "active", "invoice": invoice,
			"pay_url": paylink.payment_url(invoice) if invoice else None, "months": months}


@frappe.whitelist(methods=["POST"])
def topup(pack: str) -> dict:
	"""The owner buys a top-up pack (messages | ai | staff | site) on the plan: an invoice; once paid it's added to that
	fair-use amount for the rest of this plan month. Returns {invoice, pay_url, adds, amount, until}."""
	from qtt_platform.audit import write_audit_event
	from qtt_platform.billing import paylink
	from qtt_platform.billing import service as billing_service

	tenant = _owner_tenant()
	now = _plan_now(tenant)
	if not now:
		frappe.throw(_("Top-ups come with the plan. Subscribe first — one plan for all 8 apps."))
	packs = rules.topups_from(_settings())
	if pack not in packs:
		frappe.throw(_("That pack isn't available."))
	p = packs[pack]
	start, end = now["start"], now["end"]
	waiting = frappe.db.get_value(TOPUP, {"tenant": tenant, "pack": pack, "status": "awaiting_payment", "period_start": start}, "invoice")
	if waiting and frappe.db.get_value("QTT Invoice", waiting, "status") == "open":
		return {"invoice": waiting, "pay_url": paylink.payment_url(waiting), "adds": p["adds"], "amount": p["amount"], "until": str(end)}
	inv = billing_service.create_invoice(tenant, [{"description": f"QTT OS top-up — {p['name']}, {start:%d %b} to {end:%d %b %Y}",
												   "amount": float(p["price"])}], due_in_days=3)
	if not inv.get("currency"):
		frappe.db.set_value("QTT Invoice", inv.name, "currency", "INR", update_modified=False)
	billing_service.issue_invoice(inv.name)
	frappe.get_doc({"doctype": TOPUP, "tenant": tenant, "pack": pack, "pack_name": p["name"], "adds": p["adds"],
					"amount": p["amount"], "price": p["price"], "status": "awaiting_payment", "period_start": start,
					"period_end": end, "invoice": inv.name}).insert(ignore_permissions=True)
	write_audit_event("one_plan_topup", tenant=tenant, product=ONE_PLAN_PRODUCT, target_doctype="QTT Invoice", target_name=inv.name,
					  metadata={"pack": pack, "price": p["price"]})
	return {"invoice": inv.name, "pay_url": paylink.payment_url(inv.name), "adds": p["adds"], "amount": p["amount"], "until": str(end)}


@frappe.whitelist(methods=["POST"])
def switch_period(period: str) -> dict:
	"""Monthly ↔ yearly from the next renewal (the next invoice is for the new period). The same period again: the
	switch is taken back. Returns {switching_to | null, from}."""
	from qtt_platform import one_plan

	tenant = _owner_tenant()
	sub = _plan_sub(tenant)
	if not sub or not is_subscribed(tenant) or not sub.paid_until:
		frappe.throw(_("Subscribe first — then you can switch."))
	target = one_plan.plan_name("yearly" if period == "yearly" else "monthly")
	if target == sub.plan:
		frappe.db.set_value(SUB, sub.name, {"scheduled_plan": None, "scheduled_plan_effective_date": None})
		return {"switching_to": None, "from": str(sub.paid_until)}
	frappe.db.set_value(SUB, sub.name, {"scheduled_plan": target, "scheduled_plan_effective_date": sub.paid_until})
	return {"switching_to": "yearly" if period == "yearly" else "monthly", "from": str(sub.paid_until)}


@frappe.whitelist(methods=["POST"])
def stop_plan(stop=1) -> dict:
	"""stop=1: the plan stops at the end of what's paid (no more invoices; everything keeps working until then, then the
	free amounts again — nothing deleted). stop=0: keep it going. Returns {stopping, until}."""
	from qtt_platform.audit import write_audit_event

	tenant = _owner_tenant()
	sub = _plan_sub(tenant)
	if not sub or not is_subscribed(tenant):
		frappe.throw(_("There's no plan to stop."))
	stopping = str(stop).lower() in ("1", "true", "yes")
	frappe.db.set_value(SUB, sub.name, "cancel_at_period_end", 1 if stopping else 0)
	write_audit_event("one_plan_stop" if stopping else "one_plan_keep", tenant=tenant, product=ONE_PLAN_PRODUCT,
					  target_doctype=SUB, target_name=sub.name)
	return {"stopping": stopping, "until": str(sub.paid_until) if sub.paid_until else None}


def on_invoice_paid(doc, method=None) -> None:
	"""doc_events QTT Invoice on_update: a paid top-up starts at once; any paid plan or top-up invoice refreshes the
	business's app (the plan switches on with no reopening)."""
	if doc.status != "paid" or not doc.has_value_changed("status"):
		return
	touched = False
	if frappe.db.table_exists(TOPUP):
		for name in frappe.get_all(TOPUP, filters={"invoice": doc.name, "status": "awaiting_payment"}, pluck="name"):
			frappe.db.set_value(TOPUP, name, "status", "active")
			touched = True
	subs = {i.subscription for i in doc.items if i.get("subscription")}
	if subs and frappe.db.exists(SUB, {"name": ["in", list(subs)], "product": ONE_PLAN_PRODUCT}):
		touched = True
	if touched:
		from qtt_platform.realtime import notify_users, tenant_users

		notify_users(tenant_users(doc.tenant), tenant=doc.tenant, reason="plan_changed")


def home_cards(user: str, tenant: str) -> list[dict]:
	"""Needs you (hook `qtt_home_cards`): for the owner on the plan, a fair-use amount nearly (80%) or fully used → Top up."""
	now = _plan_now(tenant)
	if not now or frappe.db.get_value("QTT Tenant", tenant, "owner_user") != user:
		return []
	out = []
	for i in now["status"]["items"]:
		if not (i["near"] or i["reached"]) or i["period"] != "month":
			continue
		out.append({"key": f"plan_use:{i['key']}:{now['start']}", "tone": "danger" if i["reached"] else "warning", "icon": "info",
					"title": "This month's {what} are used up" if i["reached"] else "{used} of {limit} {what} used this month",
					"body": "Top up to keep going — it's added straight away.", "args": {"what": i["label"].lower(), "used": i["used"],
					"limit": i["limit"]}, "action": {"label": "Top up", "kind": "screen", "target": "business.one_plan"}})
	return out


@frappe.whitelist(methods=["GET"])
def admin_plans() -> dict:
	"""QTT Admin › Revenue › One plan (QTT staff only): every business on the plan or waiting to pay — its period, status,
	renewal, this plan month's top-ups and what it cost QTT (AI provider spend) and its offer messages sent.
	Returns {summary: {on_plan, awaiting, stopping, topups_month}, rows: [{tenant, name, period, status, renews_on,
	stopping, topups, topups_amount, ai_cost, offer_messages}]}."""
	from qtt_platform.tenant.guards import require_platform_owner

	require_platform_owner()
	subs = frappe.get_all(SUB, filters={"product": ONE_PLAN_PRODUCT, "status": ["!=", "cancelled"]},
						  fields=["name", "tenant", "plan", "status", "creation", "current_period_start", "paid_until", "cancel_at_period_end"],
						  order_by="creation desc")
	rows, seen = [], set()
	month_topups = 0.0
	for s in subs:
		if s.tenant in seen or is_house(s.tenant):
			continue
		seen.add(s.tenant)
		start, _end = _month(s)
		tops = frappe.get_all(TOPUP, filters={"tenant": s.tenant, "status": "active", "period_start": start}, fields=["price"]) \
			if frappe.db.table_exists(TOPUP) else []
		amount = sum(float(t.price or 0) for t in tops)
		month_topups += amount
		ai_cost = frappe.db.sql("""SELECT COALESCE(SUM(provider_cost), 0) FROM `tabQTT AI Usage Record` WHERE tenant=%s AND creation >= %s""",
								(s.tenant, start))[0][0] if frappe.db.table_exists("QTT AI Usage Record") else 0
		used = plan_usage(s.tenant, start)
		paid = s.status in _OPEN
		rows.append({"tenant": s.tenant, "name": frappe.db.get_value("QTT Tenant", s.tenant, "tenant_name") or s.tenant,
					 "period": _period_of(s.plan), "status": "on_plan" if paid else ("overdue" if s.paid_until else "awaiting"),
					 "renews_on": str(s.paid_until) if s.paid_until else None, "stopping": bool(s.cancel_at_period_end),
					 "topups": len(tops), "topups_amount": amount, "ai_cost": round(float(ai_cost or 0), 2),
					 "offer_messages": int(used.get("offer_messages") or 0)})
	return {"summary": {"on_plan": sum(1 for r in rows if r["status"] == "on_plan"), "awaiting": sum(1 for r in rows if r["status"] != "on_plan"),
						"stopping": sum(1 for r in rows if r["stopping"]), "topups_month": month_topups},
			"rows": rows}
