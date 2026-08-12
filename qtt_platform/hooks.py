from . import __version__ as app_version

app_name = "qtt_platform"
app_title = "QTT SaaS Platform"
app_publisher = "Queen Touch Technology"
app_description = (
    "Reusable, product-agnostic multi-tenant SaaS platform — Tenant, Membership, "
    "Product Access, Subscriptions, Entitlements, Usage, AI, Billing, Audit — "
    "consumed by QMP LMS and future QTT products without any of them being "
    "known to this app."
)
app_email = "queentouchtech@gmail.com"
app_license = "Proprietary"

# Installed on the same site as `lms`, never editing it — every touchpoint
# below is additive (Custom Fields via fixtures, hook registrations by
# doctype name). See the six architecture documents this app implements for
# the full reasoning; this file is intentionally the only place that lists
# what's actually wired up so far, phase by phase.
#
# required_apps intentionally does NOT list "lms" — qtt_platform itself has
# zero LMS-specific knowledge (see the product-agnostic architecture). It is
# QMP LMS's own future `lms`-side hook registrations (Phase 10 of the
# implementation order) that will declare a dependency on qtt_platform, not
# the other way around.
required_apps = []

# --------------------------------------------------------------------------
# PHASE 1 — implemented: Tenant, Tenant Membership, the authorization
# engine's tenant-level functions, the server-side active-tenant session
# model, and the bootstrap session API (create_tenant / switch_tenant /
# get_my_memberships).
#
# PHASE 2 — implemented: QTT Product, QTT Product Role (child table),
# QTT Product DocType (the static doctype→product registry, deliberately
# grantless — no write/create/delete DocPerm for any role, see
# qtt_product_doctype.json), the registration functions products call from
# their own install hooks (qtt_platform.product.registry — never
# whitelisted, never reachable from a tenant or HTTP request), and the
# public product catalog endpoint (list_available_products).
#
# PHASE 3 — implemented: QTT Product Access (the Membership x Product x
# Role join, with cross-tenant-reference validation and role-catalog
# validation), the product-level authorization guards
# (require_product_access / require_product_role / has_product_access,
# qtt_platform.product.guards), and the cross-cutting document_security
# module completing the full authorization engine (resolve_tenant_for_doc /
# require_document_tenant_and_product / require_same_tenant_reference /
# assert_tenant_access). The whitelisted product-access management API
# (grant_product_access / revoke_product_access / change_product_role /
# get_my_product_access) lives in api/product_access.py, gated to Tenant
# Owner/Admin governance authority per the hardening review's role matrix.
#
# PHASE 4 — implemented: QTT Plan (+ QTT Plan Feature child table, no
# usage_resolver field per the Phase 2/3 hardening fix), QTT Product
# Subscription (+ QTT Subscription Item child table), QTT Subscription
# Event (append-only, 100% system-generated), and QTT Tenant Product
# Subscription Pointer — the hardening review's section 9 fix for
# subscription concurrency: a real database unique constraint on
# (tenant, product), not an application-level check alone. The lifecycle
# service (create / change plan / cancel, plus the atomic pointer
# activation) lives in qtt_platform/subscription/service.py; the
# whitelisted, Tenant-Owner-gated API lives in api/subscription.py.
#
# PHASE 5/6 — implemented together, deliberately: get_entitlements() for a
# numeric feature is non-functional without a real usage-counting
# mechanism to call, so shipping Phase 5 alone would have been a
# half-working engine. QTT Tenant Feature Override (one-off grant/revoke,
# System-Manager-only), the feature_key field added to QTT Subscription
# Item (so an add-on can augment a numeric plan limit), the usage resolver
# registry (qtt_platform.usage.registry — reads the usage_resolvers dict
# below, aggregated across every installed app's own hooks.py, never a
# DocType field), and the entitlement engine itself
# (qtt_platform.entitlement.engine: get_entitlements / check_limit /
# is_feature_enabled / can_i) all shipped this pass. The whitelisted
# can_i endpoint lives in api/entitlements.py.
#
# No product has registered a usage resolver yet — LMS integration is
# Phase 10 — so numeric-feature checks currently fail closed for every
# feature_key (FeatureNotConfigured -> check_limit()/can_i() return
# False/not-allowed) until LMS registers its own resolvers. Flag-shaped
# features (no resolver expected) already work correctly today via
# is_feature_enabled().
#
# PHASE 7 — implemented, with an honest scope correction: every doctype
# shipped through Phase 6 grants NO DocPerm to any tenant-facing role
# (System Manager only). has_permission/permission_query_conditions hooks
# only ever run for a caller who has already cleared the coarse DocPerm
# check — since no tenant-facing role can clear it for any doctype in this
# app today, REGISTERING either hook against them would be dead code, not
# real protection (the real protection is the whitelisted API layer's own
# explicit checks, already shipped in Phases 1/3/4/5). See
# qtt_platform/permissions/handlers.py's module docstring for the full
# reasoning.
#
# What actually shipped this phase:
#   - A generic, doctype-agnostic has_permission handler (real, tested
#     shape, zero registrations yet — ready the moment Phase 10 gives it a
#     real target, e.g. a hook-only LMS doctype with broader DocPerm).
#   - permission_query_conditions deliberately NOT implemented generically
#     — its SQL-fragment shape is inherently doctype-specific; writing one
#     for a doctype that doesn't exist yet would be exactly the kind of
#     guessed API this project has avoided throughout.
#   - A REAL gap found and fixed: neither QTT Product Subscription nor QTT
#     Tenant Feature Override previously guarded against their own
#     `tenant` field being edited after creation. QTT Product Access
#     needed no such fix — its validate() already unconditionally
#     re-derives `tenant` from the referenced membership on every save, a
#     stronger, self-healing guarantee.
doc_events = {
    "QTT Product Subscription": {
        "before_save": "qtt_platform.permissions.handlers.guard_tenant_change_before_save",
    },
    "QTT Tenant Feature Override": {
        "before_save": "qtt_platform.permissions.handlers.guard_tenant_change_before_save",
    },
}
permission_query_conditions = {}
has_permission = {}

