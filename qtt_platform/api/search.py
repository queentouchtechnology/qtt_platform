"""
Search everything in the active business from one box (rules in
qtt_platform.search_logic). Results only ever come from what this person may
see; tapping one opens that record in its app.

  query(q, types?) -> {results, counts, suggestions, did_you_mean}  (the app)
  everything(q)    -> [{type, id, title, subtitle, product, icon}] (older apps)

Sources: the shared customer directory here, plus every app's own records
through the `qtt_search_providers` hook — (user, tenant, q) -> list.
One source failing never breaks search.
"""

import frappe

from qtt_platform import search_logic as logic
from qtt_platform.smart_list import smart_get_all
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership


def _customers(user: str, tenant: str, q: str) -> list[dict]:
	require_tenant_membership(tenant)
	rows, _more = smart_get_all("QTT Customer", filters={"tenant": tenant, "status": "Active"}, q=q, title_field="customer_name",
								fields=["name", "customer_name", "company_name", "phone", "city"],
								search_fields=["customer_name", "company_name", "email", "city", "gstin"], digits_field="phone",
								order_by="customer_name asc", page_length=logic.PER_SOURCE)
	return [{"type": "customer", "id": r.name, "title": r.customer_name,
			 "subtitle": " · ".join(x for x in (r.company_name, r.phone, r.city) if x), "product": None, "icon": "person"} for r in rows]


def _collect(q: str) -> list[dict]:
	"""Every source's records for q, best first ([] if the query is too short)."""
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
	return logic.rank(results, q, limit=60)


@frappe.whitelist(methods=["GET"])
def everything(q: str | None = None) -> list[dict]:
	"""Records only (apps before the categorized search)."""
	return _collect(q)[:30]


@frappe.whitelist(methods=["GET"])
def query(q: str | None = None, types: str | None = None) -> dict:
	"""Categorized search: results (optionally only some types), a count per
	type (for the filter chips), smart completions, and "did you mean"."""
	q = (q or "").strip()
	found = _collect(q)
	counts: dict[str, int] = {}
	for r in found:
		counts[r["type"]] = counts.get(r["type"], 0) + 1
	wanted = {t.strip() for t in (types or "").split(",") if t.strip()}
	titles = [r.get("title") or "" for r in found]
	return {
		"results": [r for r in found if not wanted or r["type"] in wanted][:40],
		"counts": counts,
		"per_source": logic.PER_SOURCE,  # a count this high means "this many or more"
		"suggestions": logic.completions(titles, q) if q else [],
		"did_you_mean": logic.did_you_mean(titles, q) if q else None,
	}
