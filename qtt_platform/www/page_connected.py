"""/page-connected — where a business lands after connecting a Facebook / Instagram / … page for
the Marketing assistant (the posting service's project redirect URL). Says it worked (or not) and
to go back to the app, which shows the page as soon as it's open again. Names no tool behind it."""

import frappe

no_cache = 1


def get_context(context):
	args = frappe.form_dict
	context.no_cache = 1
	context.title = "Page connected"
	# An OAuth refusal comes back as ?error=… (the person tapped Cancel, or didn't allow posting).
	context.failed = bool(args.get("error") or args.get("error_description") or str(args.get("success") or "").lower() == "false")
	return context