# PHASE 8 — implemented: the full AI core layer ported from
# qzmaster-ai-gateway (qtt_platform/ai/core/: AiRequest/AiResponse,
# AiProvider interface, AiProviderRegistry, AiGateway with retry+fallback,
# task->model routing now sourced from QTT AI Model instead of static
# config), six providers (Mock — real, deterministic, no network;
# DeepSeek/OpenAI/OpenRouter — real, OpenAI-compatible, via a shared HTTP
# client; Gemini/Anthropic — registered stubs, same status as the
# original Node gateway), QTT AI Provider/QTT AI Model (config, secrets
# via Password fieldtype, System-Manager-only), QTT AI Credit Ledger +
# QTT AI Usage Record (append-only, 100% system-generated), and QTT
# Tenant Product Wallet — the hardening review's section 8 fix: a real,
# atomically-updated concurrency-control cache (not a replacement source
# of truth — the ledger stays authoritative, see that doctype's own
# description). The credit/cost/usage services live in
# qtt_platform/ai/services/; the top-level orchestration
# (generate_and_track — reserve credits, call the gateway, refund on
# failure, record usage) lives in qtt_platform/ai/service.py.
#
# No whitelisted "generate" endpoint exists yet — api/ai.py exposes only
# a balance-check endpoint. An AI feature needs a real prompt and
# feature_key, both product-specific business logic; the platform
# deliberately doesn't invent a fake one to expose. That's Phase 10's
# first real caller (a future LMS QuizAiService calling
# qtt_platform.ai.service.generate_and_track() directly).
#
# One real porting difference from the Node gateway, named not hidden:
# provider HTTP calls are synchronous (requests, not fetch/await) since
# Frappe whitelisted methods run in a WSGI worker, not an event loop —
# accepted for now, same capacity question the single-application
# specification already flagged as open, not re-litigated here.
#
# PHASE 9 — implemented: QTT Payment Gateway Config (secrets via Password
# fieldtype, same trust boundary as QTT AI Provider), QTT Invoice (+ QTT
# Invoice Item, supporting multi-product consolidated billing), QTT
# Payment (append-only — a refund is a NEW row with refund_of set, never
# a mutation), QTT Payment Transaction (raw gateway records, fully
# locked). The provider-agnostic gateway interface lives in
# qtt_platform/billing/gateways/base.py; Razorpay is the first real
# implementation (real HMAC-SHA256 webhook signature verification via
# hmac.compare_digest — not guessed cryptography, but built from
# Razorpay's publicly documented conventions rather than tested against a
# real sandbox account, which wasn't available this session — see that
# file's own docstring). billing/service.py owns the full lifecycle
# (create_invoice, create_payment_order — amount always read server-side
# from the invoice, never a request parameter — process_webhook,
# refund_payment, reconcile_payments). The one allow_guest=True
# whitelisted method in this entire app is the webhook receiver
# (api/billing.py's razorpay_webhook) — its signature check is the only
# authentication, matching the hardening review section 10's explicit
# design.
#
# Also this phase: QTT Audit Log — a real gap found while writing this
# phase. Every prior phase (1/3/4) had left a `TODO(Phase 8+ audit)`
# comment deferring it, and it had never actually been scheduled as its
# own deliverable in this phase breakdown. Built now: the doctype itself
# (fully locked down, insert-only via qtt_platform.audit.write_audit_event,
# no role can rewrite history) and every one of those deferred TODOs
# wired up for real, not left pending again.
#
# PHASE 10 — implemented, in a SEPARATE app: qmp_lms_bridge (a sibling
# project, not part of this repository). qtt_platform itself gained one
# small, generic extension this phase: resolve_tenant_for_doc()
# (document_security.py) now implements the parent-walk case it deferred
# in Phase 3 — both a static registry (tenant_parent_links, below) and a
# dynamic/polymorphic one (tenant_dynamic_parent_links, for a
# reference_doctype/reference_docname-style field pair). Both dicts are
# declared empty here, same pattern as usage_resolvers: qtt_platform
# registers neither, qmp_lms_bridge populates both with real LMS data.
# has_permission (Phase 7, built generic, never registered anywhere) is
# now genuinely load-bearing — qmp_lms_bridge registers the exact same
# function against LMS's 4 hook-only doctypes with zero new platform code
# needed, exactly the "Phase 10 wires up Custom Fields and hooks.py
# registrations only" outcome Phase 1's very first comment predicted.
#
# See qmp_lms_bridge's own README for why this had to be a third app
# (never inside `lms` — vendor code; never inside qtt_platform — must
# stay product-agnostic) and for its explicit confidence notes on which
# LMS field names were freshly verified this project vs. carried forward
# from earlier work and flagged for confirmation before a real deploy.
#
# Nothing below this comment references a doctype that doesn't exist yet —
# each phase's hook registrations are added when that phase's doctypes ship,
# not stubbed in advance.
# --------------------------------------------------------------------------

