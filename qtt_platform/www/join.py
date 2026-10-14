"""/join?code=K7M2-QX9P — the invitation email's Join button. Opens the QTT OS app with the code
filled in (qttos://join), and shows the code to copy in case the app isn't on this phone yet.
Shows only the business and who invited — never the invitee's email."""

import frappe
from frappe.utils import now_datetime

from qtt_platform import invitation_code
from qtt_platform.api.invitation import find_pending

no_cache = 1


def get_context(context):
	raw = (frappe.form_dict.get("code") or "").strip()
	context.no_cache = 1
	context.title = "Join on QTT OS"
	context.state = "invalid"
	name = find_pending(raw) if invitation_code.looks_like_code(raw) else None
	if not name:
		return context
	inv = frappe.db.get_value("QTT Invitation", name, ["tenant", "invited_by", "expires_on", "code"], as_dict=True)
	context.business = frappe.db.get_value("QTT Tenant", inv.tenant, "tenant_name") or ""
	if inv.expires_on and now_datetime() > inv.expires_on:
		context.state = "expired"
		return context
	context.state = "ok"
	context.code = invitation_code.display(inv.code)
	context.inviter = frappe.utils.get_fullname(inv.invited_by) if inv.invited_by else context.business
	context.app_link = f"qttos://join?code={context.code}"
	context.android = frappe.db.get_single_value("QTT App Settings", "update_url_android")
	context.ios = frappe.db.get_single_value("QTT App Settings", "update_url_ios")
	return context
