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

## Status: ALL 10 PHASES source-complete, never deployed — SaaS Customer Lifecycle build underway (Phase A done)

A second, lettered phase sequence (A, B, C, ...) is now layered on top of
the 10 numbered phases below — the end-to-end customer signup → trial →
paid → upgrade/downgrade → cancellation lifecycle, phase-gated the same
way the numbered phases were. See "What's implemented (SaaS Lifecycle
Phase A)" further down for the first of these.

**Phase B (the 3 SaaS plans + entitlement limits) has no code in this
repository at all** — it's entirely in `qmp_lms_bridge/plans.py`, since
which plans exist and what they cost is QMP_LMS business data, not
generic platform infrastructure. See that project's own README for the
full plan/entitlement table.

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

## What's implemented (SaaS Lifecycle Phase A — added this pass)

The first phase of the customer-facing signup/onboarding lifecycle,
built strictly on top of the 10 numbered phases above — no existing
DocType, guard function, or engine was changed. Two new files:

- **`qtt_platform/errors.py`** — a small `{"success": bool, ...}`
  response envelope (`ok()`/`fail()`) and a `QttApiError(code, message)`
  exception, scoped ONLY to the new `api/saas.py` module. Every other
  existing whitelisted method in this app still raises
  `frappe.PermissionError`/`frappe.ValidationError` directly and relies
  on Frappe's own non-2xx + `exc_type` response — unchanged, still
  authoritative everywhere else.
- **`qtt_platform/api/saas.py`** — `signup()` (the only other
  `allow_guest=True` endpoint in this app besides the Razorpay webhook)
  and `get_plans()`. `signup()` composes, in one request transaction (no
  `frappe.db.commit()` anywhere in this module — same reliance on
  Frappe's own commit-at-end-of-request/rollback-on-exception behaviour
  `api/session.py::create_tenant()` already depended on):

  Frappe `User` → `QTT Tenant` (status=`trial`) → `QTT Tenant Membership`
  (`tenant_role=Tenant Owner`) →
  `qtt_platform.subscription.service.create_subscription()` (reused,
  unmodified — trial length comes from the plan's own `trial_days`) →
  `QTT Product Access` (`product_role=Manager`).

  **Role decision, explicit and deliberate**: QMP_LMS's real product
  role catalog (registered by `qmp_lms_bridge/install.py`) is
  `Instructor / Manager / Staff / Student` — no `Owner`, no
  `administrator`. Nothing was renamed or added. Signup grants the new
  Tenant Owner **`Manager`** product access, not `Owner` — the platform's
  Tenant Owner (billing/membership/tenant governance) and QMP_LMS's
  Manager (product-level administration) are deliberately different
  roles on different doctypes; `_INITIAL_PRODUCT_ROLE = {"QMP_LMS":
  "Manager"}` lives in `api/saas.py`, not in `qtt_platform`'s generic
  product registry, which still knows nothing product-specific.

  Every failure mode `signup()` checks for itself returns a clean code
  via the new envelope: `VALIDATION_ERROR`, `INVALID_EMAIL`,
  `WEAK_PASSWORD`, `DUPLICATE_EMAIL`, `INVALID_PRODUCT`, `INVALID_PLAN`,
  `INVALID_COUNTRY`, `INVALID_LANGUAGE`; anything unexpected is logged
  server-side (`frappe.log_error`) and reported only as `INTERNAL_ERROR`
  — no stack trace crosses the API boundary. Password strength is
  enforced by Frappe's own `User.password_strength_test()` (active only
  if the site's System Settings → `enable_password_policy` is on — not
  changed here); hashing is Frappe's own `_update_password()`, triggered
  by setting `new_password` before insert — nothing custom.

  Two concurrency-relevant retry behaviours, both real, both tested:
  duplicate-email races are caught as `frappe.DuplicateEntryError` on
  `User.name` (the email itself is the primary key) and mapped to
  `DUPLICATE_EMAIL`; slug collisions on `QTT Tenant.slug` (unique) are
  retried up to 5 times with an incrementing suffix before failing
  closed with `INTERNAL_ERROR`.

  **Deliberately NOT done in Phase A** (per the phase brief): no
  Razorpay call of any kind — `create_subscription()` only ever writes
  local rows; a genuinely external Razorpay customer/subscription is
  Phase C. `signup()` also does not log the new user in — the client
  calls Frappe's standard `/api/method/login` afterward with the same
  credentials; building session-establishment inside a guest endpoint
  was judged out of scope for this phase rather than guessed at.

## What's implemented (SaaS Lifecycle Phase C — Razorpay Subscriptions)

Extends the existing Orders-only Razorpay adapter with a second,
optional capability — the Orders implementation (`create_order`,
`verify_webhook_signature`, `parse_webhook_event`) is **completely
unchanged**, still the entire contract for `PaymentGateway`.

