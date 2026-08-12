# QTT SaaS Platform

A reusable, product-agnostic multi-tenant SaaS platform — Tenant, Membership,
Product Access, Subscriptions, Entitlements, Usage, AI, Billing, Audit —
consumed by QMP LMS and future QTT products (HRMS, CRM, ...) without any of
those products' domain concepts (Course, Employee, Lead, ...) ever appearing
in this app.

This app is designed to install on the **same Frappe site, same database,
same authentication system** as `lms` — never a second site, never a second
database, never a separate service. See the six architecture documents this
implements for the full reasoning; nothing here should be read without that
context.

## Status: source-complete through Phase 3, never deployed

Exactly like `qzmaster-ai-gateway` earlier in this project, this app has
been built and validated locally (Python syntax + DocType JSON checked) but
**has not been installed on any Frappe site**, including
`app.quizmasterplus.in`. I only have REST API access to that site this
session, not bench/filesystem access — I cannot run `bench get-app`,
`bench install-app`, or `bench migrate` against it myself. Deployment is a
step for whoever has bench access to the target site.

## What's implemented (Phase 1)

| Piece | File |
|---|---|
| App scaffold, hooks.py | `qtt_platform/hooks.py` |
| `QTT Tenant` DocType | `qtt_platform/qtt_platform/doctype/qtt_tenant/` |
| `QTT Tenant Membership` DocType | `qtt_platform/qtt_platform/doctype/qtt_tenant_membership/` |
| Tenant-level authorization guards (`require_tenant_membership`, `require_tenant_role`, `require_platform_owner`) | `qtt_platform/tenant/guards.py` |
| Server-side active-tenant session model (`resolve_active_tenant`, `switch_tenant`) | `qtt_platform/tenant/context.py` |
| Bootstrap session API (`create_tenant`, `switch_tenant`, `get_my_memberships`, `get_active_tenant`) | `qtt_platform/api/session.py` |
| DB-level `(user, tenant)` uniqueness patch | `qtt_platform/patches/v0_1/add_tenant_membership_unique_constraint.py` |

Every function that touches tenant/membership data re-validates against the
live database on every call — nothing about *whether access is valid* is
cached, only *which tenant is currently selected* is (see the module
docstring in `tenant/context.py`). This matches the hardening review's
section 6 requirement precisely: a revoked membership or a suspended tenant
locks out access on the very next request, regardless of any cached state.

## What's implemented (Phase 2 — added this pass)

| Piece | File |
|---|---|
| `QTT Product` DocType (+ `QTT Product Role` child table) | `qtt_platform/qtt_platform/doctype/qtt_product/`, `.../qtt_product_role/` |
| `QTT Product DocType` — the static doctype→product registry | `qtt_platform/qtt_platform/doctype/qtt_product_doctype/` |
| Registration functions (`register_product`, `register_product_doctype`, `unregister_product_doctype`, `resolve_product_for_doctype`, `get_product_roles`) | `qtt_platform/product/registry.py` |
| Public product catalog endpoint (`list_available_products`) | `qtt_platform/api/product.py` |

Two deliberate hardening decisions carried over from the review, made
concrete in code:

