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

## Status: source-complete for Phase 1, never deployed

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

## What's deliberately NOT here yet

Per the implementation order in the hardening review (section 27) and the
platform specification (section 32), later phases add:

- **Phase 2** — `QTT Product`, `QTT Product DocType` (the product registry)
- **Phase 3** — `QTT Product Access`, product-level role checks
  (`require_product_access`, `require_product_role`,
  `require_document_tenant_and_product`)
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