- **New fields, additive only, nothing existing removed or renamed**:
  `QTT Plan.razorpay_plan_id`, `QTT Payment Gateway Config.mode`
  (test/live, descriptive-only — Razorpay's API distinguishes test/live
  purely by which key pair is used, not a separate endpoint, so nothing
  branches on this field), `QTT Tenant.razorpay_customer_id`,
  `QTT Product Subscription.{razorpay_subscription_id, trial_start,
  trial_end, cancellation_requested_at, cancel_reason, cancelled_at,
  effective_end_date}`. `subscription/service.py::create_subscription()`
  (unchanged otherwise) now also populates `trial_start`/`trial_end`
  when a subscription starts `trialing`.
- **`billing/gateways/base.py`** gained a second, optional ABC —
  `SubscriptionCapableGateway` (`create_plan`, `create_subscription`,
  `cancel_subscription`, `parse_subscription_webhook_event`) — kept
  deliberately separate from `PaymentGateway` so a gateway that only
  does one-time orders is never forced to implement subscription
  methods it doesn't have.
- **`RazorpayGateway` now implements both** `PaymentGateway` and
  `SubscriptionCapableGateway`. The Subscriptions API shape
  (`POST /v1/plans`, `POST /v1/subscriptions`, `POST
  /v1/subscriptions/:id/cancel`, and the `subscription.*` webhook event
  names/payload shape) was fetched fresh from Razorpay's own current API
  documentation while building this phase — not from memory — given how
  costly a wrong field name would be here. One finding from that lookup
  that changed the design from what was originally assumed: **Razorpay's
  Create Subscription request does not accept a `customer_id`** — the
  customer is captured automatically once they complete checkout
  authorization. `QTT Tenant.razorpay_customer_id` is therefore NOT
  populated by pre-creating a Razorpay Customer at subscription time (an
  earlier draft of this phase would have done exactly that, and the
  created customer would have gone unused) — it's backfilled from the
  first subscription webhook that reports a `customer_id`, which is
  Phase D's job (`parse_subscription_webhook_event()` already surfaces
  it; nothing writes it yet).
- **`billing/service.py`** gained three new functions, all additive —
  every existing Orders/Invoice/Payment function is untouched:
  - `ensure_razorpay_plan(plan_name)` — reuse-first (Part 12): returns
    the existing `razorpay_plan_id` if set, otherwise creates the
    Razorpay Plan exactly once and stores it. Safe to call on every
    subscription creation for the same `QTT Plan`.
  - `create_razorpay_subscription(subscription_name)` — links an
    already-created LOCAL `QTT Product Subscription`
    (`subscription/service.py::create_subscription()`, unmodified) to a
    NEW external Razorpay subscription. If the local subscription is
    `trialing`, its `trial_end` becomes Razorpay's `start_at` (Unix
    timestamp) — the trial mechanism: the customer authorizes now, the
    first real charge happens at `trial_end`. Refuses to double-link an
    already-linked subscription.
  - `cancel_razorpay_subscription(subscription_name)` — cancels the
    linked external subscription; a safe no-op (not an error) if the
    local subscription was never linked to Razorpay at all.
  - Deliberately **not** included this phase: webhook event
    *processing* / the trial→active→past_due→suspended state machine —
    that's Phase D's explicit scope.  `_UNBOUNDED_TOTAL_COUNT = 120`
    (10 years of monthly cycles) is this phase's stated, deliberate
    stand-in for "recurring until cancelled" — Razorpay requires either
    `total_count` or `end_at` to bound every subscription; there is no
    "forever" option, and this app never lets the count run out in
    practice since cancellation is always driven by
    `cancel_razorpay_subscription()`.
- Never fakes success anywhere — every function above either returns a
  real gateway response (or, in tests, a response from a
  `spec=SubscriptionCapableGateway` mock standing in for one) or raises.

## What's implemented (SaaS Lifecycle Phase D — webhook, state machine, reconciliation)

**New DocType**: `QTT Webhook Event` — the idempotency ledger for
subscription lifecycle webhooks, keyed on Razorpay's `X-Razorpay-Event-Id`
header (confirmed unique-per-delivery against Razorpay's own webhook
docs — not guessed). Deliberately separate from `QTT Payment
Transaction`, which stays the idempotency mechanism for the existing
Orders webhook flow, unchanged — a bare lifecycle event like
`subscription.halted` often has no payment at all, so reusing a
payment-shaped doctype for it would be a conflation. Same
insert-then-catch-`UniqueValidationError` concurrency pattern already
established by `QTT Tenant Product Subscription Pointer`. New patch
`v0_7` adds the supporting index (`gateway_event_id`'s own uniqueness
comes free from its `"unique": 1` in the JSON, same as `QTT Payment
Transaction.gateway_reference` — no patch needed for that part).

**`status` gained a 5th value**: `"suspended"` (was `trialing/active/
past_due/cancelled`) — the terminal state after Razorpay's own
retry/grace period is exhausted, distinct from `past_due` (still
retrying).

**`billing/service.py::process_webhook()`** now dispatches by event-name
prefix — Razorpay delivers both one-time-payment events and
`subscription.*` events to the same URL. The existing order/payment
logic was extracted verbatim into `_process_order_webhook()`, not
rewritten; a payment-event webhook takes the exact same path it always
did.