- **`QTT Product DocType` grants no write/create/delete DocPerm to any
  role at all** — not even System Manager (see its `.json` permissions
  array). Every row is written by `registry.py`'s functions with
  `ignore_permissions=True`, callable only from trusted Python (a
  product's own install hook), never from a whitelisted REST endpoint.
  There is no `@frappe.whitelist()` anywhere in `registry.py`.
- **`register_product_doctype` refuses to silently move a doctype from
  one product to another**, even when called from trusted code — it
  throws unless the existing registration is deleted first. This is the
  literal fix for the "could a malicious actor repoint an LMS doctype at
  HRMS" question the hardening review posed in section 3.

## What's implemented (Phase 3 — added this pass)

| Piece | File |
|---|---|
| `QTT Product Access` DocType — the Membership × Product × Role join | `qtt_platform/qtt_platform/doctype/qtt_product_access/` |
| DB-level `(membership, product)` unique constraint + `(tenant, product)` / `(tenant, product, status)` indexes | `qtt_platform/patches/v0_2/add_product_access_constraints.py` |
| Product-level authorization guards (`require_product_access`, `require_product_role`, `has_product_access`) | `qtt_platform/product/guards.py` |
| Cross-cutting document security (`resolve_tenant_for_doc`, `require_document_tenant_and_product`, `require_same_tenant_reference`, `assert_tenant_access`) | `qtt_platform/document_security.py` |
| Whitelisted product-access management (`grant_product_access`, `revoke_product_access`, `change_product_role`, `get_my_product_access`) | `qtt_platform/api/product_access.py` |

This completes the full authorization engine originally specified across
the six architecture documents — all ten functions now exist:
`resolve_active_tenant`, `require_tenant_membership`, `require_tenant_role`
(tenant/), `require_product_access`, `require_product_role`,
`has_product_access` (product/), `resolve_tenant_for_doc`,
`require_document_tenant_and_product`, `require_same_tenant_reference`,
`assert_tenant_access` (document_security.py), plus
`resolve_product_for_doctype` (product/registry.py, Phase 2).

Two things worth calling out:

- **`QTT Product Access.validate()` implements the hardening review's
  section 7 cross-reference fix directly** — `tenant` is always
  overwritten from the referenced membership, never trusted from the
  caller, and `product_role` is checked against the product's own
  declared catalog rather than any platform-hardcoded list.
- **`require_product_access` treats a removed/suspended Tenant Membership
  as implicitly voiding every Product Access grant it owns** — no
  cascade-delete needed when a membership is removed, per the hardening
  review's section 22 failure-mode design.
- **`resolve_tenant_for_doc` intentionally implements only the
  direct-field case in Phase 3.** The parent-walk case for hook-only
  doctypes (needed once LMS integration registers doctypes like Course
  Chapter that resolve tenant via a parent Link rather than their own
  field) is added in Phase 10 when there's a real doctype to walk to —
  not guessed at now.

## What's deliberately NOT here yet

Per the implementation order in the hardening review (section 27) and the
platform specification (section 32), later phases add:

- **Phase 4** — `QTT Plan`, `QTT Product Subscription`,
  `QTT Subscription Item`, `QTT Tenant Product Subscription Pointer` (the
  hardening review's DB-constraint fix for subscription concurrency)
- **Phase 5** — the entitlement engine (`get_entitlements`, `check_limit`,
  `can_i`)
- **Phase 6** — the usage engine, with resolvers registered via
  `hooks.py` (`usage_resolvers = {...}`) — **never** a DocType field, per
  the hardening review's section 2 fix for the arbitrary-import risk that
  design would otherwise create
- **Phase 7** — `permission_query_conditions` / `has_permission` /
  `validate` hooks, both against this app's own doctypes and (later)
  against LMS doctypes
- **Phase 8** — the AI platform: the ported `AiGateway`/`AiProvider`
  design from `qzmaster-ai-gateway`, `QTT AI Provider`, `QTT AI Model`,
  `QTT AI Credit Ledger`, `QTT AI Usage Record`, and
  `QTT Tenant Product Wallet` (the hardening review's atomic-deduction fix
  for AI credit concurrency)
- **Phase 9** — billing: `QTT Invoice`, `QTT Payment`,
  `QTT Payment Transaction`, the Razorpay adapter, the webhook handler
- **Phase 10** — QMP LMS integration: the 12 `tenant` Custom Fields on
  LMS's anchor/denormalized doctypes, LMS's own product registration

Nothing in Phase 1 references any doctype or function from a later phase —
`hooks.py` documents this explicitly rather than stubbing ahead.

## Deployment (for whoever has bench access)

```bash
# from the bench directory
bench get-app qtt_platform /path/to/this/qtt_platform
bench --site app.quizmasterplus.in install-app qtt_platform
bench --site app.quizmasterplus.in migrate
```

`install-app` creates the two DocTypes; `migrate` additionally runs the
`add_tenant_membership_unique_constraint` patch. Confirm both DocTypes and
the unique index exist afterward before treating Phase 1 as live.

## Testing before installing on the real site

This app has not been tested against a live Frappe instance (no bench
access, as above). Before installing on `app.quizmasterplus.in`, install it
on a disposable/staging site first and exercise at minimum:

- `create_tenant` — creates both records, activates the new tenant, and
  rolls back cleanly (no orphaned `QTT Tenant` row) if the membership
  insert is made to fail artificially
- `switch_tenant` — succeeds for a real membership, fails with
  `PermissionError` for a tenant the user has no membership in
- `get_my_memberships` — returns only the calling user's own rows
- The `(user, tenant)` unique constraint — attempting to insert a second
  membership for the same pair fails at the database level, not only via
  the friendly `validate()` message
- `register_product` — idempotent: calling it twice with the same
  `product_key` updates the existing row rather than creating a duplicate
- `register_product_doctype` — registering the same doctype under the
  same product twice is a no-op; registering it under a *different*
  product raises, rather than silently moving it
- Confirm no role — including System Manager — can edit or delete a
  `QTT Product DocType` row through the Desk UI (only `read` should work)
- **Case A** (hardening review section 4): a user with active Tenant
  Membership but no Product Access attempts a product-gated action →
  `PermissionError`
- **Case B**: a user with Product Access to one product attempts an
  action gated to a different product → `PermissionError`
- **Case C**: a user whose `product_role` isn't in `allowed_roles`
  attempts a role-gated action → `PermissionError`
- Removing a Tenant Membership (status → `removed`) immediately blocks
  `require_product_access` for every product that membership had access
  to, without touching any `QTT Product Access` row directly
- `grant_product_access` with a `product_role` not in the product's own
  role catalog → rejected by `QTT Product Access.validate()`, not by the
  API layer — confirms the doctype-level guard holds even if an API
  check were ever bypassed
