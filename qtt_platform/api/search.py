"""
Search everything in the active business from one box (rules in
qtt_platform.search_logic). Results only ever come from what this person may
see; tapping one opens that record in its app.

  everything(q) -> [{type, id, title, subtitle, product, icon}]

Sources: the shared customer directory here, plus every app's own records
through the `qtt_search_providers` hook — (user, tenant, q) -> list.
One source failing never breaks search.
"""

import frappe

from qtt_platform import search_logic as logic
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership


def _customers(user: str, tenant: str, q: str) -> list[dict]:
	require_tenant_membership(tenant)
	words = logic.terms(q)
	or_filters = []
	for f in ("customer_name", "company_name", "email", "city", "gstin"):
		or_filters.append(["QTT Customer", f, "like", f"%{words[0]}%"])
	d = logic.digits(q)
	if d:
		or_filters.append(["QTT Customer", "phone", "like", f"%{d}%"])
	rows = frappe.get_all("QTT Customer", filters={"tenant": tenant, "status": "Active"}, or_filters=or_filters,
						  fields=["name", "customer_name", "company_name", "phone", "email", "city", "gstin"], limit=50)
	out = []
	for r in rows:
		if not logic.matches([r.customer_name, r.company_name, r.phone, r.email, r.city, r.gstin], q):
			continue
		out.append({"type": "customer", "id": r.name, "title": r.customer_name,
					"subtitle": " · ".join(x for x in (r.company_name, r.phone, r.city) if x), "product": None, "icon": "person"})
	return out[: logic.PER_SOURCE]


@frappe.whitelist(methods=["GET"])
def everything(q: str | None = None) -> list[dict]:
	q = (q or "").strip()
	if len(q) < logic.MIN_QUERY:
		return []
	user = frappe.session.user
	tenant = resolve_active_tenant(user)
	if not tenant:
		return []
	results = []
	for source in [_customers] + [frappe.get_attr(p) for p in frappe.get_hooks("qtt_search_providers") or []]:
		try:
			results.extend((source(user, tenant, q) or [])[: logic.PER_SOURCE])
		except (frappe.PermissionError, frappe.ValidationError):
			continue  # this person doesn't use that app (or it isn't set up)
		except Exception:
			frappe.log_error(title=f"qtt search: {getattr(source, '__module__', source)}", message=frappe.get_traceback())
	return logic.rank(results, q)