**The subscription state machine** (`_SUBSCRIPTION_EVENT_TO_LOCAL_STATUS`)
is this project's own deliberate, documented mapping — Razorpay
publishes no canonical "map our events to your states" table:

| Razorpay event | Local status |
|---|---|
| `subscription.authenticated` | *(no change — customer_id backfill only)* |
| `subscription.activated` / `subscription.charged` / `subscription.resumed` | `active` |
| `subscription.pending` | `past_due` |
| `subscription.halted` | `suspended` |
| `subscription.paused` | `suspended` *(no separate local "paused" state)* |
| `subscription.cancelled` / `subscription.completed` | `cancelled` |
| `subscription.updated` | *(no change — informational)* |

`subscription.pending` = mid-retry inside Razorpay's own grace period;
`subscription.halted` = grace period exhausted — this maps Part 25's
"grace period" onto Razorpay's real, confirmed retry semantics rather
than inventing a separate local timer.

- `_record_webhook_event_once()` — the ledger insert; returns whether
  this is a fresh delivery.
- `_apply_subscription_status_transition()` — the ONE place that writes
  `QTT Product Subscription.status` and audits it; a no-op if the target
  status already matches (no duplicate audit noise on a redundant
  confirmation). Used by both the webhook handler and reconciliation.
- `_backfill_tenant_razorpay_customer_id()` — where `QTT Tenant.
  razorpay_customer_id` (Phase C field, deliberately left unset at
  subscription-creation time) actually gets set: the first webhook that
  reports one.
- `_record_subscription_charge()` — a successful `subscription.charged`
  reuses the existing `QTT Invoice`/`QTT Payment`/`QTT Payment
  Transaction` architecture exactly as the Orders flow does (Part 19/20),
  idempotent on the gateway payment id.
