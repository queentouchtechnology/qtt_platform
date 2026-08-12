"""
Frappe User creation, shared between qtt_platform.api.saas (signup,
Phase A) and qtt_platform.api.invitation (accept_invitation, Phase F) —
extracted here rather than duplicated once a second caller needed the
identical logic. Behavior is byte-for-byte what api.saas.signup() has
used since Phase A: setting `new_password` before insert triggers
Frappe's own User.validate() -> password_strength_test() (respects the
site's System Settings -> enable_password_policy, not overridden here)
and _update_password() (real hashing) — nothing custom, no change from
what was already reviewed in Phase A.
"""

import frappe

from qtt_platform.errors import QttApiError


def create_user(full_name: str, email: str, password: str):
	"""Raises QttApiError("DUPLICATE_EMAIL", ...) or
	QttApiError("WEAK_PASSWORD", ...) on the same conditions
	api.saas.signup() has always handled; returns the inserted User doc
	on success. Never sends a welcome email — callers are responsible for
	whatever onboarding email makes sense for their own flow."""
	if frappe.db.exists("User", email):
		raise QttApiError("DUPLICATE_EMAIL", "An account with this email already exists.")
	try:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": full_name,
				"send_welcome_email": 0,
				"new_password": password,
			}
		)
		user.insert(ignore_permissions=True)
		return user
	except frappe.DuplicateEntryError as exc:
		# Two concurrent callers for the same email: User.name is the
		# email address itself, so the loser of the race hits Frappe's
		# own primary-key uniqueness here, not a guessed check of ours.
		raise QttApiError("DUPLICATE_EMAIL", "An account with this email already exists.") from exc
	except frappe.ValidationError as exc:
		raise QttApiError(
			"WEAK_PASSWORD", str(exc) or "Password does not meet the minimum security requirements."
		) from exc
