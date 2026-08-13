"""
Customer-facing SaaS onboarding — Phase A of the SaaS customer lifecycle.
The only guest-accessible endpoints in this app besides the Razorpay
webhook (api/billing.py) — a new customer has no session yet by
definition.

Everything this module does is composed from already-existing,
already-reviewed platform pieces (QTT Tenant, QTT Tenant Membership, QTT
Product Access, qtt_platform.subscription.service, qtt_platform.audit) —
no new authorization engine, no new DocType, no change to any existing
guard function. The one genuinely new piece of policy is
_INITIAL_PRODUCT_ROLE below; see its own comment for why that decision
belongs here and not in qtt_platform's generic product registry.

Atomicity (SaaS lifecycle brief, "the entire database onboarding
transaction must be atomic / never commit midway"): this module never
calls frappe.db.commit() or frappe.db.rollback() itself. It relies on
Frappe's own request lifecycle — already the exact mechanism
api/session.py::create_tenant() depends on today — which commits once,
at the end of a successful request, and rolls back everything written
during the request if any exception propagates out of the whitelisted
method. Every write below uses ignore_permissions=True (this is
Guest-called trusted bootstrap logic, the same trust boundary
subscription/service.py and product/registry.py already operate at, not
a new one), and every failure path raises rather than returning
early-with-partial-writes.
"""

import re

import frappe

from qtt_platform.ai.services.credit_service import AI_CREDITS_GRANT_FEATURE_KEY, grant_plan_credits
from qtt_platform.audit import write_audit_event
from qtt_platform.errors import QttApiError, fail, ok
from qtt_platform.subscription import service as subscription_service
from qtt_platform.user_provisioning import create_user as _provision_user

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 8
_MAX_SLUG_RETRIES = 5

