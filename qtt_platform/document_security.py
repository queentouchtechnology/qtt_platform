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


#: Static parent-link registry cache key — see _get_static_parent_link().
_STATIC_LINK_CACHE_KEY = "qtt_tenant_static_parent_links"
#: Dynamic (polymorphic) parent-link registry cache key.
_DYNAMIC_LINK_CACHE_KEY = "qtt_tenant_dynamic_parent_links"
_REGISTRY_CACHE_TTL = 60 * 60


def resolve_tenant_for_doc(doctype: str, name: str) -> str | None:
	"""Resolves which tenant owns a specific document. Three cases, tried
	in order:

	1. Direct field — the doctype has its own `tenant` Link (every
	   doctype in qtt_platform itself, and every LMS anchor/denormalized
	   doctype from Phase 10 onward).
	2. Static parent link — a hooks.py-registered
	   `tenant_parent_links = {"Course Chapter": ("course", "LMS Course")}`
	   entry: read `course` off the doc, recurse into LMS Course.
	3. Dynamic (polymorphic) parent link — a hooks.py-registered
	   `tenant_dynamic_parent_links = {"Discussion Topic":
	   ("reference_doctype", "reference_docname")}` entry: both the parent
	   DOCTYPE and NAME are read from fields on the row itself, then
	   recurse.

	Both registries are populated by products via their own hooks.py —
	qtt_platform itself registers neither (see Phase 2's identical
	pattern for the usage-resolver registry). Recursive, so a multi-level
	hierarchy resolves correctly without each level needing its own
	direct field. Never raises — returns None if nothing resolves, or the
	document/parent doesn't exist. Callers decide whether None is fatal.
	"""
	meta = frappe.get_meta(doctype)
	if meta.has_field("tenant"):
		return frappe.db.get_value(doctype, name, "tenant")

	dynamic_link = _get_dynamic_parent_link(doctype)
	if dynamic_link:
		doctype_field, name_field = dynamic_link
		row = frappe.db.get_value(doctype, name, [doctype_field, name_field], as_dict=True)
		if not row or not row.get(doctype_field) or not row.get(name_field):
			return None
		return resolve_tenant_for_doc(row[doctype_field], row[name_field])

	static_link = _get_static_parent_link(doctype)
	if static_link:
		parent_field, parent_doctype = static_link
		parent_name = frappe.db.get_value(doctype, name, parent_field)
		if not parent_name:
			return None
		return resolve_tenant_for_doc(parent_doctype, parent_name)

	return None


def resolve_tenant_for_new_doc(doc) -> str | None:
	"""Like resolve_tenant_for_doc(), but resolves from an IN-MEMORY
	document object's own field values rather than re-querying the
	database for `doc` itself — the correct approach inside a validate()/
	before_insert hook (SaaS lifecycle Phase G's role-enforcement hooks
	are the first caller), where a new document may not be committed —
	or even fully named — yet. Only the PARENT lookup (for a parent-link
	doctype) still hits the database, since the parent is assumed to
	already exist. Same three-case precedence as resolve_tenant_for_doc():
	direct field, dynamic parent link, static parent link."""
	meta = frappe.get_meta(doc.doctype)
	if meta.has_field("tenant"):
		return doc.get("tenant")

	dynamic_link = _get_dynamic_parent_link(doc.doctype)
	if dynamic_link:
		doctype_field, name_field = dynamic_link
		parent_doctype = doc.get(doctype_field)
		parent_name = doc.get(name_field)
		if not parent_doctype or not parent_name:
			return None
		return resolve_tenant_for_doc(parent_doctype, parent_name)

	static_link = _get_static_parent_link(doc.doctype)
	if static_link:
		parent_field, parent_doctype = static_link
		parent_name = doc.get(parent_field)
		if not parent_name:
			return None
		return resolve_tenant_for_doc(parent_doctype, parent_name)

	return None


def _build_link_registry(hook_name: str) -> dict:
	merged: dict = {}
	raw = frappe.get_hooks(hook_name) or {}
	# Same defensive both-shapes handling as usage/registry.py, and the
	# same open question about frappe.get_hooks()'s exact return shape
	# for a custom dict-valued hook — see that module's comment.
	if isinstance(raw, dict):
		merged.update(raw)
	else:
		for app_value in raw:
			if isinstance(app_value, dict):
				merged.update(app_value)
	return merged


def _get_static_parent_link(doctype: str) -> tuple[str, str] | None:
	registry = frappe.cache().get_value(_STATIC_LINK_CACHE_KEY)
	if registry is None:
		registry = _build_link_registry("tenant_parent_links")
		frappe.cache().set_value(_STATIC_LINK_CACHE_KEY, registry, expires_in_sec=_REGISTRY_CACHE_TTL)
	entry = registry.get(doctype)
	return tuple(entry) if entry else None


def _get_dynamic_parent_link(doctype: str) -> tuple[str, str] | None:
	registry = frappe.cache().get_value(_DYNAMIC_LINK_CACHE_KEY)
	if registry is None:
		registry = _build_link_registry("tenant_dynamic_parent_links")
		frappe.cache().set_value(_DYNAMIC_LINK_CACHE_KEY, registry, expires_in_sec=_REGISTRY_CACHE_TTL)
	entry = registry.get(doctype)
	return tuple(entry) if entry else None


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
