"""
Frappe User creation, shared between qtt_platform.api.saas (signup,
Phase A) and qtt_platform.api.invitation (accept_invitation, Phase F) —
extracted here rather than duplicated once a second caller needed the
identical logic.

Setting `new_password` before insert still triggers Frappe's own
User.validate() -> password_strength_test() (respects the site's System
Settings -> enable_password_policy, not overridden here) — that part
was correctly reviewed in Phase A and still holds. What did NOT hold,
found via a real, unauthenticated signup() call followed by a real
login attempt (both failed silently — no exception, no error, just an
account nobody could ever log into): on THIS Frappe version,
User.on_update() -> send_password_notification() fires validate() a
second time internally during the same insert, and that second pass
clears self.new_password to "" before send_password_notification()
ever reads it — so User's own automatic "set the password hash on
insert" side effect silently no-ops. Confirmed via direct tracing
against 100% unmodified Frappe core code (no qtt_platform involved) —
this is a framework-level quirk on this deployment, not a bug in this
function's previous logic. Rather than patch frappe/core (never
appropriate here), the password is now set explicitly and unconditionally
right after insert, via the exact same low-level utility
send_password_notification() itself would have called
(frappe.utils.password.update_password — the real "just hash and store
this password for this user" primitive, used identically for a
self-service reset with no dependency on frappe.session/reset keys).
"""

import frappe
from frappe.utils.password import update_password as _set_password

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
		_set_password(email, password)
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