#: Which QMP_LMS product role a brand-new Tenant Owner is granted at
#: signup. An explicit, deliberate policy decision (per the SaaS lifecycle
#: brief's own instruction): the platform's product-role catalog
#: (QTT Product Role) has no concept of "the" administrator role for a
#: product — that would require qtt_platform to know something
#: product-specific. QMP_LMS's real, existing role catalog (registered by
#: qmp_lms_bridge/install.py) is Instructor / Manager / Staff / Student —
#: no "Owner", no "administrator". "Manager" is the closest existing role
#: to product-level administration and is what signup grants; nothing was
#: renamed or added to that catalog. This mapping is intentionally kept
#: here, in the SaaS onboarding flow, and not inside qtt_platform's
#: generic product/registry.py, which must stay product-agnostic.
_INITIAL_PRODUCT_ROLE = {
	"QMP_LMS": "Manager",
}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def signup(
	full_name: str,
	email: str,
	password: str,
	organization_name: str,
	country: str | None = None,
	language: str | None = None,
	product_key: str = "QMP_LMS",
	plan_key: str | None = None,
) -> dict:
	"""Customer -> Frappe User -> QTT Tenant -> Tenant Owner Membership ->
	QTT Product Subscription (trial) -> QMP_LMS Product Access(Manager),
	all in one request-transaction. See the module docstring for the
	atomicity guarantee. Returns {"success": True, "data": {...}} on
	success — never a password, hash, or any secret — or
	{"success": False, "error": {"code": ..., "message": ...}} for every
	expected failure mode. An unexpected exception is logged server-side
	(frappe.log_error) and reported to the caller only as a generic
	INTERNAL_ERROR — no stack trace ever crosses this boundary.
	"""
	try:
		_validate_signup_input(full_name, email, password, organization_name)
		product = _resolve_product(product_key)
		plan = _resolve_plan(product_key, plan_key)
		_validate_locale_refs(country, language)

		user = _provision_user(full_name.strip(), email.strip().lower(), password)
		tenant = _create_tenant(user.name, organization_name.strip(), country, language)

		membership = frappe.get_doc(
			{
				"doctype": "QTT Tenant Membership",
				"user": user.name,
				"tenant": tenant.name,
				"tenant_role": "Tenant Owner",
				"status": "active",
			}
		)
		membership.insert(ignore_permissions=True)

		subscription = subscription_service.create_subscription(tenant.name, product_key, plan.name)

		if subscription.status == "trialing":
			# trial_end (SaaS lifecycle Phase C) is the fixed original trial
			# boundary; current_period_end (unchanged) will start moving on
			# renewal once Phase D's billing cycle logic lands, so this is
			# now the more correct source for the tenant-level marker.
			frappe.db.set_value("QTT Tenant", tenant.name, "trial_ends_on", subscription.trial_end)

		product_role = _INITIAL_PRODUCT_ROLE.get(product_key)
		if not product_role:
			# Reaching this means a product other than QMP_LMS was passed as
			# product_key — _resolve_product() already confirmed the product
			# row exists and is active, but self-service signup only knows
			# how to bootstrap product access for products it has an
			# explicit initial-role policy for. Fail closed rather than
			# guessing a role or leaving the owner with no product access.
			raise QttApiError(
				"INVALID_PRODUCT",
				f"Self-service signup is not configured for product '{product_key}'.",
			)

		access = frappe.get_doc(
			{
				"doctype": "QTT Product Access",
				"membership": membership.name,
				"tenant": tenant.name,
				"product": product_key,
				"product_role": product_role,
				"status": "active",
			}
		)
		access.insert(ignore_permissions=True)

		# AI credit grant (production-readiness audit, Part 10) — a
		# safe no-op (returns 0.0) if this plan defines no
		# ai_credits_grant feature at all; never blocks signup if it
		# does nothing.
		ai_credits_granted = grant_plan_credits(
			tenant.name,
			product_key,
			plan.name,
			AI_CREDITS_GRANT_FEATURE_KEY,
			source="subscription_grant",
			reference=f"signup:{subscription.name}",
		)

		_write_signup_audit_trail(tenant.name, product_key, user.name, membership, subscription)

		return ok(
			{
				"user": user.name,
				"tenant": tenant.name,
				"tenant_name": tenant.tenant_name,
				"tenant_role": membership.tenant_role,
				"product": product_key,
				"product_role": access.product_role,
				"subscription": subscription.name,
				"plan": plan.name,
				"plan_code": plan.plan_code,
				"subscription_status": subscription.status,
				"trial_ends_on": str(subscription.trial_end) if subscription.status == "trialing" else None,
				"current_period_end": str(subscription.current_period_end),
				"ai_credits_granted": ai_credits_granted,
			}
		)

	except QttApiError as exc:
		return fail(exc.code, str(exc))
	except frappe.ValidationError as exc:
		# Any validation failure raised by a reused doctype controller
		# (QTT Tenant / QTT Tenant Membership / QTT Product Access /
		# QTT Product Subscription / QTT Plan's own validate() methods) —
		# still a clean, expected rejection, just not one this function
		# pre-checked itself. Reported generically rather than guessing a
		# specific code for every possible controller-raised message.
		return fail("VALIDATION_ERROR", str(exc))
	except Exception:
		frappe.log_error(title="qtt_platform.api.saas.signup failed", message=frappe.get_traceback())
		return fail("INTERNAL_ERROR", "Signup could not be completed. Please try again.")


@frappe.whitelist(allow_guest=True)
def get_plans(product_key: str = "QMP_LMS") -> dict:
	"""Public plan catalog for the signup/pricing screen — only
	is_public=1 plans, only display-safe fields. No session required, same
	public-catalog reasoning as api/product.py::list_available_products."""
	rows = frappe.get_all(
		"QTT Plan",
		filters={"product": product_key, "is_public": 1},
		fields=["name", "plan_code", "display_name", "base_price", "billing_period", "trial_days"],
		order_by="base_price asc",
	)
	return ok({"plans": rows})