- **`reconcile_subscriptions()`** (Part 42) — for every locally "open"
  subscription linked to Razorpay, fetches Razorpay's own current status
  (`RazorpayGateway.fetch_subscription_status()`, `GET
  /v1/subscriptions/:id`, confirmed against Razorpay's docs) and repairs
  drift via the SAME `_apply_subscription_status_transition()` the
  webhook handler uses — one mapping, two entry points. A fetch failure
  for one subscription is logged and skipped, never raised — one
  unreachable subscription doesn't abort reconciling the rest. Not
  registered as a scheduled job yet — that's Phase I.
- **`subscription/service.py::cancel_subscription()`** (unchanged
  function, extended signature) now also records
  `cancellation_requested_at`/`cancel_reason`/`effective_end_date`
  (Phase C fields) and, for an immediate cancellation only, `cancelled_at`
  — for `at_period_end=True` (the default), `cancelled_at` is
  deliberately left unset until Phase I's scheduled sweep actually flips
  `status` to `cancelled` once `current_period_end` passes.
- **`api/subscription.py::cancel()`** now also calls
  `billing.service.cancel_razorpay_subscription()` for the linked
  external subscription. The local cancellation is NOT rolled back if
  the external call fails — the failure is logged
  (`frappe.log_error`), and `reconcile_subscriptions()` is the stated
  safety net for the local/external mismatch this could leave behind.

## What's implemented (SaaS Lifecycle Phase E — plan upgrade/downgrade)

**No new DocType.** Two new fields on the existing `QTT Product
Subscription` (`scheduled_plan`, `scheduled_plan_effective_date`) —
inspected first whether the existing model could represent "a downgrade
is pending" (it couldn't: nothing on `QTT Plan`/`QTT Subscription
Item`/`QTT Tenant Product Subscription Pointer` records a *future* plan)
before adding them, mirroring the exact pattern `cancel_at_period_end`
already established for deferred cancellation.

**Plan comparison**: `base_price` ascending, never a plan-name/plan-code
string comparison anywhere. This is not a new decision — `qmp_lms_bridge/
plans.py` (Phase B) already documented base_price as the architecture's
own ordering mechanism when it deliberately chose not to add a
`plan_order` field; Phase E reuses that decision rather than re-deciding
it.

**Upgrade — immediate** (`api/subscription.py::change_plan()` →
`_apply_upgrade()`): Razorpay is synced FIRST
(`billing.service.sync_razorpay_plan_change(..., immediate=True)` →
`RazorpayGateway.update_subscription_plan()`, `PATCH
/v1/subscriptions/:id` with `schedule_change_at="now"`, confirmed
against Razorpay's current API docs) — only on success does the LOCAL
`subscription/service.py::change_plan()` run (unchanged function,
reused exactly as Phase 4 built it: creates a new current row, repoints
the existing pointer, writes the existing `upgraded` `QTT Subscription
Event`). If the Razorpay call fails, the local plan is never touched —
`PLAN_CHANGE_FAILED` is returned and a `plan_change_failed` audit event
is written.

**A real gap this phase found and fixed in `change_plan()` itself**: the
new row it creates now carries forward `razorpay_subscription_id`,
`trial_start`, `trial_end`, and `status` from the row it supersedes.
Previously (Phase 4-era code, never exercised by Razorpay integration
since that didn't exist until Phase C) the new row left
`razorpay_subscription_id` blank and hardcoded `status='active'` — which
would have silently orphaned the Razorpay linkage on every plan change
and silently ended an in-progress trial early. Both are fixed at the
source (`subscription/service.py::change_plan()`), not worked around in
the API layer, so every caller of `change_plan()` benefits, not just
Phase E's own.

**Downgrade — scheduled for next billing cycle** (`_schedule_downgrade()`):
same Razorpay-first ordering, with `schedule_change_at="cycle_end"` —
Razorpay's own native deferred-plan-change mechanism, not something this
app invented. Only on success are the local `scheduled_plan`/
`scheduled_plan_effective_date` fields set
(`subscription/service.py::schedule_plan_change()`, which also writes a
`plan_downgrade_scheduled` `QTT Audit Log` event — deliberately audit
log, not `QTT Subscription Event`: nothing about the subscription's
actual plan changed yet, so recording it in the doctype meant for real
plan-lifecycle transitions would misrepresent what happened). The
CURRENT plan field is never touched by scheduling — old-plan
entitlements remain in effect exactly until the scheduled date, for
free, because `qtt_platform.entitlement.engine.get_entitlements()`
still reads the unchanged `plan` field.

**Applying a scheduled downgrade** (`subscription/service.py::
apply_scheduled_plan_change()`): a no-op unless `scheduled_plan` is set
and its effective date has arrived; when due, calls the SAME
`change_plan()` upgrades use (creating a new current row, same history
pattern) and writes a `plan_downgrade_applied` audit event alongside the
`downgraded` `QTT Subscription Event` `change_plan()` itself already
writes. **Trigger**: extended the EXISTING `subscription.charged`
webhook handler (Phase D) to call this immediately after recording the
charge — a new billing cycle actually starting is exactly when a
pending downgrade should apply, per this phase's own instruction to
extend the existing webhook processor rather than build a second one.
No scheduled job was added for this (Phase I's territory, same
`reconcile_payments()`/`reconcile_subscriptions()` precedent) — in
practice this means an in-trial or already-fully-cancelled subscription
that never fires another `subscription.charged` event won't apply its
scheduled downgrade until Phase I's scheduler exists; documented as a
known limitation below, not silently accepted.

**Trial plan change**: the SAME Razorpay subscription id is reused for
every plan change (never a second Razorpay subscription — there is
structurally no code path that creates one for a plan change, upgrade
or downgrade); `trial_start`/`trial_end` are carried forward verbatim
by the `change_plan()` fix above, so the trial is never restarted or
extended. An upgrade during trial keeps `status='trialing'` on the new
row (carried forward, not hardcoded to `'active'`) — the trial
continues exactly as before, just on the new plan's entitlements.

**Cancellation interaction**: `change_plan()` checks
`cancel_at_period_end`/`cancellation_requested_at` before anything else
plan-related and returns `CANCELLATION_PENDING` — no silent state
transition. New `resume()` endpoint (Owner-only, matching `cancel()`'s
own gate) clears the local cancellation fields
(`subscription/service.py::resume_subscription()`). **Known
limitation, stated plainly**: `resume()` does not call Razorpay — no
confirmed "un-cancel a scheduled cancellation" Razorpay endpoint was
found this session, and this project does not implement unconfirmed
APIs. `reconcile_subscriptions()` (Phase D) is the stated safety net for
whatever local/external divergence this leaves if the subscription was
ever cancelled via `cancel_razorpay_subscription()` with
`cancel_at_cycle_end=True`.

**Usage over limit**: `qtt_platform.entitlement.engine.
get_over_limit_features()` (new — pure composition of
`get_entitlements()`/`get_usage()`, no new limit-comparison logic) is
checked at TWO points: a preview against the TARGET plan at request
time (`api/subscription.py::_preview_over_limit_features()`, surfaced
in the response as `usage_warning` and audited as
`plan_change_usage_exceeded` if non-empty), and implicitly, for free,
the moment a downgrade actually applies — `check_limit()` (unchanged)
naturally starts returning `False` for new creation the instant the
lower plan's entitlements take effect. Nothing is ever deleted or
auto-suspended; both checks correctly exclude flag-shaped features
(distinguishing "has a registered usage resolver" from "the stored
value happens to parse as an int," the same rule `can_i()` already
uses — a real bug caught and fixed while building this phase's own
tests, not shipped and found later).

**Concurrency**: no new locking was added, deliberately — `change_plan()`
(upgrade and applied-downgrade both go through it) already inherits
`activate_pointer()`'s existing, already-reviewed protection (a real
database unique constraint on `QTT Tenant Product Subscription
Pointer(tenant, product)`, patches/v0_3): two concurrent upgrade calls
can each insert their own new `QTT Product Subscription` row, but only
one wins the pointer, exactly the accepted "last write wins, not a
security/financial defect" reasoning that constraint's own docstring
already established. A pending downgrade schedule is a single field on
a single row (`scheduled_plan`), not a list — there is no schema shape
in which "two scheduled changes" for the same subscription can exist
simultaneously; a second `schedule_plan_change()` call before the first
applies is a benign last-write-wins field overwrite, and
`api/subscription.py`'s own `PLAN_CHANGE_ALREADY_PENDING` check is what
decides whether that overwrite is even allowed to reach that point.

**Authorization**: `change_plan()` requires Tenant Owner OR Tenant Admin
(`_PLAN_CHANGE_ROLES`, new — every other action in this file stays
Owner-only, unchanged). `require_tenant_role()` only ever reads
`QTT Tenant Membership.tenant_role` — it has no code path that looks at
`QTT Product Access.product_role` at all, so a QMP_LMS Manager/
Instructor/Staff/Student role cannot substitute for tenant billing
authorization as a structural fact, not a policy choice that could be
bypassed.

**API response envelope**: reuses `qtt_platform.errors`
(`ok()`/`fail()`/`QttApiError`, built in Phase A) — the same
`{"success": true/false, ...}` shape, extended with this phase's own
codes: `BILLING_ROLE_REQUIRED`, `PRODUCT_ACCESS_DENIED`, `INVALID_PLAN`,
`INVALID_PRODUCT`, `SUBSCRIPTION_NOT_FOUND`, `SUBSCRIPTION_CANCELLED`,
`CANCELLATION_PENDING`, `PLAN_UNCHANGED`, `PLAN_CHANGE_ALREADY_PENDING`,
`PLAN_CHANGE_FAILED`.

**A deliberate inconsistency, flagged rather than hidden**: `change_plan()`
and `resume()` resolve `tenant` from the caller's active tenant session
(`resolve_active_tenant()`), per this phase's own explicit instruction
never to accept `tenant` as a request parameter. Every other endpoint in
`api/subscription.py` (`subscribe`, `cancel`, `get_my_subscription`, all
pre-Phase-E) still takes `tenant` as an explicit parameter — safe by a
different, equally valid mechanism (`require_tenant_role` re-validates
real membership regardless of where the tenant value came from), but
genuinely a different convention now living in the same file. Not
unified in this pass — doing so would mean changing `subscribe()`/
`cancel()`'s existing signatures, which Phase E did not ask for and
which would be exactly the kind of "redo work already shipped" this
project's phase-gating exists to avoid.

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

**SaaS Lifecycle Phase A** — `python -m unittest qtt_platform.tests.test_saas_signup -v`
was actually run this pass (27 tests, all pass — pure-logic validation,
error-code mapping, slug-retry, duplicate-email-race mapping, no DB
needed). `test_saas_signup_integration.py` was written but NOT executed
(no bench). On a real site, run it (`bench --site <test-site> run-tests
--app qtt_platform --module qtt_platform.tests.test_saas_signup_integration`)
and additionally exercise:
- The full curl flow below end-to-end against a disposable site
- `signup` twice with the same email concurrently (two real parallel
  requests, not two threads in one process) → exactly one succeeds, the
  other gets a clean `DUPLICATE_EMAIL`, never a raw DB error or two
  `QTT Tenant` rows
- Confirm the granted `QTT Product Access.product_role` is exactly
  `"Manager"` and that `QTT Tenant Membership.tenant_role` is exactly
  `"Tenant Owner"` — the two must never be equal, never swapped
- Confirm no response from `signup` — success or failure — ever contains
  `password`, `new_password`, or any secret field
- With System Settings → `enable_password_policy` turned on, confirm a
  weak password is rejected with `WEAK_PASSWORD` (Phase A did not turn
  this on itself — verify against whatever the target site already has
  configured)

## Deployment — SaaS Lifecycle Phase A

No new DocType, no new patch, no schema change — `signup()`/`get_plans()`
are plain whitelisted Python functions, discovered by their dotted path.
Deploying this phase is just shipping the updated source:

```bash
cd apps/qtt_platform
git pull origin main      # or however this bench's copy of qtt_platform is updated
bench --site app.quizmasterplus.in migrate
bench restart
```

`migrate` is not strictly required (no patch was added this phase) but
costs nothing to run; `bench restart` (or a worker reload) is what
actually picks up the two new Python files.

### curl — Phase A

Requires at least one real `QTT Product` (`QMP_LMS`) and one `QTT Plan`
under it. As of Phase B, both are real and already deployed the moment
`qmp_lms_bridge` is installed/migrated — `qmp_lms_bridge/plans.py`
seeds the actual `STARTER` / `PROFESSIONAL` / `ENTERPRISE` catalog
automatically (see that project's own README). No manual plan creation
is needed anymore; the snippet below is only for a bare
`qtt_platform`-only site with `qmp_lms_bridge` not yet installed:

```python
# only if qmp_lms_bridge is not installed on this site yet
frappe.get_doc({
    "doctype": "QTT Plan", "plan_code": "STARTER", "product": "QMP_LMS",
    "display_name": "Starter", "base_price": 99, "billing_period": "monthly",
    "trial_days": 7, "is_public": 1,
}).insert(ignore_permissions=True)
frappe.db.commit()
```

**1. Get available plans (no auth required)**

```bash
curl -s -X GET \
  "https://app.quizmasterplus.in/api/method/qtt_platform.api.saas.get_plans?product_key=QMP_LMS"
```
Expected:
```json
{"message": {"success": true, "data": {"plans": [
  {"name": "<hash>", "plan_code": "STARTER", "display_name": "Starter",
   "base_price": 99.0, "billing_period": "monthly", "trial_days": 7}
]}}}
```

**2. Signup**

```bash
curl -s -X POST \
  https://app.quizmasterplus.in/api/method/qtt_platform.api.saas.signup \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Doe",
    "email": "john@example.com",
    "password": "StrongPassword123!",
    "organization_name": "John Academy",
    "country": "India",
    "language": "en",
    "product_key": "QMP_LMS",
    "plan_key": "STARTER"
  }'
