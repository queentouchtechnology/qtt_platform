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

## Status: ALL 10 PHASES source-complete, never deployed

QMP LMS integration (Phase 10) is a **separate sibling project**,
`qmp_lms_bridge` — see below for why, and see that project's own README
for its full detail. This repository (`qtt_platform`) gained one small,
generic extension to support it: the parent-walk case in
`document_security.resolve_tenant_for_doc()`, deferred since Phase 3.

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

## What's implemented (Phase 4 — added this pass)

| Piece | File |
|---|---|
| `QTT Plan` (+ `QTT Plan Feature` child table) | `qtt_platform/qtt_platform/doctype/qtt_plan/`, `.../qtt_plan_feature/` |
| `QTT Product Subscription` (+ `QTT Subscription Item` child table) | `qtt_platform/qtt_platform/doctype/qtt_product_subscription/`, `.../qtt_subscription_item/` |
| `QTT Tenant Product Subscription Pointer` — the real DB-level "at most one active subscription per (tenant, product)" guarantee | `qtt_platform/qtt_platform/doctype/qtt_tenant_product_subscription_pointer/` |
| `QTT Subscription Event` — append-only, 100% system-generated | `qtt_platform/qtt_platform/doctype/qtt_subscription_event/` |
| Lifecycle service (`create_subscription`, `get_current_subscription`, `change_plan`, `cancel_subscription`, `activate_pointer`) | `qtt_platform/subscription/service.py` |
| Whitelisted, Tenant-Owner-gated API (`subscribe`, `change_plan`, `cancel`, `get_my_subscription`) | `qtt_platform/api/subscription.py` |
| `(product, plan_code)` and pointer `(tenant, product)` DB constraints | `qtt_platform/patches/v0_3/add_subscription_constraints.py` |

Three things worth calling out:

- **`activate_pointer()` refines the hardening review's own raw-SQL
  pseudocode into something more idiomatic**, while preserving the exact
  same guarantee: the create path goes through Frappe's normal
  `insert()`/`validate()` pipeline; if two concurrent callers race to
  create the *first* pointer for a `(tenant, product)`, the database's
  real unique index (not application logic) lets exactly one succeed,
  and the loser's `frappe.UniqueValidationError` is caught and retried
  as an update. Only the update path (an already-existing pointer) uses
  a plain, safe `set_value` — deliberately not wrapped in the same
  atomic machinery, because two concurrent plan changes racing there is
  a "last write wins" outcome, not a security or financial defect (the
  hardening review's section 18 note against over-applying the
  concurrency pattern where the race is low-severity).
- **A superseded subscription is never mutated** — `change_plan` creates
  a new `QTT Product Subscription` row and repoints the pointer; the old
  row keeps whatever status it had. What makes it "historical" is purely
  that the pointer no longer references it, not a status flag.
- **`QTT Plan.plan_code` is unique per-product, not globally** — `autoname`
  is `hash`, not `field:plan_code`, specifically so "Professional" can
  exist once for `QMP_LMS` and once for a future `QTT_HRMS` without a
  naming collision.

## What's implemented (Phase 5 + 6 — added this pass, together)

Shipped together deliberately: `get_entitlements()`/`check_limit()` for a
numeric feature is non-functional without a real usage-counting mechanism
to call — shipping Phase 5 alone would have meant a `check_limit` that
could never actually return `True` for anything countable. See the
`hooks.py` comment block for the same reasoning in context.

| Piece | File |
|---|---|
| `QTT Tenant Feature Override` — one-off grant/revoke, System-Manager-only | `qtt_platform/qtt_platform/doctype/qtt_tenant_feature_override/` |
| `feature_key` added to `QTT Subscription Item` — lets an add-on augment a numeric plan limit | `qtt_platform/qtt_platform/doctype/qtt_subscription_item/qtt_subscription_item.json` |
| Usage resolver registry (`get_usage_resolver`, `get_usage`) — reads `hooks.py`'s `usage_resolvers` dict, never a DocType field | `qtt_platform/usage/registry.py` |
| Entitlement engine (`get_entitlements`, `check_limit`, `is_feature_enabled`, `can_i`) | `qtt_platform/entitlement/engine.py` |
| Shared exception types (`FeatureNotConfigured`, `UsageResolutionFailed`) | `qtt_platform/exceptions.py` |
| Whitelisted `can_i` endpoint | `qtt_platform/api/entitlements.py` |