def _validate_signup_input(full_name, email, password, organization_name) -> None:
	if not (full_name or "").strip():
		raise QttApiError("VALIDATION_ERROR", "Full name is required.")
	if not (organization_name or "").strip():
		raise QttApiError("VALIDATION_ERROR", "Organization name is required.")
	if not email or not _EMAIL_RE.match(email.strip()):
		raise QttApiError("INVALID_EMAIL", "Enter a valid email address.")
	if not password or len(password) < _MIN_PASSWORD_LENGTH:
		raise QttApiError("WEAK_PASSWORD", f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.")


def _resolve_product(product_key: str):
	product = frappe.db.get_value("QTT Product", product_key, ["name", "status"], as_dict=True)
	if not product or product.status != "active":
		raise QttApiError("INVALID_PRODUCT", f"'{product_key}' is not an available product.")
	return product


def _resolve_plan(product_key: str, plan_key: str | None):
	if not plan_key:
		raise QttApiError("INVALID_PLAN", "A plan_key is required.")
	plan_name = frappe.db.get_value("QTT Plan", {"product": product_key, "plan_code": plan_key}, "name")
	if not plan_name:
		raise QttApiError("INVALID_PLAN", f"'{plan_key}' is not a plan for product '{product_key}'.")
	return frappe.get_doc("QTT Plan", plan_name)


def _validate_locale_refs(country: str | None, language: str | None) -> None:
	# Both fields are optional Links on QTT Tenant (see qtt_tenant.json) —
	# only validated if actually supplied, never silently dropped if
	# supplied-but-invalid.
	if country and not frappe.db.exists("Country", country):
		raise QttApiError("INVALID_COUNTRY", f"'{country}' is not a recognised country.")
	if language and not frappe.db.exists("Language", language):
		raise QttApiError("INVALID_LANGUAGE", f"'{language}' is not a recognised language code.")



def _create_tenant(owner_email: str, organization_name: str, country: str | None, language: str | None):
	base_slug = _slugify(organization_name)
	last_exc = None
	for attempt in range(_MAX_SLUG_RETRIES):
		slug = base_slug if attempt == 0 else f"{base_slug}-{attempt + 1}"
		tenant = frappe.get_doc(
			{
				"doctype": "QTT Tenant",
				"tenant_name": organization_name,
				"slug": slug,
				"owner_user": owner_email,
				"status": "trial",
				"country": country or None,
				"language": language or None,
			}
		)
		try:
			tenant.insert(ignore_permissions=True)
			return tenant
		except frappe.UniqueValidationError as exc:
			last_exc = exc
			continue
	raise QttApiError("INTERNAL_ERROR", "Could not allocate a unique tenant identifier.") from last_exc


def _slugify(organization_name: str) -> str:
	slug = re.sub(r"[^a-z0-9]+", "-", organization_name.strip().lower()).strip("-")
	return slug or "tenant"


def _write_signup_audit_trail(tenant, product_key, user, membership, subscription) -> None:
	write_audit_event(
		"signup", tenant=tenant, product=product_key, actor=user, target_doctype="QTT Tenant", target_name=tenant
	)
	write_audit_event(
		"membership_created",
		tenant=tenant,
		actor=user,
		target_doctype="QTT Tenant Membership",
		target_name=membership.name,
		metadata={"tenant_role": membership.tenant_role},
	)
	write_audit_event(
		"subscription_created",
		tenant=tenant,
		product=product_key,
		actor=user,
		target_doctype="QTT Product Subscription",
		target_name=subscription.name,
		metadata={"plan": subscription.plan, "status": subscription.status},
	)
	if subscription.status == "trialing":
		write_audit_event(
			"trial_started",
			tenant=tenant,
			product=product_key,
			actor=user,
			target_doctype="QTT Product Subscription",
			target_name=subscription.name,
			metadata={"trial_end": str(subscription.trial_end)},
		)
	write_audit_event(
		"product_access_granted",
		tenant=tenant,
		product=product_key,
		actor=user,
		target_doctype="QTT Product Access",
		target_name=membership.name,
		metadata={"target_user": user, "product_role": _INITIAL_PRODUCT_ROLE.get(product_key)},
	)
