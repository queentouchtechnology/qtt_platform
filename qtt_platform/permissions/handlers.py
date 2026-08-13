"""
Generic, reusable Frappe hook handlers — the shapes has_permission,
before_insert, and before_save hooks actually require, built on top of
qtt_platform.document_security. See this module's docstrings for exactly
which of these are registered in hooks.py today and why the rest aren't
yet — read that before assuming a function here is active.

IMPORTANT CONTEXT for why hooks.py's registrations are currently sparse:
every doctype this app has shipped through Phase 6 grants NO DocPerm to
any tenant-facing role (System Manager only — see each doctype's .json).
`has_permission` and `permission_query_conditions` hooks only ever run
for a caller who has already cleared the coarse DocPerm check for that
operation — since no tenant-facing role can clear it here, registering
either hook against qtt_platform's own doctypes today would be dead code,
not real protection. The actual protection for these doctypes is the
whitelisted API layer (api/*.py), which uses ignore_permissions=True
after its own explicit require_tenant_role/require_product_access checks.

These hooks become load-bearing once a doctype exists that DOES grant
broader DocPerm to a real Frappe Role and needs tenant/product scoping on
top of that — which is exactly LMS's shape (Course Creator, System
Manager, etc. already hold real DocPerm on real LMS doctypes). That's
Phase 10. Building the generic handlers now, rather than waiting, means
Phase 10 wires up Custom Fields and hooks.py registrations only — no new
Python logic to write at that point.
"""

import frappe
from frappe import _

from qtt_platform.document_security import require_document_tenant_and_product, resolve_tenant_for_new_doc
from qtt_platform.product.guards import require_product_access
from qtt_platform.product.registry import resolve_product_for_doctype
from qtt_platform.tenant.context import resolve_active_tenant


def has_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	"""The exact shape Frappe's has_permission hook requires:
	(doc, user, permission_type) -> bool. Never raises — has_permission
	hooks must return a bool, not throw (unlike the require_* guard
	functions this delegates to, which do throw; that's why this
	function exists as a thin bool-returning wrapper rather than exposing
	require_document_tenant_and_product directly as the hook).

	Fully generic and doctype-agnostic — works for any doctype with a
	`tenant` field, resolved product or not. Register per-doctype once a
	real target exists, e.g.:

		has_permission = {
			"Course Chapter": "qtt_platform.permissions.handlers.has_permission",
		}

	A NEW (not-yet-inserted) document needs its own branch — found via
	live testing (Part C-J multi-tenant verification): a real
	Instructor's real Course Chapter create was rejected even after
	native DocPerm and roles.py both correctly allowed it, because this
	function unconditionally went through require_document_tenant_and_product()'s
	DB-lookup path (resolve_tenant_for_doc()), which can never find a row
	for a document that doesn't exist in the database yet — Frappe calls
	this hook with permission_type="create" and the in-memory (unsaved)
	doc object, not after insert. resolve_tenant_for_new_doc() (the
	in-memory field-reading counterpart document_security.py already
	provides for exactly this reason) is used instead whenever doc.is_new().
	"""
	user = user or frappe.session.user
	tenant = resolve_active_tenant(user=user)
	if not tenant:
		return False

	if doc.is_new():
		doc_tenant = resolve_tenant_for_new_doc(doc)
		if doc_tenant != tenant:
			return False
		product = resolve_product_for_doctype(doc.doctype)
		if not product:
			return True
		try:
			require_product_access(tenant, product, user=user)
			return True
		except frappe.PermissionError:
			return False

	try:
		require_document_tenant_and_product(doc.doctype, doc.name, tenant, user=user)
		return True
	except frappe.PermissionError:
		return False


# ---------------------------------------------------------------------------
# permission_query_conditions is intentionally NOT implemented generically
# here. Its required shape — (user) -> a raw SQL WHERE-clause fragment
# string — is inherently doctype-specific: the fragment has to name the
# actual table/column that resolves back to a tenant (e.g. a hook-only
# doctype like Course Chapter would need
#   "`tabCourse Chapter`.course in (select name from `tabLMS Course`
#    where tenant in (...))"
# which cannot be written without a real doctype and a real parent-link
# column to reference. Writing a fake one now, for a doctype that doesn't
# exist, would be exactly the kind of guessed-field/invented-API this
# project has avoided throughout. Phase 10 (or whenever the first
# hook-only doctype is registered) adds one factory function per doctype
# here, following the has_permission function above as the pattern for
# how it resolves tenant — not a generic function, by design.
# ---------------------------------------------------------------------------


def stamp_tenant_before_insert(doc, method: str | None = None):
	"""Generic before_insert handler: stamps doc.tenant from the caller's
	active session tenant, overwriting any client-submitted value.

	NOT registered against any doctype yet. Every tenant-scoped doctype
	shipped so far (QTT Product Access, QTT Product Subscription, QTT
	Tenant Feature Override) is created by trusted server-side service
	code that already receives `tenant` as an explicit, pre-validated
	parameter — not by a generic end-user-facing "create in my tenant"
	whitelisted method. Stamping from session state would be WRONG for
	those call sites (a service function creating a subscription for a
	specific tenant on a caller's behalf must not have that tenant
	silently overridden by whatever the caller's own active tenant
	happens to be). This becomes useful once a product (LMS, Phase 10) has
	a simple end-user-facing create flow with no such indirection.
	"""
	if not doc.meta.has_field("tenant"):
		return
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("No active tenant."), frappe.PermissionError)
	doc.tenant = tenant


def guard_tenant_change_before_save(doc, method: str | None = None):
	"""Generic before_save handler: rejects any edit to `doc.tenant` on an
	existing document unless the caller holds the System Manager Frappe
	Role. Registered today against QTT Product Subscription and QTT
	Tenant Feature Override (see hooks.py) — a real gap this phase found:
	neither doctype's own validate() previously guarded against its
	`tenant` field being edited post-creation. (QTT Product Access needs
	no such guard — its own validate() already unconditionally re-derives
	`tenant` from the referenced membership on every save, a stronger,
	self-healing guarantee that makes a reject-and-fail check redundant.)
	"""
	if not doc.meta.has_field("tenant") or doc.is_new():
		return
	previous_tenant = frappe.db.get_value(doc.doctype, doc.name, "tenant")
	if previous_tenant and previous_tenant != doc.tenant and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Changing a document's tenant is not permitted."), frappe.PermissionError)