```
Expected:
```json
{"message": {"success": true, "data": {
  "user": "john@example.com", "tenant": "<hash>", "tenant_name": "John Academy",
  "tenant_role": "Tenant Owner", "product": "QMP_LMS", "product_role": "Manager",
  "subscription": "<hash>", "plan": "<hash>", "plan_code": "STARTER",
  "subscription_status": "trialing", "trial_ends_on": "2026-08-19",
  "current_period_end": "2026-08-19"
}}}
```

**3. Signup again with the same email (expected failure)**

```bash
curl -s -X POST \
  https://app.quizmasterplus.in/api/method/qtt_platform.api.saas.signup \
  -H "Content-Type: application/json" \
  -d '{"full_name":"John Doe","email":"john@example.com","password":"StrongPassword123!","organization_name":"Another Org","product_key":"QMP_LMS","plan_key":"STARTER"}'
```
Expected: `{"message": {"success": false, "error": {"code": "DUPLICATE_EMAIL", "message": "..."}}}`

**4. Log in as the new user (standard Frappe auth — nothing new)**

```bash
curl -s -c cookies.txt -X POST \
  https://app.quizmasterplus.in/api/method/login \
  -H "Content-Type: application/json" \
  -d '{"usr": "john@example.com", "pwd": "StrongPassword123!"}'
