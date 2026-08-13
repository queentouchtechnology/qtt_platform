"""
Reporting layer (production-readiness audit, P4) — six platform-level
reports, all reading data that already exists from earlier phases
(billing, subscriptions, AI credits, audit log, invitations, team
membership). No new doctype, no new business logic: every report here is
a read-only aggregation over rows other phases already write.

One dispatcher, not six one-off whitelisted methods — mirrors the
dict-of-handlers shape `ai_feature_handlers`/`usage_resolvers` already
use elsewhere in this app, just without a hooks.py registry (unlike
those, no other app ever needs to plug a report in here; qmp_lms_bridge
has its own separate `reports.py` with its own dispatcher for the same
reason `ai_features.py` lives in that app, not this one).

Every report is scoped to the CALLER'S OWN active tenant only — Tenant
Owner/Admin, the same governance-role bar `qtt_platform/api/invitation.py`
uses for invite/revoke. In particular, "team growth" (report #6) is
deliberately THIS tenant's own membership headcount over time, not a
platform-wide new-tenant-signup metric — the latter would require
cross-tenant visibility no single Tenant Owner should ever have, the
same reasoning that keeps every other endpoint in this app tenant-scoped.
"""

import frappe

from qtt_platform.errors import fail, ok
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_role

_REPORT_GOVERNANCE_ROLES = ["Tenant Owner", "Tenant Admin"]


def _date_filter(field: str, date_from: str | None, date_to: str | None) -> tuple[str, list]:
	"""Builds a `AND field BETWEEN %s AND %s`-shaped SQL fragment (or the
	half-open variants) plus its params — every report below shares this
	so a missing date_from/date_to just omits that bound rather than
	requiring the caller to always pass both."""
	if date_from and date_to:
		return f" AND {field} BETWEEN %s AND %s", [date_from, date_to]
	if date_from:
		return f" AND {field} >= %s", [date_from]
	if date_to:
		return f" AND {field} <= %s", [date_to]
	return "", []


def _revenue_report(tenant: str, date_from: str | None, date_to: str | None) -> dict:
	date_clause, date_params = _date_filter("p.paid_at", date_from, date_to)
	rows = frappe.db.sql(
		f"""
		SELECT p.name, p.invoice, p.amount, p.currency, p.status, p.paid_at, p.refund_of
		FROM `tabQTT Payment` p
		INNER JOIN `tabQTT Invoice` i ON i.name = p.invoice
		WHERE i.tenant = %s {date_clause}
		ORDER BY p.paid_at DESC
		""",
		[tenant, *date_params],
		as_dict=True,
	)
	succeeded = [r for r in rows if r.status == "succeeded"]
	refunded = [r for r in rows if r.status == "refunded"]
	return {
		"summary": {
			"total_revenue": sum(r.amount for r in succeeded),
			"total_refunded": sum(r.amount for r in refunded),
			"net_revenue": sum(r.amount for r in succeeded) - sum(r.amount for r in refunded),
			"payment_count": len(rows),
		},
		"rows": rows,
	}


def _subscription_lifecycle_report(tenant: str, date_from: str | None, date_to: str | None) -> dict:
	date_clause, date_params = _date_filter("e.occurred_at", date_from, date_to)
	rows = frappe.db.sql(
		f"""
		SELECT e.subscription, e.event_type, e.from_plan, e.to_plan, e.occurred_at,
			s.product, s.status AS current_status
		FROM `tabQTT Subscription Event` e
		INNER JOIN `tabQTT Product Subscription` s ON s.name = e.subscription
		WHERE s.tenant = %s {date_clause}
		ORDER BY e.occurred_at DESC
		""",
		[tenant, *date_params],
		as_dict=True,
	)
	summary = {"created": 0, "renewed": 0, "upgraded": 0, "downgraded": 0, "cancelled": 0}
	for row in rows:
		if row.event_type in summary:
			summary[row.event_type] += 1
	return {"summary": summary, "rows": rows}


