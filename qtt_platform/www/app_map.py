"""/app_map — the App Map for QTT staff (qtt_platform/app_map.py). Others get it through an Office Pulse share link."""

import json

import frappe

no_cache = 1
SAFE = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"}  # inside <script>: never closes the tag


def get_context(context):
	from qtt_platform.app_map import load
	from qtt_platform.tenant.guards import require_platform_owner

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/app_map"
		raise frappe.Redirect
	require_platform_owner()  # QTT staff; anyone else gets a share link
	# its own JSON, not Jinja's tojson (that sorts the keys — each box's details would come out alphabetically)
	text = json.dumps(load(), ensure_ascii=False)
	for ch, esc in SAFE.items():
		text = text.replace(ch, esc)
	context.data_json = text
	context.no_header = context.no_breadcrumbs = 1
	return context
