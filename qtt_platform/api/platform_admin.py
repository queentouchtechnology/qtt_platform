"""
QTT staff console endpoints — every function requires the platform-wide
`QTT Platform Owner` role (tenant/guards.require_platform_owner), never a
tenant role. Product-agnostic: products appear only as QTT Product rows.

Deliberately small: read-mostly overviews plus suspend / reactivate.
Deep configuration stays in Frappe Desk.
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES
from qtt_platform.tenant.guards import require_platform_owner
from qtt_platform.smart_list import smart_get_all

#: Statuses a platform owner may set from the console. cancelled/archived
#: are lifecycle outcomes of billing/cancellation, not console toggles.
SETTABLE_TENANT_STATUSES = ("trial", "active", "suspended")
_MAX_PAGE = 100


@frappe.whitelist(methods=["GET"])
def overview() -> dict:
	require_platform_owner()
	tenant_counts = _count_by("QTT Tenant", "status")
	subs = frappe.db.sql(
		"""SELECT s.product, s.status, COUNT(*) AS n
		   FROM `tabQTT Product Subscription` s
		   JOIN `tabQTT Tenant Product Subscription Pointer` p ON p.current_subscription = s.name
		   GROUP BY s.product, s.status""",
		as_dict=True,
	)
	products: dict[str, dict] = {}
	for row in subs:
		products.setdefault(row.product, {})[row.status] = row.n
	return {
		"tenants": tenant_counts,
		"tenants_total": sum(tenant_counts.values()),
		"subscriptions_by_product": products,
		"members_total": frappe.db.count("QTT Tenant Membership", {"status": "active"}),
	}


@frappe.whitelist(methods=["GET"])
def list_tenants(q: str | None = None, status: str | None = None, start: int = 0, page_length: int = 20) -> dict:
	require_platform_owner()
	start = max(0, int(start or 0))
	page_length = min(_MAX_PAGE, max(1, int(page_length or 20)))

	filters = {}
	if status:
		filters["status"] = status
	# Intelligent search: every word, any order, one typo forgiven.
	rows, has_more = smart_get_all(
		"QTT Tenant",
		filters=filters,
		fields=["name", "tenant_name", "slug", "status", "owner_user", "trial_ends_on", "creation"],
		search_fields=["tenant_name", "slug", "owner_user"],
		title_field="tenant_name",
		q=q,
		order_by="creation desc",
		start=start,
		page_length=page_length,
	)
	products = _current_products([r.name for r in rows])
	for r in rows:
		r["creation"] = str(r.creation)
		r["trial_ends_on"] = str(r.trial_ends_on) if r.trial_ends_on else None
		r["products"] = products.get(r.name, [])
	return {"tenants": rows, "start": start, "page_length": page_length, "has_more": has_more}


@frappe.whitelist(methods=["GET"])
def get_tenant(tenant: str) -> dict:
	require_platform_owner()
	doc = frappe.db.get_value(
		"QTT Tenant",
		tenant,
		["name", "tenant_name", "slug", "status", "owner_user", "trial_ends_on", "country", "creation"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("Business not found."), frappe.DoesNotExistError)
	doc["creation"] = str(doc.creation)
	doc["trial_ends_on"] = str(doc.trial_ends_on) if doc.trial_ends_on else None

	members = frappe.get_all(
		"QTT Tenant Membership",
		filters={"tenant": tenant},
		fields=["user", "tenant_role", "status"],
		order_by="creation asc",
	)
	audit = frappe.get_all(
		"QTT Audit Log",
		filters={"tenant": tenant},
		fields=["event_type", "actor", "product", "occurred_at"],
		order_by="occurred_at desc",
		page_length=25,
	)
	for a in audit:
		a["occurred_at"] = str(a.occurred_at)
	return {
		"tenant": doc,
		"members": members,
		"products": _current_products([tenant]).get(tenant, []),
		"recent_activity": audit,
	}


@frappe.whitelist(methods=["POST"])
def set_tenant_status(tenant: str, status: str, reason: str | None = None) -> dict:
	"""Suspend or reactivate a workspace. Suspension takes effect on every
	member's next request (tenant guards re-check status live) and the
	realtime hook tells connected apps immediately."""
	require_platform_owner()
	if status not in SETTABLE_TENANT_STATUSES:
		frappe.throw(_("Status must be one of: {0}.").format(", ".join(SETTABLE_TENANT_STATUSES)))
	doc = frappe.get_doc("QTT Tenant", tenant)
	before = doc.status
	if before == status:
		return {"tenant": tenant, "status": status}
	doc.status = status
	doc.save(ignore_permissions=True)
	write_audit_event(
		"tenant_status_changed",
		tenant=tenant,
		target_doctype="QTT Tenant",
		target_name=tenant,
		before_state={"status": before},
		after_state={"status": status},
		metadata={"reason": (reason or "").strip()[:500] or None, "by": "platform_owner"},
	)
	return {"tenant": tenant, "status": status}


# --------------------------------------------------------------------------
def _count_by(doctype: str, field: str) -> dict:
	rows = frappe.db.sql(f"SELECT `{field}` AS k, COUNT(*) AS n FROM `tab{doctype}` GROUP BY `{field}`", as_dict=True)
	return {r.k or "": r.n for r in rows}


def _current_products(tenants: list[str]) -> dict[str, list[dict]]:
	"""Each tenant's CURRENT subscription per product (via the pointer table,
	same rule as subscription.service.get_current_subscription)."""
	if not tenants:
		return {}
	rows = frappe.db.sql(
		"""SELECT p.tenant, s.product, s.status, pl.plan_code, s.trial_end
		   FROM `tabQTT Tenant Product Subscription Pointer` p
		   JOIN `tabQTT Product Subscription` s ON s.name = p.current_subscription
		   LEFT JOIN `tabQTT Plan` pl ON pl.name = s.plan
		   WHERE p.tenant IN %(tenants)s""",
		{"tenants": tuple(tenants)},
		as_dict=True,
	)
	result: dict[str, list[dict]] = {}
	for r in rows:
		result.setdefault(r.tenant, []).append(
			{
				"product": r.product,
				"status": r.status,
				"plan_code": r.plan_code,
				"trial_end": str(r.trial_end) if r.trial_end else None,
				"is_open": r.status in OPEN_SUBSCRIPTION_STATUSES,
			}
		)
	return result