# Usage-resolver registry — read by qtt_platform.usage.registry via
# frappe.get_hooks("usage_resolvers"), aggregated across every installed
# app's own declaration of this same dict (see that module for the exact
# merge logic and an open question about its precise shape, flagged there
# rather than assumed). Deliberately a hooks.py dict, never a DocType
# field — see the hardening review §2 for why a database-editable
# dotted-import-path field is an arbitrary-code-execution risk this design
# specifically avoids. qtt_platform itself registers none (it has no
# domain features of its own); populated once a product — LMS in Phase 10
# — declares its own, e.g. {"QMP_LMS::max_students": "lms.usage.count_students"}.
usage_resolvers = {}

# Tenant parent-link registries — read by
# qtt_platform.document_security.resolve_tenant_for_doc() to walk from a
# hook-only doctype (no direct `tenant` field) up to its tenant-bearing
# parent. Same aggregation mechanism and the same open shape-verification
# note as usage_resolvers above. qtt_platform registers neither; LMS
# (Phase 10, via qmp_lms_bridge — a separate app, not this one or `lms`
# itself, since neither may know about the other's doctypes) declares
# both kinds:
#   tenant_parent_links — static: {"Course Chapter": ("course", "LMS Course")}
#   tenant_dynamic_parent_links — polymorphic, e.g. a reference_doctype/
#   reference_docname pair: {"Discussion Topic": ("reference_doctype", "reference_docname")}
tenant_parent_links = {}
tenant_dynamic_parent_links = {}
