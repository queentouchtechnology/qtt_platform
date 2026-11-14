"""
Free use (PROJ-0024): all 8 apps without a plan until one simple limit per app; then one plan for everything.
Rules in qtt_platform.free_use; limits and the plan's prices in Desk › QTT App Settings › Free use and the one plan.

  status()                     for the app: each app's used / limit / left, whether the gate is up, the plan's prices
  usage(tenant)                how much of each app the business has used (hook `qtt_free_use`: (tenant) -> {key: n},
                               plus Studio's designs from here)
  check(tenant, key, adding)   the gate for code that makes something new: raises FreeLimitReached past the limit
  is_subscribed(tenant)        on the one plan (or QTT's own workspace) — never limited
  subscribe(period)            the owner subscribes to the one plan: an invoice and its payment link

One app failing to count never stops anyone: its count is just 0.
"""

import frappe
from frappe import _

from qtt_platform import free_use as rules
from qtt_platform.house import is_house
from qtt_platform.tenant.context import resolve_active_tenant

from qtt_platform.house import ONE_PLAN_PRODUCT  # the one plan for all 8 apps (qtt_platform.one_plan)
_OPEN = ("trialing", "active", "past_due")


class FreeLimitReached(frappe.ValidationError):
	"""Past an app's free limit: the app shows the one plan instead of an error (HTTP 402)."""

	http_status_code = 402


def _settings() -> dict:
	try:
		return frappe.get_cached_doc("QTT App Settings").as_dict()
	except Exception:
		return {}


def is_subscribed(tenant: str) -> bool:
	if is_house(tenant):
		return True
	return bool(frappe.db.exists("QTT Product Subscription", {"tenant": tenant, "product": ONE_PLAN_PRODUCT, "status": ["in", list(_OPEN)]}))


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


def _state(tenant: str) -> dict:
	s = _settings()
	return {"settings": s, "enabled": bool(s.get("free_use_enabled", 1)), "subscribed": is_subscribed(tenant),
			"limits": rules.limits_from(s)}


def check(tenant: str, key: str, adding: int = 1) -> None:
	"""Call before making something new in an app (a person, a bill, a website, a post…). Past the free limit: raises
	FreeLimitReached, which the app turns into the one-plan sheet."""
	st = _state(tenant)
	if not rules.limited(st["enabled"], st["subscribed"]):
		return
	used = usage(tenant).get(key, 0)
	if rules.blocked(key, used, st["limits"], enabled=st["enabled"], subscribed=st["subscribed"], adding=adding):
		label = next((name for k, name, _u in rules.APPS if k == key), key)
		frappe.throw(_("You've used the free {0}. Subscribe to keep going — one plan for all 8 apps.").format(label),
					 FreeLimitReached, title=f"free_limit:{key}")


@frappe.whitelist(methods=["GET"])
def status() -> dict:
	"""What the app shows about free use for the signed-in person's business.

	Returns {limited, gate, reached: [app keys], apps: [{key, label, unit, used, limit, left, reached}],
	plan: {monthly, yearly}, subscribed}. `limit`/`left` are null when that app has no limit (or the business is on
	the plan, or free use is switched off in Desk)."""
	tenant = resolve_active_tenant(frappe.session.user)
	if not tenant:
		return {"limited": False, "gate": False, "reached": [], "apps": [], "plan": rules.plan_prices({}), "subscribed": False}
	st = _state(tenant)
	out = rules.status(usage(tenant), st["limits"], enabled=st["enabled"], subscribed=st["subscribed"])
	return {**out, "plan": rules.plan_prices(st["settings"]), "subscribed": st["subscribed"]}


def guard_new_design(doc, method=None) -> None:
	"""doc_events QTT Design before_insert — past the free designs, a new one asks to subscribe."""
	if doc.get("tenant") and not (frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch):
		check(doc.tenant, "studio")


@frappe.whitelist(methods=["POST"])
def subscribe(period: str = "monthly") -> dict:
	"""The owner subscribes to the one plan for all 8 apps (`period`: monthly | yearly). It starts once the first
	invoice is paid — paying lifts every free limit. Asking again while unpaid gives the same invoice.
	Returns {status: awaiting_payment | active, invoice, pay_url}."""
	from frappe.utils import getdate, today

	from qtt_platform import invoice_billing, one_plan
	from qtt_platform import invoice_billing_rules as billing_rules
	from qtt_platform.audit import write_audit_event
	from qtt_platform.billing import paylink
	from qtt_platform.subscription import service as subscription_service
	from qtt_platform.tenant.guards import require_tenant_role

	tenant = resolve_active_tenant(frappe.session.user)
	if not tenant:
		frappe.throw(_("Choose a business first."))
	require_tenant_role(tenant, ["Tenant Owner"])
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
		current.db_set("status", "cancelled")  # switching monthly ↔ yearly before paying: the new one replaces it
	sub = subscription_service.create_subscription(tenant, ONE_PLAN_PRODUCT, plan)
	start = getdate(today())
	# Off until the first invoice is paid — paying turns it on (invoice_billing.on_invoice_update).
	sub.db_set({"status": "suspended", "billing_mode": "invoice", "trial_start": None, "trial_end": None, "paid_until": None,
				"current_period_start": start, "current_period_end": start})
	invoice = invoice_billing.invoice_period(sub.name, start)
	write_audit_event("one_plan_subscribe", tenant=tenant, product=ONE_PLAN_PRODUCT, target_doctype="QTT Product Subscription",
					  target_name=sub.name, metadata={"plan": plan, "invoice": invoice})
	months = billing_rules.months_for("yearly" if period == "yearly" else "monthly")
	return {"status": "awaiting_payment" if invoice else "active", "invoice": invoice,
			"pay_url": paylink.payment_url(invoice) if invoice else None, "months": months}
