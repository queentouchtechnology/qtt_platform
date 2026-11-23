"""
QTT Admin → SaaS: the one plan, a business's apps (usage and overrides), revenue. Every app comes with QTT OS (free
until the free-use limits, then the one plan): no per-app plans or per-app plan changes (gone 23 Nov 2026).
Platform Owners only (like api/platform_admin.py, which keeps the
workspace list/detail and suspend/reactivate).

Customer actions reuse the subscription/billing services the customer
flows already use — same Razorpay ordering (gateway first, local write
second), same events — rather than re-implementing lifecycle rules.
Every action is audited.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from qtt_platform import saas_admin_logic as logic
from qtt_platform.audit import write_audit_event
from qtt_platform.entitlement.engine import get_entitlements_with_usage
from qtt_platform.realtime import notify_users, tenant_users
from qtt_platform.subscription import service as subscription_service
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES
from qtt_platform.tenant.guards import require_platform_owner

CURRENCY = "INR"  # QTT Plan prices and the Razorpay gateway are INR


# --------------------------------------------------------------------------
# Plans and pricing
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_plans(product: str | None = None) -> dict:
	"""QTT Admin › Plans: the one plan for all 8 apps (monthly, yearly) with its subscribers. Its prices are set in QTT
	Admin › Settings › Free use (one_plan.sync_prices copies them here); there are no per-app plans (gone 23 Nov 2026)."""
	require_platform_owner()
	from qtt_platform.house import ONE_PLAN_PRODUCT

	plans = frappe.get_all("QTT Plan", filters={"product": ONE_PLAN_PRODUCT},
						   fields=["name", "plan_code", "product", "display_name", "base_price", "billing_period", "trial_days", "is_public"],
						   order_by="base_price asc")
	counts = _current_subscription_counts()
	for p in plans:
		p["features"] = []
		p["subscribers"] = counts.get(p.name, 0)
		p["is_public"] = bool(p.is_public)
	products = frappe.get_all("QTT Product", filters={"product_key": ONE_PLAN_PRODUCT}, fields=["product_key", "display_name", "status"])
	return {"plans": plans, "products": products, "currency": CURRENCY, "feature_catalog": {}}


# --------------------------------------------------------------------------
# Customer (workspace) actions
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def workspace_billing(tenant: str) -> dict:
	"""Per app: whether it's on, usage against limits and overrides (every app comes with QTT OS — no per-app plans).
	Complements platform_admin.get_tenant."""
	require_platform_owner()
	_require_tenant(tenant)
	products = []
	for p in frappe.get_all("QTT Product", filters={"status": "active"}, fields=["product_key", "display_name"]):
		current = subscription_service.get_current_subscription(tenant, p.product_key)
		sub = None
		if current:
			plan = frappe.db.get_value("QTT Plan", current.plan, ["plan_code", "display_name", "base_price", "billing_period"], as_dict=True) or {}
			sub = {
				"name": current.name,
				"status": current.status,
				"plan": current.plan,
				"plan_code": plan.get("plan_code"),
				"plan_name": plan.get("display_name"),
				"price": plan.get("base_price"),
				"billing_period": plan.get("billing_period"),
				"period_end": _d(current.current_period_end),
				"trial_end": _d(current.trial_end),
				"cancel_at_period_end": bool(current.cancel_at_period_end),
				"effective_end_date": _d(current.effective_end_date),
				"scheduled_plan": current.scheduled_plan,
				"gateway_linked": bool(current.razorpay_subscription_id),
			}
		usage = []
		if current and current.status in OPEN_SUBSCRIPTION_STATUSES:
			try:
				usage = get_entitlements_with_usage(tenant, p.product_key)
			except Exception:
				frappe.log_error(title=f"saas_admin.workspace_billing usage failed for {tenant}/{p.product_key}")
		overrides = frappe.get_all(
			"QTT Tenant Feature Override",
			filters={"tenant": tenant, "product": p.product_key},
			fields=["name", "feature_key", "override_value", "reason", "expires_on"],
			order_by="creation desc",
		)
		for o in overrides:
			o["expires_on"] = _d(o.expires_on)
		from qtt_platform import app_plans

		included = app_plans.plan_for(p.product_key)
		keys = frappe.get_all("QTT Plan Feature", filters={"parent": included or "", "parenttype": "QTT Plan"}, pluck="feature_key")
		products.append({
			"product": p.product_key,
			"product_name": p.display_name,
			"subscription": sub,
			"usage": usage,
			"overrides": overrides,
			"feature_keys": sorted(k for k in keys if k),  # what an override can set (the app's one entry)
		})
	invoices = frappe.get_all(
		"QTT Invoice",
		filters={"tenant": tenant},
		fields=["name", "amount", "currency", "status", "due_date", "creation"],
		order_by="creation desc",
		page_length=10,
	)
	for i in invoices:
		i["due_date"], i["creation"] = _d(i.due_date), _d(i.creation)
	return {"tenant": tenant, "products": products, "invoices": invoices, "currency": CURRENCY}


@frappe.whitelist(methods=["GET"])
def tenant_invoices(tenant: str, start: int = 0, page_length: int = 20, status: str | None = None) -> dict:
	"""A business's invoices, newest first, a page at a time (QTT Admin; loads more as you scroll)."""
	from qtt_platform import list_sort

	require_platform_owner()
	_require_tenant(tenant)
	start, length = list_sort.page(start, page_length)
	filters = {"tenant": tenant}
	if status:
		filters["status"] = status
	rows = frappe.get_all("QTT Invoice", filters=filters, fields=["name", "amount", "currency", "status", "due_date", "creation"],
						  order_by="creation desc", start=start, page_length=length)
	for i in rows:
		i["due_date"], i["creation"] = _d(i.due_date), _d(i.creation)
	return {"invoices": rows, "has_more": len(rows) == length}