```

**5. Confirm the new tenant/membership/product access, as that user**

```bash
curl -s -b cookies.txt \
  "https://app.quizmasterplus.in/api/method/qtt_platform.api.session.get_my_memberships"

curl -s -b cookies.txt \
  "https://app.quizmasterplus.in/api/method/qtt_platform.api.product_access.get_my_product_access?tenant=<tenant-from-step-2>"
```
Expected: one membership (`tenant_role: "Tenant Owner"`), one product
access row (`product: "QMP_LMS"`, `product_role: "Manager"`).

## Deployment — SaaS Lifecycle Phase C

New fields on four existing DocTypes, no new DocType, no new patch — a
plain `bench migrate` syncs the field changes (Frappe diffs each
DocType's JSON against the DB schema automatically on migrate):

```bash
cd apps/qtt_platform
git pull origin main
bench --site app.quizmasterplus.in migrate
bench restart
```

Confirm afterward: `QTT Plan`, `QTT Payment Gateway Config`,
`QTT Tenant`, and `QTT Product Subscription` each show their new
column(s) in the Desk / via `frappe.db.describe_table` — and that no
existing field on any of the four was renamed or dropped (`bench
migrate` should report 4 columns added across the run, nothing else).

## Testing — SaaS Lifecycle Phase C

`python -m unittest discover -s qtt_platform/tests -p "test_*.py"` was
actually run this pass: **42 tests, 40 pass** (13 of them new —
`test_billing_subscriptions.py`), the other 2 fail to *import* for the
same, expected, unavoidable reason as `test_saas_signup_integration.py`
in Phase A — `test_billing_subscriptions_integration.py` needs a real
`frappe` package (`frappe.tests.utils.FrappeTestCase`), not available
this session.

**A caveat about running individual test files together, not through
`discover`**: `test_saas_signup.py` and `test_billing_subscriptions.py`
each install their own independent fake `frappe`/`requests` modules at
import time. Run as `python -m unittest discover ...` (imports files in
a stable, consistent order) or one file at a time, both of which were
actually run and pass cleanly. Running them via `python -m unittest
qtt_platform.tests.test_saas_signup qtt_platform.tests.
test_billing_subscriptions` (arbitrary file order as direct arguments)
can leave `qtt_platform.audit` — cached from whichever file imported
first — bound to a stale, already-reconfigured fake from that file's
last-run test, since Python caches module imports and a later file's
fresh fake object doesn't retroactively rebind an already-imported
module's `frappe` reference. This is a property of the test harness's
module-level mocking, not a bug in `qtt_platform.audit`,
`qtt_platform.billing.service`, or any production code — `discover` is
the supported, verified way to run this suite as a whole.

Real Razorpay Subscriptions API calls were **not** made — no sandbox
account/credentials available this session, per Part 38's own
instruction to mock the gateway for automated tests and build the
credentialed integration path separately. Before this governs real
billing: register a Razorpay TEST account, configure
`QTT Payment Gateway Config` (`mode=test`), and manually run
`ensure_razorpay_plan()` / `create_razorpay_subscription()` /
`cancel_razorpay_subscription()` from `bench console` against it —
confirm the created Plan/Subscription actually appear in the Razorpay
Dashboard's test mode, and that `create_subscription()`'s `start_at`
produces the expected trial delay on a real subscription's `charge_at`.

## Deployment — SaaS Lifecycle Phase D

One new DocType this time — `bench migrate` both creates it and syncs
the `status` field's new `suspended` option:

```bash
cd apps/qtt_platform
git pull origin main
bench --site app.quizmasterplus.in migrate
bench restart
```

Confirm afterward: `QTT Webhook Event` exists as a Desk list (System
Manager only, no create/write DocPerm to anyone); `QTT Product
Subscription`'s status dropdown shows 5 options including `suspended`.

**Razorpay Dashboard configuration** (not something this code can do —
a one-time manual step wherever Razorpay credentials are configured):
point the webhook URL
(`https://app.quizmasterplus.in/api/method/qtt_platform.api.billing.razorpay_webhook`)
at BOTH the payment events already in use (`payment.captured`, ...) AND
the subscription events this phase handles: `subscription.authenticated`,
`subscription.activated`, `subscription.charged`, `subscription.pending`,
`subscription.halted`, `subscription.paused`, `subscription.resumed`,
`subscription.cancelled`, `subscription.completed`, `subscription.updated`.

