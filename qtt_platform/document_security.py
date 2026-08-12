"""
Cross-cutting document-level tenant+product resolution — the layer
has_permission / permission_query_conditions hooks (Phase 7) are built on,
and the last four functions of the originally-specified seven-function
authorization engine (resolve_active_tenant, require_tenant_membership,
require_tenant_role live in tenant/; require_product_access,
require_product_role live in product/guards.py; the four below complete
the set: resolve_tenant_for_doc, require_document_tenant_and_product,
require_same_tenant_reference, assert_tenant_access).
"""

import frappe
from frappe import _

from qtt_platform.product.guards import require_product_access
from qtt_platform.product.registry import resolve_product_for_doctype
from qtt_platform.tenant.context import resolve_active_tenant


def resolve_tenant_for_doc(doctype: str, name: str) -> str | None:
	"""Resolves which tenant owns a specific document.

	Phase 3 implements only the direct-field case: a doctype with its own
	`tenant` Link field, which is true of every doctype registered so far
	(QTT Product Access). The parent-walk case for hook-only doctypes
	(Course Chapter, Timetable, Discussion Topic in the LMS integration
	design — none of which are registered yet, since that's Phase 10) is
	added when the first such doctype is actually registered, via a small
	PARENT_LINK-style dispatch table, not guessed at here in advance for
	doctypes that don't exist in this app.

	Never raises — returns None for a doctype with no `tenant` field, or
	a document that doesn't exist. Callers decide whether None is fatal.
	"""
	meta = frappe.get_meta(doctype)
	if not meta.has_field("tenant"):
		return None
	return frappe.db.get_value(doctype, name, "tenant")


def require_document_tenant_and_product(doctype: str, name: str, tenant: str, user: str | None = None):
	"""The check has_permission hooks (Phase 7) will call for every
	tenant+product-scoped doctype: does this document belong to the
	caller's active tenant, AND does the caller hold Product Access to
	whichever product this doctype belongs to (resolved via the static
	registry, never a per-row field). Raises frappe.PermissionError on
	any mismatch rather than returning a boolean, so a caller can't
	accidentally ignore a failed check.
	"""
	doc_tenant = resolve_tenant_for_doc(doctype, name)
	if doc_tenant != tenant:
		frappe.throw(_("This document does not belong to your active tenant."), frappe.PermissionError)

	product = resolve_product_for_doctype(doctype)
	if not product:
		# A tenant-scoped doctype with no product registration at all is a
		# deploy-time mistake (every tenant-scoped doctype should be
		# registered to exactly one product) — not something to silently
		# work around here. Nothing further to check for an unregistered
		# doctype; it is simply not product-gated by this function.
		return

	require_product_access(tenant, product, user=user)


def require_same_tenant_reference(*refs: tuple[str, str], tenant: str):
	"""Asserts every (doctype, name) pair in `refs` resolves to `tenant` —
	the cross-tenant reference smuggling guard (hardening review section
	7). Used inside a doctype's own validate(), e.g. a Batch checking
	that the Course it references belongs to the same tenant it does.
	Empty/None names are skipped (an optional Link field left blank isn't
	a smuggling attempt)."""
	for doctype, name in refs:
		if not name:
			continue
		doc_tenant = resolve_tenant_for_doc(doctype, name)
		if doc_tenant != tenant:
			frappe.throw(
				_("{0} {1} does not belong to the same tenant.").format(doctype, name),
				frappe.ValidationError,
			)


def assert_tenant_access(doctype: str, name: str, user: str | None = None):
	"""Convenience wrapper for whitelisted methods that receive a document
	name from the request: resolves the caller's own active tenant and
	checks the document against it (tenant AND product) in one call —
	the one-liner a whitelisted method should reach for by default,
	per the hardening review section 14's mandatory pattern, step 6."""
	tenant = resolve_active_tenant(user=user)
	if not tenant:
		frappe.throw(_("No active tenant."), frappe.PermissionError)
	require_document_tenant_and_product(doctype, name, tenant, user=user)