Design points worth calling out:

- **Nothing is cached** — `get_entitlements()` recomputes from the live
  subscription/plan/overrides on every call, same "never cache an access
  decision" discipline as tenant/product access checks. A plan
  downgrade takes effect on the very next call, not after some TTL.
- **A feature's numeric-vs-flag nature is never declared or guessed from
  its stored value** — it's determined by whether a usage resolver is
  *registered* for that `(product, feature_key)` pair. This sidesteps a
  real ambiguity in the spec's own `limit_value` convention (a string
  `"0"`/`"1"` could mean "a flag that's off" or "a numeric limit of
  zero") by not needing to resolve it centrally at all.
- **Every failure path in `check_limit`/`can_i` fails closed** — missing
  entitlement, unregistered resolver, or the resolver itself raising all
  result in `False`/`not allowed`, never a silent pass.
- **No product has registered a usage resolver yet** (LMS integration is
  Phase 10), so today every numeric feature_key check fails closed via
  `FeatureNotConfigured` — expected, not a bug. Flag-shaped features
  (`is_feature_enabled`) already work correctly right now, since they
  need no resolver at all.
- **`qtt_platform/usage/registry.py` flags a genuine open question**
  rather than guessing: whether `frappe.get_hooks()` returns an
  already-merged dict or a list of per-app dicts for a custom
  dict-shaped hook isn't something this session could verify empirically
  (no live Frappe instance available). The registry-building code
  handles both shapes defensively; the comment there says exactly what
  to check on first real deploy to simplify it.

## What's implemented (Phase 7 — added this pass, with an honest scope correction)

Before writing any hook registration, it's worth stating the thing that
shaped this whole phase: **every doctype shipped through Phase 6 grants no
DocPerm to any tenant-facing role at all** (System Manager only).
`has_permission`/`permission_query_conditions` hooks only ever run for a
caller who has already cleared the coarse DocPerm check for that
operation — since no tenant-facing role can clear it for anything in this
app today, registering either hook against qtt_platform's own doctypes
would be dead code, not real protection. The real protection for these
doctypes has been the whitelisted API layer all along (shipped in Phases
1/3/4/5) — this phase doesn't change that, it adds the next layer for
when it's actually needed.

| Piece | File |
|---|---|
| Generic `has_permission` handler — doctype-agnostic, real, register-ready | `qtt_platform/permissions/handlers.py` |
| Generic `stamp_tenant_before_insert` / `guard_tenant_change_before_save` handlers | same file |
| `guard_tenant_change_before_save` registered against `QTT Product Subscription` and `QTT Tenant Feature Override` | `qtt_platform/hooks.py`'s `doc_events` |

What's real and load-bearing today vs. what's infrastructure waiting for
a target:

- **A genuine gap found and fixed**: neither `QTT Product Subscription`
  nor `QTT Tenant Feature Override` previously guarded against their own
  `tenant` field being edited after creation. `QTT Product Access` needed
  no equivalent fix — its `validate()` already unconditionally re-derives
  `tenant` from the referenced membership on every save, a stronger,
  self-healing guarantee that makes a reject-and-fail check redundant.
- **`has_permission` is fully generic and real**, built on
  `document_security.require_document_tenant_and_product`, but has **zero
  registrations** — there's no doctype in this app yet where it would do
  anything a whitelisted method doesn't already do. It becomes load-bearing
  the moment a doctype exists with broader DocPerm needing tenant/product
  narrowing on top — exactly LMS's shape (Phase 10).
- **`permission_query_conditions` was deliberately NOT implemented
  generically.** Its required shape is a raw SQL WHERE-clause fragment,
  inherently doctype-specific (it has to name a real table/column). Writing
  one now for a doctype that doesn't exist would be exactly the kind of
  guessed API this project has avoided throughout — see the comment block
  in `handlers.py` for what Phase 10 needs to add instead.