## Testing — SaaS Lifecycle Phase D

`python -m unittest discover -s qtt_platform/tests -p "test_*.py"` was
actually run this pass: **64 tests, 61 pass** (34 of them in
`test_billing_subscriptions.py`, which now also covers Phase D — see
that file's own module docstring for why Phase D's tests were added
there rather than a new file: `qtt_platform.audit`/`qtt_platform.
subscription.service`/`qtt_platform.billing.service` all get bound to
whichever fake `frappe` module was live at THEIR first import, so a new
self-mocking file risks the exact cross-file staleness already
documented for Phase C — adding to the file that already establishes
the canonical fake sidesteps it entirely). The other 3 failures are the
expected, unavoidable bench-only `FrappeTestCase` import errors (one per
phase's own integration file: `test_saas_signup_integration.py`,
`test_billing_subscriptions_integration.py`,
`test_subscription_lifecycle_integration.py` — this phase's).

On a real bench, run `test_subscription_lifecycle_integration.py`
(`bench --site <test-site> run-tests --app qtt_platform --module
qtt_platform.tests.test_subscription_lifecycle_integration`) and
additionally exercise:
- **Two genuinely concurrent webhook deliveries with the same
  `X-Razorpay-Event-Id`** (real parallel HTTP requests, not two calls in
  one process) → exactly one inserts into `QTT Webhook Event` and
  processes the status transition; the other's insert hits the real DB
  unique constraint and returns `already_processed`
- Send `razorpay_webhook` a `subscription.*` payload with a valid
  signature but no `X-Razorpay-Event-Id` header → rejected, no
  `QTT Webhook Event` row, no status change
- A `subscription.charged` event with a real `payload.payment.entity` →
  confirms a `QTT Invoice` (status `paid`) and `QTT Payment` are created,
  and that redelivering the identical event is a no-op (no second
  Invoice/Payment)
- `reconcile_subscriptions()` against a subscription whose Razorpay
  status has drifted from local (e.g. manually halt one in the Razorpay
  Dashboard test mode) → local `status` corrects to `suspended`, an
  audit event is recorded with `source: "reconciliation"`
- Cancel a subscription via `api/subscription.py::cancel()` while
  temporarily misconfiguring `QTT Payment Gateway Config` (e.g. blank
  `key_secret`) → the LOCAL cancellation still succeeds
  (`cancel_at_period_end`/`cancellation_requested_at` set), the Razorpay
  call fails and is logged via `frappe.log_error`, nothing crashes back
  to the caller

Real Razorpay webhook deliveries were **not** tested — no sandbox
account/credentials available this session, consistent with every prior
phase's own honest disclosure.

## Deployment — SaaS Lifecycle Phase E

Two new fields on one existing DocType, plus a query-performance index —
`bench migrate` handles both, no new patch logic beyond the index patch
already shipped (`v0_8`):

```bash
cd apps/qtt_platform
git pull origin main
bench --site app.quizmasterplus.in migrate
bench restart
```

`bench list-apps` should show `frappe`, `lms`, `qtt_platform`,
`qmp_lms_bridge` — no new app this phase.

### curl — Phase E

```bash
# Upgrade (immediate) — tenant comes from the session, log in first
curl -s -b cookies.txt -X POST \
  https://app.quizmasterplus.in/api/method/qtt_platform.api.subscription.change_plan \
  -H "Content-Type: application/json" \
  -d '{"product": "QMP_LMS", "new_plan": "PROFESSIONAL"}'
```
Expected:
```json
{"message": {"success": true, "data": {
  "subscription": "<hash>", "old_plan": "STARTER", "new_plan": "PROFESSIONAL",
  "change_type": "upgrade", "effective": "immediate"
}}}
```

```bash
# Downgrade (scheduled)
curl -s -b cookies.txt -X POST \
  https://app.quizmasterplus.in/api/method/qtt_platform.api.subscription.change_plan \
  -H "Content-Type: application/json" \
  -d '{"product": "QMP_LMS", "new_plan": "STARTER"}'
```
Expected:
```json
{"message": {"success": true, "data": {
  "subscription": "<hash>", "old_plan": "PROFESSIONAL", "new_plan": "STARTER",
  "change_type": "downgrade", "effective": "next_billing_cycle",
  "effective_date": "2026-08-31", "usage_warning": null
}}}
```

```bash
# Trying to change plan while a cancellation is pending
curl -s -b cookies.txt -X POST \
  https://app.quizmasterplus.in/api/method/qtt_platform.api.subscription.change_plan \
  -H "Content-Type: application/json" \
  -d '{"product": "QMP_LMS", "new_plan": "PROFESSIONAL"}'
# -> {"message": {"success": false, "error": {"code": "CANCELLATION_PENDING", ...}}}

curl -s -b cookies.txt -X POST \
  https://app.quizmasterplus.in/api/method/qtt_platform.api.subscription.resume \
  -H "Content-Type: application/json" -d '{"product": "QMP_LMS"}'
# -> {"message": {"success": true, "data": {"subscription": "<hash>", "status": "active", ...}}}
```

```bash
# Extended subscription info (Phase E fields)
curl -s -b cookies.txt \
  "https://app.quizmasterplus.in/api/method/qtt_platform.api.subscription.get_my_subscription?tenant=<tenant>&product=QMP_LMS"
```

## Testing — SaaS Lifecycle Phase E

`python -m unittest discover -s qtt_platform/tests -p "test_*.py"` was
actually run this pass: **99 tests, 96 pass** (35 of them new, in
`test_billing_subscriptions.py` — the same "add to the file that
already establishes the canonical fake `frappe`" reasoning as Phase D,
now covering upgrade/downgrade/trial/cancellation/usage/concurrency/
audit end to end). The other 3 failures are the expected, unavoidable
bench-only `FrappeTestCase` import errors, one per phase's own
integration file — `test_plan_change_integration.py` is this phase's,
written but not executed (no bench).

A genuine bug this phase's OWN tests caught before it shipped: an
earlier draft of `get_over_limit_features()` / `_preview_over_limit_
features()` used `int(limit_value)` alone to decide whether a feature
was "numeric" — which incorrectly treated a flag stored as `"1"` (e.g.
`live_classes_enabled`) as if it were a real countable limit of 1.
Fixed to require a REGISTERED usage resolver first, the exact same rule
`can_i()` already used — caught by `GetOverLimitFeaturesTest` failing
before any other code depended on the wrong behavior.

On a real bench, run `test_plan_change_integration.py` (`bench --site
<test-site> run-tests --app qtt_platform --module
qtt_platform.tests.test_plan_change_integration`) and additionally
exercise:
- **Two genuinely concurrent `change_plan` upgrade requests** (real
  parallel HTTP requests) for the same tenant+product → exactly one
  `QTT Tenant Product Subscription Pointer` row exists afterward,
  pointing at whichever new `QTT Product Subscription` row won; the
  loser's row is orphaned (never referenced by the pointer, never
  granted) — expected, matches `activate_pointer()`'s own documented
  last-write-wins reasoning
