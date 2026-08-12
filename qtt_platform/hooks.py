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
# NOT yet implemented (later phases — see the implementation-order section
# of the hardening review):
#   Phase 2  Product / Product DocType registry
#   Phase 3  Product Access + product roles
#   Phase 4  Plan / Product Subscription / Subscription Item
#   Phase 5  Entitlement engine (get_entitlements / check_limit / can_i)
#   Phase 6  Usage engine (hooks.py-registered resolvers, per the hardening
#            review's fix — usage_resolvers = {...} will be declared here)
#   Phase 7  permission_query_conditions / has_permission / validate hooks
#            against LMS and this app's own doctypes
#   Phase 8  AI platform (ported gateway, AI Provider/Model/Credit
#            Ledger/Usage Record, the QTT Tenant Product Wallet concurrency
#            fix)
#   Phase 9  Billing (Invoice/Payment/Payment Transaction, Razorpay adapter,
#            webhook handler)
#   Phase 10 QMP LMS integration (Custom Fields on the 12 anchor/denormalized
#            LMS doctypes, LMS's own product registration)
#
# Nothing below this comment references a doctype that doesn't exist yet —
# each phase's hook registrations are added when that phase's doctypes ship,
# not stubbed in advance.
# --------------------------------------------------------------------------

doc_events = {}
permission_query_conditions = {}
has_permission = {}

# Usage-resolver registry (Phase 6) — populated by qtt_platform's own
# resolvers (none yet) and by every product's hooks.py via Frappe's
# frappe.get_hooks("usage_resolvers") aggregation. Deliberately a hooks.py
# dict, never a DocType field — see the hardening review §2 for why a
# database-editable dotted-import-path field is an arbitrary-code-execution
# risk this design specifically avoids.
usage_resolvers = {}