def _grant_owner_initial_role(tenant: str, product: str) -> str | None:
	"""Same rule as self-service signup: the workspace owner gets the
	product's initial role (e.g. Office Pulse → HR Admin) so someone can
	open it and hand out access. Skipped when the owner already has access
	or the product declares no initial role."""
	from qtt_platform.api.saas import _initial_product_role

	role = _initial_product_role(product)
	owner = frappe.db.get_value("QTT Tenant", tenant, "owner_user")
	membership = frappe.db.get_value("QTT Tenant Membership", {"tenant": tenant, "user": owner, "status": "active"}, "name") if owner else None
	if not role or not membership or frappe.db.exists("QTT Product Access", {"membership": membership, "product": product}):
		return None
	frappe.get_doc({"doctype": "QTT Product Access", "membership": membership, "tenant": tenant, "product": product,
					"product_role": role, "status": "active"}).insert(ignore_permissions=True)
	return f"{owner}: {role}"


@frappe.whitelist(methods=["POST"])
def set_override(tenant: str, product: str, feature_key: str, value: str, reason: str | None = None, expires_on: str | None = None) -> dict:
	"""Give one workspace a different limit or flag than its plan (e.g. 5
	extra agents until a date). Replaces the plan value while it applies."""
	require_platform_owner()
	_require_tenant(tenant)
	row = _clean(lambda: logic.clean_features([{"feature_key": feature_key, "limit_value": value}]))
	if not row:
		frappe.throw(_("Choose a feature."))
	key, val = row[0]["feature_key"], row[0]["limit_value"]
	expires = getdate(expires_on) if expires_on else None
	if expires and expires < getdate(today()):
		frappe.throw(_("The end date is in the past."))
	existing = frappe.db.get_value("QTT Tenant Feature Override", {"tenant": tenant, "product": product, "feature_key": key})
	doc = frappe.get_doc("QTT Tenant Feature Override", existing) if existing else frappe.new_doc("QTT Tenant Feature Override")
	before = {"value": doc.override_value, "expires_on": _d(doc.expires_on)} if existing else None
	doc.update({"tenant": tenant, "product": product, "feature_key": key, "override_value": val,
				"reason": (reason or "").strip()[:500] or None, "expires_on": expires})
	doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
	_audit("admin_override_set", tenant, product, doc.name, {"feature_key": key},
		   before=before, after={"value": val, "expires_on": _d(expires)})
	_refresh_apps(tenant)
	return workspace_billing(tenant)


@frappe.whitelist(methods=["POST"])
def remove_override(tenant: str, name: str) -> dict:
	require_platform_owner()
	doc = frappe.get_doc("QTT Tenant Feature Override", name)
	if doc.tenant != tenant:
		frappe.throw(_("Unknown override."), frappe.DoesNotExistError)
	_audit("admin_override_removed", tenant, doc.product, doc.name, {"feature_key": doc.feature_key},
		   before={"value": doc.override_value})
	doc.delete(ignore_permissions=True)
	_refresh_apps(tenant)
	return workspace_billing(tenant)