- A downgrade scheduled, then upgraded instead before the effective
  date → confirm the eventual behavior matches whichever of upgrade/
  downgrade ran last (this phase's own `PLAN_CHANGE_ALREADY_PENDING`
  check blocks a second DIFFERENT scheduled downgrade, but does not
  currently special-case "upgrade over a pending downgrade" — verify
  this resolves sensibly against real data, flagged as untested combi
  nation below)
- Register a Razorpay TEST subscription, then call `change_plan` for
  real and confirm in the Razorpay Dashboard that `PATCH
  /v1/subscriptions/:id` actually produced `has_scheduled_changes`/
  `schedule_change_at` matching what this app expected — the one thing
  this phase genuinely could not verify without a sandbox account

### Known limitations (Phase E)

- `resume()` does not call Razorpay — no confirmed Razorpay API for
  un-cancelling a scheduled cancellation was found this session.
- Applying a scheduled downgrade is triggered only by the
  `subscription.charged` webhook event — a subscription that never
  charges again (e.g. abandoned mid-trial) will not have its scheduled
  downgrade applied until Phase I's scheduler exists.
- An upgrade requested while a downgrade is already scheduled for a
  DIFFERENT plan is blocked (`PLAN_CHANGE_ALREADY_PENDING`) rather than
  auto-resolved (e.g. by cancelling the pending downgrade) — the
  customer must be told to resolve it, no endpoint for "cancel my
  pending scheduled downgrade" was built this phase (the underlying
  `subscription/service.py::clear_scheduled_plan_change()` function
  exists and is ready, just not wired to a whitelisted endpoint yet).
- `reconcile_subscriptions()` (Phase D) reconciles STATUS drift, not
  PLAN drift — if Razorpay's own plan and this app's local `plan` field
  were ever to diverge (e.g. the local `change_plan()` write failing
  after a successful Razorpay sync, an edge case Part 14's own ordering
  is designed to make rare, not impossible), nothing currently detects
  that specific divergence automatically.