def _ai_usage_report(tenant: str, date_from: str | None, date_to: str | None) -> dict:
	date_clause, date_params = _date_filter("creation", date_from, date_to)
	rows = frappe.db.sql(
		f"""
		SELECT name, product, user, feature, provider, model, status,
			input_tokens, output_tokens, total_tokens, credits_used, provider_cost,
			duration_ms, creation
		FROM `tabQTT AI Usage Record`
		WHERE tenant = %s {date_clause}
		ORDER BY creation DESC
		""",
		[tenant, *date_params],
		as_dict=True,
	)
	return {
		"summary": {
			"request_count": len(rows),
			"total_credits_used": sum(r.credits_used or 0 for r in rows),
			"total_tokens": sum(r.total_tokens or 0 for r in rows),
			"total_provider_cost": sum(r.provider_cost or 0 for r in rows),
		},
		"rows": rows,
	}


def _audit_log_report(tenant: str, date_from: str | None, date_to: str | None) -> dict:
	date_clause, date_params = _date_filter("occurred_at", date_from, date_to)
	rows = frappe.db.sql(
		f"""
		SELECT name, event_type, actor, target_doctype, target_name, occurred_at
		FROM `tabQTT Audit Log`
		WHERE tenant = %s {date_clause}
		ORDER BY occurred_at DESC
		LIMIT 500
		""",
		[tenant, *date_params],
		as_dict=True,
	)
	return {
		"summary": {
			"event_count": len(rows),
			"distinct_event_types": len({r.event_type for r in rows}),
		},
		"rows": rows,
	}


def _team_activity_report(tenant: str, date_from: str | None, date_to: str | None) -> dict:
	date_clause, date_params = _date_filter("creation", date_from, date_to)
	rows = frappe.db.sql(
		f"""
		SELECT name, email, tenant_role, product, product_role, status, creation, accepted_at
		FROM `tabQTT Invitation`
		WHERE tenant = %s {date_clause}
		ORDER BY creation DESC
		""",
		[tenant, *date_params],
		as_dict=True,
	)
	summary = {"invited": len(rows), "accepted": 0, "pending": 0, "revoked": 0, "expired": 0}
	for row in rows:
		if row.status in summary:
			summary[row.status] += 1
	return {"summary": summary, "rows": rows}


def _team_growth_report(tenant: str, date_from: str | None, date_to: str | None) -> dict:
	"""THIS tenant's own active-membership headcount over time, bucketed
	by month — see this module's own docstring for why this is NOT a
	platform-wide new-tenant metric."""
	date_clause, date_params = _date_filter("creation", date_from, date_to)
	rows = frappe.db.sql(
		f"""
		SELECT DATE_FORMAT(creation, '%%Y-%%m') AS month, COUNT(*) AS new_members
		FROM `tabQTT Tenant Membership`
		WHERE tenant = %s AND status = 'active' {date_clause}
		GROUP BY month
		ORDER BY month ASC
		""",
		[tenant, *date_params],
		as_dict=True,
	)
	return {
		"summary": {"total_active_members": frappe.db.count("QTT Tenant Membership", {"tenant": tenant, "status": "active"})},
		"rows": rows,
	}


_REPORTS = {
	"revenue": _revenue_report,
	"subscription_lifecycle": _subscription_lifecycle_report,
	"ai_usage": _ai_usage_report,
	"audit_log": _audit_log_report,
	"team_activity": _team_activity_report,
	"team_growth": _team_growth_report,
}


@frappe.whitelist()
def get_report(report_key: str, date_from: str | None = None, date_to: str | None = None) -> dict:
	tenant = resolve_active_tenant()
	if not tenant:
		return fail("TENANT_ACCESS_DENIED", "No active tenant.")

	try:
		require_tenant_role(tenant, _REPORT_GOVERNANCE_ROLES)
	except frappe.PermissionError as exc:
		return fail("ROLE_PERMISSION_DENIED", str(exc))

	handler = _REPORTS.get(report_key)
	if not handler:
		return fail("REPORT_NOT_FOUND", f"Unknown report: {report_key}")

	return ok(handler(tenant, date_from, date_to))