- **`stamp_tenant_before_insert` is built but also not registered
  anywhere** — every tenant-scoped doctype so far is created by trusted
  service code that already receives `tenant` as an explicit,
  pre-validated parameter, not by a generic end-user-facing create flow.
  Stamping from session state would actually be *wrong* for those call
  sites. It's ready for the first product (LMS) whose create flow needs it.

## What's implemented (Phase 8 — added this pass, the biggest one yet)

| Piece | File |
|---|---|
| AI core — request/response, provider interface, registry, task→model routing, the gateway (retry + fallback) | `qtt_platform/ai/core/` |
| Providers — Mock (real), DeepSeek/OpenAI/OpenRouter (real, OpenAI-compatible), Gemini/Anthropic (registered stubs) | `qtt_platform/ai/providers/` |
| `QTT AI Provider` / `QTT AI Model` — config + secrets, System-Manager-only | `qtt_platform/qtt_platform/doctype/qtt_ai_provider/`, `.../qtt_ai_model/` |
| `QTT AI Credit Ledger` / `QTT AI Usage Record` — append-only, 100% system-generated | `.../qtt_ai_credit_ledger/`, `.../qtt_ai_usage_record/` |
| `QTT Tenant Product Wallet` — the hardening review's section 8 concurrency fix | `.../qtt_tenant_product_wallet/` |
| Credit / cost / usage services | `qtt_platform/ai/services/` |
| Top-level orchestration (`generate_and_track`) | `qtt_platform/ai/service.py` |
| Whitelisted balance-check endpoint | `qtt_platform/api/ai.py` |

This is a genuine port of `qzmaster-ai-gateway` (the Node service retired
in favor of this single-application design), not a rewrite from a blank
page — the retry/fallback algorithm, the provider interface shape, and
the cost/credit separation all carry over. What changed structurally:

- **Routing now reads `QTT AI Model`, not static env config** — the one
  place this port is a genuine improvement: changing which model handles
  a task, or updating pricing, is a Desk UI edit now, not a code deploy.
- **Provider HTTP calls are synchronous** (`requests`, not `fetch`/`await`)
  — Frappe whitelisted methods run in a WSGI worker, not an event loop.
  Named as an open capacity question, not silently accepted: see
  `hooks.py`'s own comment and the single-application specification's
  prior note on this.
- **`exceptions.py` is flagged as a reconstruction, not a byte-exact
  port** — this session read `ai-gateway.ts` and `ai-provider.ts` in
  detail earlier, but not `ai-exceptions.ts` itself; the shape here
  (`is_transient`, `is_fallback_eligible`) is inferred from how the
  gateway actually uses those fields, which is enough to get the
  retry/fallback logic right, but is called out honestly rather than
  presented as a confirmed match.
- **The credit-concurrency fix, concretely**: `deduct_credits()` does one
  atomic `UPDATE ... WHERE balance >= amount` against `QTT Tenant Product
  Wallet` — the exact same pattern already proven for subscriptions in
  Phase 4, applied here to the exact 100/80/80 overdraft scenario the
  hardening review described. The ledger stays the authoritative history;
  the wallet is a concurrency-control cache, kept consistent via a
  `reconcile_wallet()` safety net (not yet wired to a scheduled job — see
  below).
- **No whitelisted "generate" endpoint exists.** `api/ai.py` exposes only
  a balance check. Building a generic AI-generation endpoint in the
  platform would mean either exposing raw prompt construction to Flutter
  (a real security/cost-control problem) or inventing a fake feature to
  demonstrate it against — neither is real work. The first real caller is
  Phase 10's LMS integration.
- **`reconcile_wallet()` is built but not scheduled** — no
  `scheduler_events` convention exists in this app yet; wiring it into a
  real cron is left for Phase 9, which has its own billing-reconciliation
  job needs to establish that convention alongside.

## What's implemented (Phase 9 — added this pass)