# --------------------------------------------------------------------------
# Revenue
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def revenue() -> dict:
	require_platform_owner()
	subs = frappe.db.sql(
		"""SELECT s.name, s.tenant, s.product, s.status, s.trial_end, s.current_period_end, s.billing_mode,
		          pl.base_price, pl.billing_period, pl.plan_code, t.tenant_name, t.is_house
		   FROM `tabQTT Tenant Product Subscription Pointer` p
		   JOIN `tabQTT Product Subscription` s ON s.name = p.current_subscription
		   LEFT JOIN `tabQTT Plan` pl ON pl.name = s.plan
		   LEFT JOIN `tabQTT Tenant` t ON t.name = s.tenant""",
		as_dict=True,
	)
	items = frappe.get_all(
		"QTT Subscription Item",
		filters={"parenttype": "QTT Product Subscription", "parent": ["in", [s.name for s in subs] or [""]]},
		fields=["parent", "quantity", "unit_price"],
	)
	by_sub: dict[str, list] = {}
	for i in items:
		by_sub.setdefault(i.parent, []).append({"quantity": i.quantity, "unit_price": i.unit_price})
	# Only what businesses are billed for: house workspaces and never-billed subscriptions aren't revenue (or "at risk").
	subs = [s for s in subs if logic.counts_as_revenue(s)]
	summary = logic.revenue_summary([{**s, "items": by_sub.get(s.name, [])} for s in subs])

	soon = add_days(today(), 7)
	trials_ending = [
		{"tenant": s.tenant, "tenant_name": s.tenant_name, "product": s.product, "plan_code": s.plan_code, "trial_end": _d(s.trial_end)}
		for s in subs
		if s.status == "trialing" and s.trial_end and str(s.trial_end) <= soon
	]
	past_due = [
		{"tenant": s.tenant, "tenant_name": s.tenant_name, "product": s.product, "plan_code": s.plan_code, "since": _d(s.current_period_end)}
		for s in subs if s.status == "past_due"
	]

	month_start = getdate(today()).replace(day=1)
	paid = frappe.db.sql(
		"""SELECT
		     COALESCE(SUM(CASE WHEN paid_at >= %(d30)s THEN amount END), 0) AS last_30_days,
		     COALESCE(SUM(CASE WHEN paid_at >= %(month)s THEN amount END), 0) AS this_month
		   FROM `tabQTT Payment` WHERE status = 'succeeded'""",
		{"d30": add_days(today(), -30), "month": month_start},
		as_dict=True,
	)[0]
	open_invoices = frappe.db.sql(
		"SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS amount FROM `tabQTT Invoice` WHERE status = 'open'",
		as_dict=True,
	)[0]
	payments = frappe.db.sql(
		"""SELECT pay.name, pay.amount, pay.currency, pay.status, pay.paid_at, inv.tenant, t.tenant_name
		   FROM `tabQTT Payment` pay
		   LEFT JOIN `tabQTT Invoice` inv ON inv.name = pay.invoice
		   LEFT JOIN `tabQTT Tenant` t ON t.name = inv.tenant
		   ORDER BY pay.paid_at DESC LIMIT 15""",
		as_dict=True,
	)
	for p in payments:
		p["paid_at"] = str(p.paid_at) if p.paid_at else None
	return {
		**summary,
		"currency": CURRENCY,
		"collected": {"last_30_days": float(paid.last_30_days), "this_month": float(paid.this_month)},
		"open_invoices": {"count": open_invoices.n, "amount": float(open_invoices.amount)},
		"trials_ending": sorted(trials_ending, key=lambda r: r["trial_end"] or ""),
		"past_due": past_due,
		"recent_payments": payments,
	}


# --------------------------------------------------------------------------
def _clean(fn):
	try:
		return fn()
	except logic.SaasInputError as exc:
		frappe.throw(_(str(exc)))


def _d(value):
	return str(value)[:10] if value else None


def _require_tenant(tenant: str) -> None:
	if not frappe.db.exists("QTT Tenant", tenant):
		frappe.throw(_("Business not found."), frappe.DoesNotExistError)


def _open_subscription(tenant: str, product: str):
	current = subscription_service.get_current_subscription(tenant, product)
	if not current or current.status not in OPEN_SUBSCRIPTION_STATUSES:
		frappe.throw(_("Your business isn't subscribed to this app."))
	return current


def _current_subscription_counts() -> dict[str, int]:
	rows = frappe.db.sql(
		"""SELECT s.plan, COUNT(*) AS n
		   FROM `tabQTT Tenant Product Subscription Pointer` p
		   JOIN `tabQTT Product Subscription` s ON s.name = p.current_subscription
		   WHERE s.status IN %(open)s GROUP BY s.plan""",
		{"open": OPEN_SUBSCRIPTION_STATUSES},
		as_dict=True,
	)
	return {r.plan: r.n for r in rows}


def _refresh_apps(tenant: str) -> None:
	"""Overrides change entitlements without touching the subscription,
	so its live-refresh hook doesn't fire — tell the apps directly."""
	notify_users(tenant_users(tenant), tenant=tenant, reason="entitlements")


def _audit(event: str, tenant: str, product: str, target: str, metadata: dict, *, before=None, after=None) -> None:
	write_audit_event(
		event,
		tenant=tenant,
		product=product,
		target_doctype="QTT Product Subscription" if not event.startswith("admin_override") else "QTT Tenant Feature Override",
		target_name=target,
		before_state=before,
		after_state=after,
		metadata={**metadata, "by": "platform_owner"},
	)
