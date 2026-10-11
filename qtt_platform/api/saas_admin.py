"""
QTT Admin → SaaS: plans and pricing, customer actions, revenue.
Platform Owners only (like api/platform_admin.py, which keeps the
workspace list/detail and suspend/reactivate).

Customer actions reuse the subscription/billing services the customer
flows already use — same Razorpay ordering (gateway first, local write
second), same events — rather than re-implementing lifecycle rules.
Every action is audited.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from qtt_platform import saas_admin_logic as logic
from qtt_platform.audit import write_audit_event
from qtt_platform.billing import service as billing_service
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
	require_platform_owner()
	filters = {"product": product} if product else {}
	plans = frappe.get_all(
		"QTT Plan",
		filters=filters,
		fields=["name", "plan_code", "product", "display_name", "base_price", "billing_period", "trial_days", "is_public"],
		order_by="product asc, base_price asc",
	)
	features = frappe.get_all(
		"QTT Plan Feature",
		filters={"parenttype": "QTT Plan", "parent": ["in", [p.name for p in plans] or [""]]},
		fields=["parent", "feature_key", "limit_value"],
		order_by="idx asc",
	)
	by_plan: dict[str, list] = {}
	for f in features:
		by_plan.setdefault(f.parent, []).append({"feature_key": f.feature_key, "limit_value": f.limit_value})
	counts = _current_subscription_counts()
	for p in plans:
		p["features"] = by_plan.get(p.name, [])
		p["subscribers"] = counts.get(p.name, 0)
		p["is_public"] = bool(p.is_public)
	products = frappe.get_all("QTT Product", fields=["product_key", "display_name", "status"], order_by="display_name asc")
	return {"plans": plans, "products": products, "currency": CURRENCY}


@frappe.whitelist(methods=["POST"])
def save_plan(plan, name: str | None = None) -> dict:
	"""Create (no name) or edit a plan. A price/period change on a plan
	already linked to Razorpay clears that link so the next subscription
	creates a fresh gateway plan; existing subscribers keep their current
	gateway price until their plan changes."""
	require_platform_owner()
	data = _json(plan)
	clean = _clean(lambda: logic.clean_plan(data, is_new=not name))

	if name:
		doc = frappe.get_doc("QTT Plan", name)
		before = {k: doc.get(k) for k in ("display_name", "base_price", "billing_period", "trial_days", "is_public")}
		before["features"] = [{"feature_key": f.feature_key, "limit_value": f.limit_value} for f in doc.features]
		gateway_reset = bool(doc.razorpay_plan_id) and logic.billing_changed(before, clean)
	else:
		if not frappe.db.exists("QTT Product", clean["product"]):
			frappe.throw(_("Unknown product."))
		if frappe.db.exists("QTT Plan", {"product": clean["product"], "plan_code": clean["plan_code"]}):
			frappe.throw(_("This product already has a plan with that code."))
		doc = frappe.new_doc("QTT Plan")
		doc.product = clean["product"]
		doc.plan_code = clean["plan_code"]
		before, gateway_reset = {}, False

	doc.update({k: clean[k] for k in ("display_name", "base_price", "billing_period", "trial_days", "is_public")})
	doc.set("features", clean["features"])
	if gateway_reset:
		doc.razorpay_plan_id = None
	doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)

	write_audit_event(
		"plan_saved" if name else "plan_created",
		product=doc.product,
		target_doctype="QTT Plan",
		target_name=doc.name,
		before_state=before or None,
		after_state={k: clean[k] for k in clean if k != "features"} | {"features": clean["features"]},
		metadata={"plan_code": doc.plan_code, "gateway_plan_reset": gateway_reset},
	)
	return {**list_plans(), "saved": doc.name, "gateway_plan_reset": gateway_reset}


# --------------------------------------------------------------------------
# Customer (workspace) actions
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def workspace_billing(tenant: str) -> dict:
	"""Per product: current subscription, usage against limits, overrides,
	and the plans it could move to. Complements platform_admin.get_tenant."""
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
		plans = frappe.get_all(
			"QTT Plan",
			filters={"product": p.product_key},
			fields=["name", "plan_code", "display_name", "base_price", "billing_period", "trial_days"],
			order_by="base_price asc",
		)
		products.append({
			"product": p.product_key,
			"product_name": p.display_name,
			"subscription": sub,
			"usage": usage,
			"overrides": overrides,
			"plans": plans,
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


@frappe.whitelist(methods=["POST"])
def add_product(tenant: str, product: str, plan: str) -> dict:
	"""Subscribe a workspace to a product (trial if the plan has trial
	days). Refused while it already has an open subscription."""
	require_platform_owner()
	_require_tenant(tenant)
	current = subscription_service.get_current_subscription(tenant, product)
	if current and current.status in OPEN_SUBSCRIPTION_STATUSES:
		frappe.throw(_("This workspace already has this product. Change its plan instead."))
	sub = subscription_service.create_subscription(tenant, product, plan)
	granted = _grant_owner_initial_role(tenant, product)
	_audit("admin_product_added", tenant, product, sub.name, {"plan": plan, "owner_access": granted})
	return workspace_billing(tenant)


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
def change_plan(tenant: str, product: str, plan: str) -> dict:
	"""Immediate plan change by QTT (upgrade or downgrade). Razorpay is
	updated first; if that fails nothing changes locally."""
	require_platform_owner()
	current = _open_subscription(tenant, product)
	if current.cancel_at_period_end or current.cancellation_requested_at:
		frappe.throw(_("A cancellation is pending. Undo it first, then change the plan."))
	if current.plan == plan:
		frappe.throw(_("The workspace is already on this plan."))
	if frappe.db.get_value("QTT Plan", plan, "product") != product:
		frappe.throw(_("That plan belongs to another product."))
	try:
		billing_service.sync_razorpay_plan_change(current.name, plan, immediate=True)
	except Exception:
		frappe.log_error(title=f"saas_admin.change_plan: Razorpay sync failed for {current.name}")
		frappe.throw(_("Couldn't update the payment gateway (Razorpay). Nothing was changed."))
	if current.scheduled_plan:
		subscription_service.clear_scheduled_plan_change(tenant, product)
	new_sub = subscription_service.change_plan(tenant, product, plan)
	_audit("admin_plan_changed", tenant, product, new_sub.name, {"from": current.plan, "to": plan})
	return workspace_billing(tenant)


@frappe.whitelist(methods=["POST"])
def extend_trial(tenant: str, product: str, days) -> dict:
	require_platform_owner()
	current = subscription_service.get_current_subscription(tenant, product)
	if not current:
		frappe.throw(_("Your business doesn't have this app."))
	status, new_end = _clean(lambda: logic.extended_trial(
		status=current.status,
		trial_end=current.trial_end,
		linked_to_gateway=bool(current.razorpay_subscription_id),
		days=days,
		today=getdate(today()),
	))
	before = {"status": current.status, "trial_end": _d(current.trial_end)}
	current.status = status
	current.trial_end = new_end
	current.current_period_end = new_end
	if not current.trial_start:
		current.trial_start = getdate(today())
	current.save(ignore_permissions=True)
	_audit("admin_trial_extended", tenant, product, current.name, {"days": int(days)},
		   before=before, after={"status": status, "trial_end": str(new_end)})
	return workspace_billing(tenant)


@frappe.whitelist(methods=["POST"])
def cancel_product(tenant: str, product: str, immediately=0, reason: str | None = None) -> dict:
	"""Cancel at period end (default) or now. Razorpay is cancelled too;
	a gateway failure is logged and caught by the nightly reconcile, the
	same as a customer-initiated cancel."""
	require_platform_owner()
	_open_subscription(tenant, product)
	at_period_end = str(immediately).lower() not in ("1", "true", "yes")
	reason = (reason or "").strip()[:500] or None
	sub = subscription_service.cancel_subscription(tenant, product, at_period_end=at_period_end, reason=reason)
	try:
		billing_service.cancel_razorpay_subscription(sub.name, cancel_at_cycle_end=at_period_end)
	except Exception:
		frappe.log_error(title=f"saas_admin.cancel_product: Razorpay cancel failed for {sub.name}")
	_audit("admin_product_cancelled", tenant, product, sub.name, {"at_period_end": at_period_end, "reason": reason})
	return workspace_billing(tenant)


@frappe.whitelist(methods=["POST"])
def undo_cancellation(tenant: str, product: str) -> dict:
	require_platform_owner()
	sub = subscription_service.resume_subscription(tenant, product)
	_audit("admin_cancellation_undone", tenant, product, sub.name, {})
	return workspace_billing(tenant)


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
		"""SELECT s.name, s.tenant, s.product, s.status, s.trial_end, s.current_period_end,
		          pl.base_price, pl.billing_period, pl.plan_code, t.tenant_name
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
def _json(value) -> dict:
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid data."))
	if not isinstance(value, dict):
		frappe.throw(_("Invalid data."))
	return value


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