| Piece | File |
|---|---|
| `QTT Payment Gateway Config` — secrets via Password fieldtype | `qtt_platform/qtt_platform/doctype/qtt_payment_gateway_config/` |
| `QTT Invoice` (+ `QTT Invoice Item`) — multi-product consolidated billing | `.../qtt_invoice/`, `.../qtt_invoice_item/` |
| `QTT Payment` (append-only) / `QTT Payment Transaction` (raw, fully locked) | `.../qtt_payment/`, `.../qtt_payment_transaction/` |
| Gateway interface + Razorpay adapter (real HMAC signature verification) | `qtt_platform/billing/gateways/` |
| Billing lifecycle service + reconciliation | `qtt_platform/billing/service.py` |
| Whitelisted API + the one `allow_guest=True` webhook receiver in this app | `qtt_platform/api/billing.py` |
| **Gap-fill**: `QTT Audit Log` + `write_audit_event()`, wired into all 5 previously-deferred `TODO(audit)` comments across Phases 1/3/4/9 | `.../qtt_audit_log/`, `qtt_platform/audit.py` |

Worth calling out:

- **No client-controlled amount, concretely**: `create_payment_order()`
  reads `invoice.amount`/`invoice.currency` from the database — there is
  no code path anywhere in `billing/service.py` that accepts an amount
  from a caller for a real charge, closing the hardening review section
  10's explicit vulnerability.
- **The Razorpay adapter is real, correct code, not tested against a real
  account.** Built from Razorpay's publicly documented Orders API and
  webhook conventions (Basic Auth, amounts in paise, HMAC-SHA256 webhook
  signatures) — the same general-API-knowledge basis used for the
  DeepSeek/OpenAI provider clients in Phase 8. Signature verification
  itself (`hmac.compare_digest`) is standard, correct cryptographic
  practice. What's genuinely unverified: the exact webhook payload field
  nesting, since no Razorpay sandbox account was available this session
  — flagged directly in `razorpay_gateway.py`'s docstring, not glossed
  over.
- **`QTT Audit Log` was a real gap, not a planned deliverable that
  happened to land here.** Every architecture document specified it; no
  phase breakdown ever scheduled building it. Found and closed while
  writing this phase's own webhook-rejection audit event — rather than
  add a 6th `TODO`, all 5 pre-existing ones got wired up for real.
- **`reconcile_payments()`** (the recoverable-state mechanism from the
  hardening review section 24) and Phase 8's `reconcile_wallet()` are
  both built but neither is registered as a scheduled job — no
  `scheduler_events` convention exists in this app yet. Deliberately not
  invented for one job in isolation; both are ready the moment that
  convention is established.

## What's implemented (Phase 10 — QMP LMS integration, in a sibling project)

Phase 10 is **`qmp_lms_bridge`**, a separate app in its own repository —
not part of this one. Full detail, including the architectural reasoning
for why it has to be a third app, lives in that project's own README.
What changed *here*, in `qtt_platform` itself, to support it:

