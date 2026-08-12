"""
The product registry — the code-level trust boundary the hardening review
(section 3) requires: nothing in this module is a whitelisted REST
endpoint. These functions are meant to be called only from a product's own
`after_install`/`after_migrate`/`before_uninstall` hooks — trusted Python
running as part of a deploy, the same boundary `hooks.py` registrations
already rely on. A tenant, a Product Access row, or any HTTP request can
never reach these functions directly; there is no `@frappe.whitelist()`
anywhere in this file, deliberately.
"""

import frappe
from frappe import _

_DOCTYPE_REGISTRY_CACHE_KEY = "qtt_product_doctype_registry"
_DOCTYPE_REGISTRY_CACHE_TTL = 60 * 60  # static per deploy; an hour is generous, not load-bearing


def register_product(
	product_key: str,
	display_name: str,
	app_name: str,
	*,
	version: str | None = None,
	icon: str | None = None,
	description: str | None = None,
	roles: list[dict] | None = None,
	status: str = "active",
):
	"""Create-or-update the QTT Product row for `product_key`. Idempotent —
	safe to call on every `bench migrate`, which is exactly when a
	product's own install hook should call it, so the role catalog and
	metadata always match what's actually deployed."""
	existing_name = frappe.db.exists("QTT Product", product_key)

	if existing_name:
		product = frappe.get_doc("QTT Product", existing_name)
	else:
		product = frappe.new_doc("QTT Product")
		product.product_key = product_key

	product.display_name = display_name
	product.app_name = app_name
	product.version = version
	product.icon = icon
	product.description = description
	product.status = status

	product.set("roles", [])
	for role in roles or []:
		product.append("roles", {"role_key": role["role_key"], "role_name": role["role_name"]})

	if existing_name:
		product.save(ignore_permissions=True)
	else:
		product.insert(ignore_permissions=True)

	return product


def register_product_doctype(product_key: str, doctype_name: str, *, is_tenant_scoped: bool = True):
	"""Register one DocType as belonging to `product_key`. Idempotent for
	the common case (already registered to the SAME product — a no-op
	return). Refuses to silently move a doctype from one product to
	another, even from trusted install code — that specific operation is
	exactly the 'malicious tenant repoints an LMS doctype at HRMS' shape
	the hardening review worried about (section 3), so it requires an
	explicit delete of the old row first, never an implicit overwrite."""
	if not frappe.db.exists("QTT Product", product_key):
		frappe.throw(_("Cannot register {0} — unknown product {1}.").format(doctype_name, product_key))
	if not frappe.db.exists("DocType", doctype_name):
		frappe.throw(_("Cannot register {0} — no such DocType exists.").format(doctype_name))

	existing_name = frappe.db.exists("QTT Product DocType", {"doctype_name": doctype_name})
	if existing_name:
		current_product = frappe.db.get_value("QTT Product DocType", existing_name, "product")
		if current_product == product_key:
			return frappe.get_doc("QTT Product DocType", existing_name)
		frappe.throw(
			_(
				"{0} is already registered to product {1}. Delete that registration "
				"explicitly before re-registering it under {2}."
			).format(doctype_name, current_product, product_key)
		)

	row = frappe.get_doc(
		{
			"doctype": "QTT Product DocType",
			"product": product_key,
			"doctype_name": doctype_name,
			"is_tenant_scoped": 1 if is_tenant_scoped else 0,
		}
	)
	row.insert(ignore_permissions=True)
	_invalidate_doctype_registry_cache()
	return row


def unregister_product_doctype(doctype_name: str):
	"""Called from a product's before_uninstall hook only. Not called as
	part of normal operation — a doctype's product registration is meant
	to be immutable for the life of the product's installation."""
	existing_name = frappe.db.exists("QTT Product DocType", {"doctype_name": doctype_name})
	if existing_name:
		frappe.delete_doc("QTT Product DocType", existing_name, ignore_permissions=True)
		_invalidate_doctype_registry_cache()


def resolve_product_for_doctype(doctype_name: str) -> str | None:
	"""The lookup the security engine's require_document_tenant_and_product
	(Phase 3) is built on: which product does `doctype_name` belong to.
	Static per deploy, so aggressively cached — this is precisely the kind
	of metadata the hardening review's section 23 performance review
	flags as safe to cache (unlike an access *decision*, which is never
	cached — see tenant/context.py's module docstring).

	Uses frappe.get_all deliberately: this is internal platform
	infrastructure reading its own registry to make a routing decision,
	not tenant-owned data being handed to a caller — the same reasoning
	already applied to get_my_memberships in api/session.py.
	"""
	registry = frappe.cache().get_value(_DOCTYPE_REGISTRY_CACHE_KEY)
	if registry is None:
		rows = frappe.get_all("QTT Product DocType", fields=["doctype_name", "product"])
		registry = {row.doctype_name: row.product for row in rows}
		frappe.cache().set_value(
			_DOCTYPE_REGISTRY_CACHE_KEY, registry, expires_in_sec=_DOCTYPE_REGISTRY_CACHE_TTL
		)
	return registry.get(doctype_name)


def get_product_roles(product_key: str) -> set[str]:
	"""The set of valid product_role values for `product_key`, per that
	product's own declared role catalog — this is what Phase 3's
	QTT Product Access.validate() checks a submitted role against."""
	product = frappe.db.get_value("QTT Product", product_key, "name")
	if not product:
		return set()
	rows = frappe.get_all("QTT Product Role", filters={"parent": product_key}, fields=["role_key"])
	return {row.role_key for row in rows}


def _invalidate_doctype_registry_cache():
	frappe.cache().delete_value(_DOCTYPE_REGISTRY_CACHE_KEY)
