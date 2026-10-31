"""/app_map — the App Map for QTT staff (qtt_platform/app_map.py). Others get it through an Office Pulse share link."""

import frappe

no_cache = 1


def get_context(context):
	from qtt_platform.app_map import load
	from qtt_platform.tenant.guards import require_platform_owner

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/app_map"
		raise frappe.Redirect
	require_platform_owner()  # QTT staff; anyone else gets a share link
	context.data = load()
	context.no_header = context.no_breadcrumbs = 1
	return context