- **`document_security.resolve_tenant_for_doc()` gained the parent-walk
  case it deferred back in Phase 3** — both a static form
  (`tenant_parent_links`, e.g. `{"Course Chapter": ("course", "LMS Course")}`)
  and a dynamic/polymorphic form (`tenant_dynamic_parent_links`, for a
  `reference_doctype`/`reference_docname`-style field pair like
  `Discussion Topic`'s). Both registries are hooks.py dicts populated by
  products — `qtt_platform` declares both empty, the same pattern already
  established for `usage_resolvers`.
- **Nothing else changed.** `has_permission` (built generic in Phase 7,
  sitting unregistered for lack of a real target) needed zero new code —
  `qmp_lms_bridge` registers the exact same function directly against
  LMS's 4 hook-only doctypes. This is the literal payoff of building that
  function generically three phases before it had anywhere to go: Phase
  10 really did turn out to be "wire up Custom Fields and hooks.py
  registrations only," exactly as Phase 1's very first `hooks.py` comment
  predicted it would be.

Every one of the six architecture documents this project implements is
now fully realized in source code — nothing left deferred to "a later
phase." What remains is genuinely external: bench access to actually
install any of this, real credentials for the AI/payment providers, and
the confidence-flagged LMS field names in `qmp_lms_bridge` that should be
confirmed against live schema before this governs real tenant data.

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
- **Subscription concurrency** (hardening review section 9, the actual
  scenario it was written to fix): fire two concurrent `subscribe` calls
  for the same `(tenant, product)` with no existing subscription — exactly
  one should succeed in creating the pointer; the other should complete
  via the `UniqueValidationError` → retry-as-update path in
  `activate_pointer`, never end up with two pointer rows
- `change_plan` — confirms the old `QTT Product Subscription` row is
  untouched (same status, same fields) and only the pointer moved
- A plan belonging to a different product than the subscription it's
  attached to → rejected by `QTT Product Subscription.validate()`
- Attempting to create a second `QTT Tenant Product Subscription Pointer`
  row for the same `(tenant, product)` directly (bypassing the service
  layer) fails at the database constraint, not only in application code
- `get_entitlements` on a tenant with no open subscription for that
  product → `{}`, and `check_limit`/`is_feature_enabled` against any
  `feature_key` on that empty map → `False`
- A `QTT Subscription Item` with `feature_key="max_instructors"` and
  `quantity=5` → `get_entitlements()["max_instructors"]` is the plan's
  base limit plus 5
- An override with a past `expires_on` is ignored by `get_entitlements`
  — confirms expired overrides don't silently keep applying
- `check_limit` for a `feature_key` with no registered usage resolver →
  `False` via the `FeatureNotConfigured` fail-closed path, not an
  unhandled exception
- Confirm `frappe.get_hooks("usage_resolvers")`'s actual return shape on
  first real deploy (see the comment in `usage/registry.py`) and
  simplify that function once confirmed
- As System Manager, edit an existing `QTT Product Subscription`'s
  `tenant` field directly through the Desk UI → rejected by
  `guard_tenant_change_before_save`; confirm the same edit succeeds only
  when performed by a session actually holding the System Manager Frappe
  Role (the one legitimate escape hatch the guard allows)
- Confirm `stamp_tenant_before_insert`/`has_permission` behave correctly
  in isolation (unit-testable without a real tenant-scoped doctype to
  register them against, since both are pure functions of a passed-in
  `doc`) — real end-to-end registration testing waits for Phase 10
- **AI credit concurrency** (hardening review section 8, the exact
  100/80/80 scenario): grant a tenant 100 AI credits, fire two concurrent
  `deduct_credits(..., amount=80, ...)` calls — exactly one should
  succeed (balance → 20), the other must observe zero affected rows and
  return `{"ok": False, "reason": "insufficient_credits"}`, never a
  negative balance
- `deduct_credits`/`refund_credits` called twice with the same
  `reference` → the second call is a no-op (`already_processed: True` /
  silently returns), confirming idempotency under client retry
- `MockProvider` end-to-end through `AiGateway` — confirms routing,
  retry, and the response shape without needing any real API key
- Register a `QTT AI Model` with `default_for_task="quiz_generation"`
  twice (two different models) → the second insert is rejected by
  `QTT AI Model.validate()`'s ambiguous-routing guard
- Configure two `QTT AI Provider` rows with `is_fallback=1` → rejected
  by `QTT AI Provider.validate()`
- `reconcile_wallet()` after manually corrupting a wallet's `balance` via
  direct SQL → confirms it's corrected back to `SUM(ledger.amount)`
- Confirm `get_decrypted_password`'s exact import path/signature against
  the real Frappe version on first deploy — referenced throughout
  `qtt_platform/ai/providers/openai_compatible_provider.py` as the
  standard mechanism but not executable-verified this session (no live
  Frappe instance available)
- **Webhook signature rejection**: send `razorpay_webhook` a payload with
  an invalid/missing signature → rejected before any DB write, a
  `security_violation` audit event recorded, no `QTT Payment Transaction`
  status changed
- **Webhook idempotency**: replay the identical valid webhook payload
  twice → the second call returns `already_processed: True`, no second
  `QTT Payment` row created
- Attempt `create_payment_order` with a fabricated `amount` anywhere in
  the request (there shouldn't be a parameter for it at all) — confirms
  by construction that the server-side invoice amount is the only source
- `refund_payment` called twice against the same original payment →
  returns the same existing refund row both times, never creates two
  - Register a real Razorpay sandbox account before going live and run
  one real `create_order` + webhook round trip — the one thing this
  phase genuinely could not verify without external credentials
