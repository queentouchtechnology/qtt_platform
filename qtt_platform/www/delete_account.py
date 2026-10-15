"""/delete_account — delete a QTT OS account from the web (the address Google Play lists). Signed in:
see where the deletion stands. Signed out: enter the email; if it has an account, an email link
confirms the request (api/account_deletion.request_web). Either way it waits 7 days, then runs."""

import frappe

no_cache = 1


def get_context(context):
	from qtt_platform import account_deletion_rules as rules

	context.no_cache = 1
	context.title = "Delete your QTT OS account"
	context.grace_days = rules.GRACE_DAYS
	context.signed_in = frappe.session.user not in ("Guest", None)
	return context
