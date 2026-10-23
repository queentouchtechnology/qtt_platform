"""/page-connected — where a business lands after connecting a Facebook / Instagram / … page for
the Marketing assistant (the posting service's project redirect URL). Says it worked (or not) and
to go back to the app, which shows the page as soon as it's open again. Names no tool behind it. Its own QTT OS page
(not the backend site's layout), with Back to QTT OS → the web app's Marketing assistant."""

import frappe

no_cache = 1

# The name to show for ?provider= (the posting service's own names).
PLATFORMS = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn", "x": "X", "youtube": "YouTube", "threads": "Threads",
			 "tiktok": "TikTok", "tiktok_business": "TikTok", "pinterest": "Pinterest", "bluesky": "Bluesky"}


def get_context(context):
	args = frappe.form_dict
	context.no_cache = 1
	context.title = "Page connected"
	# An OAuth refusal comes back as ?error=… (the person tapped Cancel, or didn't allow posting).
	context.failed = bool(args.get("error") or args.get("error_description") or str(args.get("success") or "").lower() == "false"
						  or str(args.get("isSuccess") or "").lower() == "false")
	context.platform = PLATFORMS.get(str(args.get("provider") or "").lower())
	# Back to the QTT OS web app, on the Marketing assistant (phones: they switch back to the app themselves).
	context.app_url = "https://queentouchtech.in/app/#/?s=p:QTT_SERVICES&p=services.marketing"
	return context
