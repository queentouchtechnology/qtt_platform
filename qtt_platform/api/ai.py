"""
Tenant-facing AI endpoints.

`generate()` (production-readiness audit) is the generic dispatcher the
original Phase 10 comment below deferred — it exists now because
qmp_lms_bridge finally has a real feature to dispatch to
(qmp_lms_bridge.ai_features.generate_quiz). This module still never
constructs a prompt or knows what a "quiz" is: it resolves tenant/basic
product access, looks up the registered handler for "<product>::<feature>"
(qtt_platform.ai.feature_registry — the same hooks.py-registered-dotted-
path pattern as usage_resolvers), and calls it. The registered handler
owns its own role check, credit cost, prompt, and result shape — the
server-side prompt-construction concern the original comment raised is
still respected, just resolved by keeping that logic in the product's own
bridge app rather than never building a dispatcher at all.
"""

import frappe

from qtt_platform.ai.core.exceptions import AiProviderException
from qtt_platform.ai.feature_registry import get_ai_feature_handler
from qtt_platform.ai.services.credit_service import get_balance
from qtt_platform.errors import QttApiError, fail, ok
from qtt_platform.exceptions import FeatureNotConfigured
from qtt_platform.product.guards import require_product_access
from qtt_platform.tenant.context import resolve_active_tenant


@frappe.whitelist()
def get_ai_credit_balance(tenant: str, product: str) -> dict:
	require_product_access(tenant, product)
	return {"tenant": tenant, "product": product, "balance": get_balance(tenant, product)}


@frappe.whitelist(methods=["POST"])
def generate(product: str, feature: str, inputs: dict | str | None = None) -> dict:
	"""Tenant resolved from the active session, matching this project's
	newer customer-facing endpoints (change_plan/resume/dashboard). Every
	failure mode — no active tenant, no product access, feature not
	registered, insufficient credits (mapped from generate_and_track()'s
	own plain ValidationError — that function is reused unmodified, not
	touched, so the mapping happens here rather than by changing it),
	provider failure, or the handler's own validation errors — returns
	the qtt_platform.errors envelope, never a raw traceback or a leaked
	provider detail."""
	try:
		tenant = resolve_active_tenant()
		if not tenant:
			raise QttApiError("TENANT_ACCESS_DENIED", "No active tenant.")

		try:
			require_product_access(tenant, product)
		except frappe.PermissionError as exc:
			raise QttApiError("PRODUCT_ACCESS_DENIED", str(exc)) from exc

		try:
			handler = get_ai_feature_handler(product, feature)
		except FeatureNotConfigured as exc:
			raise QttApiError("AI_FEATURE_NOT_CONFIGURED", str(exc)) from exc

		if isinstance(inputs, str):
			inputs = frappe.parse_json(inputs)

		result = handler(tenant=tenant, user=frappe.session.user, inputs=inputs or {})
		return ok(result)

	except QttApiError as exc:
		return fail(exc.code, str(exc))
	except frappe.PermissionError as exc:
		# A feature handler's own require_product_role() failure — a real
		# QMP_LMS product role (e.g. Student) attempting an
		# Instructor/Manager-only AI feature.
		return fail("ROLE_PERMISSION_DENIED", str(exc))
	except frappe.ValidationError as exc:
		message = str(exc)
		code = "AI_CREDITS_EXHAUSTED" if "credit" in message.lower() else "VALIDATION_ERROR"
		return fail(code, message)
	except AiProviderException as exc:
		return fail("AI_PROVIDER_UNAVAILABLE", str(exc))
	except Exception:
		frappe.log_error(title="qtt_platform.api.ai.generate failed", message=frappe.get_traceback())
		return fail("INTERNAL_ERROR", "AI generation failed. Please try again.")
