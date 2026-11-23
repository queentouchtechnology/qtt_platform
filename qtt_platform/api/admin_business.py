"""
QTT Admin › Businesses — create a business, turn its apps on or off, settle invoices. Every app comes with QTT OS (free
until the free-use limits, then the one plan): a new business gets all of them by itself — there is no app or plan to
assign (per-app plans gone 23 Nov 2026). Managed services are assigned through qtt_services.api.admin.assign_service.

  create_business    a new business and its owner (email invitation; optional temporary password)
  set_app_status     turn an app on or off for a business (active / suspended)
  set_invoice_status mark an invoice paid (cash, UPI, bank transfer) or void it
"""

import re

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.subscription import service as subscription_service
from qtt_platform.tenant.guards import require_platform_owner

SUB = "QTT Product Subscription"


def _require_tenant(tenant: str):
	if not tenant or not frappe.db.exists("QTT Tenant", tenant):
		frappe.throw(_("Business not found."), frappe.DoesNotExistError)


@frappe.whitelist(methods=["POST"])
def create_business(business_name: str, owner_email: str, owner_name: str | None = None, house=0, temp_password: str | None = None,
					country: str | None = None) -> dict:
	"""A new business and its owner. The owner gets an email: new to QTT → a link to set their own password
	(the invitation); already a QTT user → the business appears in their list. temp_password (optional)
	lets them sign in at once with it. house=1: a free workspace (QTT's own) — never invoiced."""
	require_platform_owner()
	from qtt_platform.api.saas import _create_tenant

	name = (business_name or "").strip()
	email = (owner_email or "").strip().lower()
	if not name:
		frappe.throw(_("Name the business."))
	if not frappe.utils.validate_email_address(email):
		frappe.throw(_("Enter the owner's email address."))
	new_user = not frappe.db.exists("User", email)
	if new_user:
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": (owner_name or email.split("@")[0]).strip()[:140],
							   "send_welcome_email": 0, "enabled": 1}).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
		if not user.enabled:
			frappe.throw(_("{0} is switched off. Turn the user back on first.").format(email))
	if temp_password:
		from frappe.utils.password import update_password

		if len(temp_password) < 8:
			frappe.throw(_("Use at least 8 characters for the temporary password."))
		update_password(email, temp_password)
	tenant = _create_tenant(email, name, country, None)
	updates = {"status": "active"}
	if str(house).lower() in ("1", "true", "yes"):
		updates["is_house"] = 1
	tenant.db_set(updates)
	frappe.get_doc({"doctype": "QTT Tenant Membership", "user": email, "tenant": tenant.name, "tenant_role": "Tenant Owner",
					"status": "active", "invited_by": frappe.session.user}).insert(ignore_permissions=True)
	sent = _welcome(user, name, new_user, bool(temp_password))
	write_audit_event("admin_business_created", tenant=tenant.name, target_doctype="QTT Tenant", target_name=tenant.name,
					  metadata={"owner": email, "new_owner": new_user, "house": bool(updates.get("is_house")), "temp_password": bool(temp_password)})
	return {"tenant": tenant.name, "name": name, "owner": email, "new_owner": new_user, "email_sent": sent}


def _welcome(user, business: str, new_user: bool, has_password: bool) -> bool:
	try:
		if new_user:
			# Frappe's own welcome email: a link to set their password (works alongside a temporary one).
			user.send_welcome_mail_to_user()
		else:
			from qtt_platform import emails

			emails.send("QTT · Business ready", [user.name], {"business": business, "preheader": f"{business} is ready on QTT OS"})
		return True
	except Exception:
		frappe.log_error(title="QTT Admin: welcome email failed", message=frappe.get_traceback())
		return False


@frappe.whitelist(methods=["POST"])
def set_app_status(tenant: str, product: str, status: str) -> dict:
	"""Turn an app on (active) or off (suspended) for a business, whatever its billing."""
	require_platform_owner()
	if status not in ("active", "suspended"):
		frappe.throw(_("Choose on or off."))
	sub = subscription_service.get_current_subscription(tenant, product)
	if not sub or sub.status == "cancelled":
		frappe.throw(_("This business doesn't have this app."))
	before = sub.status
	sub.status = status
	sub.save(ignore_permissions=True)
	write_audit_event("admin_app_status", tenant=tenant, product=product, target_doctype=SUB, target_name=sub.name,
					  before_state={"status": before}, after_state={"status": status})
	return {"subscription": sub.name, "status": sub.status}


@frappe.whitelist(methods=["POST"])
def set_invoice_status(invoice: str, status: str, note: str | None = None) -> dict:
	"""Mark an open invoice paid (paid outside the app: cash, UPI, bank transfer — note says how) or void it.
	Paid runs everything a Pay now payment does: the app or service is extended and turned back on."""
	require_platform_owner()
	inv = frappe.get_doc("QTT Invoice", invoice)
	if inv.status != "open":
		frappe.throw(_("Only an open invoice can be changed."))
	if status == "paid":
		from qtt_platform.billing.service import _mark_invoice_paid_and_activate_subscriptions

		_mark_invoice_paid_and_activate_subscriptions(inv.name)  # on_update hooks extend apps and services
	elif status == "void":
		inv.status = "void"
		inv.save(ignore_permissions=True)
	else:
		frappe.throw(_("Choose paid or void."))
	if note:
		frappe.get_doc("QTT Invoice", inv.name).add_comment("Comment", re.sub(r"<[^>]+>", "", note)[:500])
	write_audit_event(f"admin_invoice_{status}", tenant=inv.tenant, target_doctype="QTT Invoice", target_name=inv.name, metadata={"note": note})
	return {"invoice": inv.name, "status": frappe.db.get_value("QTT Invoice", inv.name, "status")}
