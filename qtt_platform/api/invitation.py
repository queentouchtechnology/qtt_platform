"""
Tenant invitation — SaaS lifecycle Phase F. Owner/Admin invites an email
address to a tenant (optionally with QMP_LMS-or-whatever-product access
attached); the invitee accepts via a one-time token, which is when a
QTT Tenant Membership (and, if a product was included, a QTT Product
Access) actually gets created.

invite_user/revoke_invitation/get_pending_invitations follow
api/product_access.py's existing convention exactly (plain dicts, real
frappe.throw on failure — these are the same class of tenant-governance
action grant_product_access/revoke_product_access already are, gated the
same way). accept_invitation follows api/saas.py::signup()'s convention
instead (the {"success": ...} envelope from qtt_platform.errors) — it's
the other guest-accessible endpoint in this app besides signup and the
Razorpay webhook, and inherits that pattern for the same reason signup
does: a caller with no session yet needs a response shape it can safely
branch on without depending on HTTP status parsing.
"""

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from qtt_platform.audit import write_audit_event
from qtt_platform.errors import QttApiError, fail, ok
from qtt_platform.tenant.guards import require_tenant_role
from qtt_platform.user_provisioning import create_user

_GOVERNANCE_ROLES = ["Tenant Owner", "Tenant Admin"]
_DEFAULT_EXPIRY_DAYS = 7


@frappe.whitelist()
def invite_user(
	tenant: str,
	email: str,
	tenant_role: str = "Member",
	product: str | None = None,
	product_role: str | None = None,
	expires_in_days: int = _DEFAULT_EXPIRY_DAYS,
) -> dict:
	"""Owner/Admin only. Creates (or refreshes, if one is already
	pending) a QTT Invitation and emails the invitee a token. Product
	role, if given, must come from that product's own role catalog —
	QTT Invitation.validate() enforces this the same way QTT Product
	Access already does; this function never hardcodes a role list."""
	require_tenant_role(tenant, _GOVERNANCE_ROLES)
	email = (email or "").strip().lower()

	membership_name = frappe.db.get_value("QTT Tenant Membership", {"user": email, "tenant": tenant}, "name")
	if membership_name and frappe.db.get_value("QTT Tenant Membership", membership_name, "status") == "active":
		frappe.throw(_("{0} is already a member of this tenant.").format(email), frappe.ValidationError)

	existing_pending = frappe.db.exists(
		"QTT Invitation", {"tenant": tenant, "email": email, "status": "pending"}
	)
	token = frappe.generate_hash(length=48)
	expires_on = add_days(now_datetime(), expires_in_days)

	if existing_pending:
		invitation = frappe.get_doc("QTT Invitation", existing_pending)
		invitation.tenant_role = tenant_role
		invitation.product = product
		invitation.product_role = product_role
		invitation.token = token
		invitation.expires_on = expires_on
		invitation.save(ignore_permissions=True)
	else:
		invitation = frappe.get_doc(
			{
				"doctype": "QTT Invitation",
				"tenant": tenant,
				"email": email,
				"tenant_role": tenant_role,
				"product": product,
				"product_role": product_role,
				"status": "pending",
				"token": token,
				"invited_by": frappe.session.user,
				"expires_on": expires_on,
			}
		)
		invitation.insert(ignore_permissions=True)

	_send_invitation_email(invitation)

	write_audit_event(
		"user_invited",
		tenant=tenant,
		product=product,
		target_doctype="QTT Invitation",
		target_name=invitation.name,
		metadata={"email": email, "tenant_role": tenant_role, "product_role": product_role},
	)

	return {"invitation": invitation.name, "email": email, "expires_on": str(invitation.expires_on)}


@frappe.whitelist()
def revoke_invitation(tenant: str, invitation: str) -> dict:
	require_tenant_role(tenant, _GOVERNANCE_ROLES)
	invitation_tenant = frappe.db.get_value("QTT Invitation", invitation, "tenant")
	if invitation_tenant != tenant:
		frappe.throw(_("This invitation does not belong to your tenant."), frappe.PermissionError)

	frappe.db.set_value("QTT Invitation", invitation, "status", "revoked")
	write_audit_event(
		"invitation_revoked", tenant=tenant, target_doctype="QTT Invitation", target_name=invitation
	)
	return {"invitation": invitation, "status": "revoked"}


@frappe.whitelist()
def get_pending_invitations(tenant: str) -> list[dict]:
	require_tenant_role(tenant, _GOVERNANCE_ROLES)
	return frappe.get_all(
		"QTT Invitation",
		filters={"tenant": tenant, "status": "pending"},
		fields=["name", "email", "tenant_role", "product", "product_role", "expires_on", "invited_by", "creation"],
		order_by="creation desc",
	)


def expire_stale_invitations() -> list[dict]:
	"""SaaS lifecycle Phase I — the scheduled sweep this app's own README
	flagged as missing: proactively marks any 'pending' QTT Invitation
	whose expires_on has passed as 'expired', rather than relying only on
	the lazy check already inside accept_invitation() (which only catches
	it if someone actually tries to use the expired token — harmless, but
	leaves a stale-looking 'pending' row sitting in get_pending_
	invitations() indefinitely otherwise). Never @frappe.whitelist()'d —
	called only by the scheduler (hooks.py's scheduler_events)."""
	expired = []
	stale = frappe.get_all(
		"QTT Invitation", filters={"status": "pending", "expires_on": ["<", now_datetime()]}, fields=["name", "tenant"]
	)
	for row in stale:
		try:
			frappe.db.set_value("QTT Invitation", row.name, "status", "expired")
			write_audit_event(
				"invitation_expired", tenant=row.tenant, target_doctype="QTT Invitation", target_name=row.name
			)
			expired.append({"invitation": row.name})
		except Exception:
			frappe.log_error(
				title=f"qtt_platform.api.invitation.expire_stale_invitations failed for {row.name}",
				message=frappe.get_traceback(),
			)
	return expired


@frappe.whitelist(allow_guest=True, methods=["POST"])
def accept_invitation(token: str, full_name: str | None = None, password: str | None = None) -> dict:
	"""Guest-accessible — the invitee may not have a session yet. Two
	cases: the email already has a Frappe User (the caller must already
	be logged in AS that user — this endpoint never accepts a password
	for an EXISTING account, which would be an account-takeover-shaped
	surface); or it doesn't, in which case `full_name`/`password` create
	one via the same qtt_platform.user_provisioning.create_user() Phase A
	signup uses. Creates the QTT Tenant Membership (and QTT Product
	Access, if the invitation included one) only now, on acceptance —
	never at invite time, since `user` is a required field on QTT Tenant
	Membership and often doesn't exist until this call creates it."""
	try:
		invitation_name = frappe.db.exists("QTT Invitation", {"token": token, "status": "pending"})
		if not invitation_name:
			raise QttApiError("INVALID_INVITATION", "This invitation is invalid or has already been used.")

		invitation = frappe.get_doc("QTT Invitation", invitation_name)
		if now_datetime() > invitation.expires_on:
			invitation.status = "expired"
			invitation.save(ignore_permissions=True)
			raise QttApiError("INVITATION_EXPIRED", "This invitation has expired. Ask for a new one.")

		existing_user = frappe.db.exists("User", invitation.email)
		if existing_user:
			if frappe.session.user != invitation.email:
				raise QttApiError(
					"LOGIN_REQUIRED",
					f"An account already exists for {invitation.email}. Log in as that user, then accept again.",
				)
			user_name = existing_user
		else:
			if not full_name or not password:
				raise QttApiError(
					"ACCOUNT_DETAILS_REQUIRED", "full_name and password are required to create your account."
				)
			user = create_user(full_name.strip(), invitation.email, password)
			user_name = user.name

		membership = _ensure_membership(invitation.tenant, user_name, invitation.tenant_role)

		access = None
		if invitation.product:
			access = _ensure_product_access(membership.name, invitation.tenant, invitation.product, invitation.product_role)

		invitation.status = "accepted"
		invitation.accepted_at = now_datetime()
		invitation.accepted_by = user_name
		invitation.save(ignore_permissions=True)

		write_audit_event(
			"invitation_accepted",
			tenant=invitation.tenant,
			product=invitation.product,
			actor=user_name,
			target_doctype="QTT Invitation",
			target_name=invitation.name,
			metadata={"tenant_role": invitation.tenant_role, "product_role": invitation.product_role},
		)

		return ok(
			{
				"user": user_name,
				"tenant": invitation.tenant,
				"tenant_role": membership.tenant_role,
				"product": invitation.product,
				"product_role": access.product_role if access else None,
			}
		)

	except QttApiError as exc:
		return fail(exc.code, str(exc))
	except frappe.ValidationError as exc:
		return fail("VALIDATION_ERROR", str(exc))
	except Exception:
		frappe.log_error(title="qtt_platform.api.invitation.accept_invitation failed", message=frappe.get_traceback())
		return fail("INTERNAL_ERROR", "Could not accept this invitation. Please try again.")


def _ensure_membership(tenant: str, user: str, tenant_role: str):
	"""Create-or-reactivate, mirroring api/product_access.py::
	grant_product_access()'s identical pattern — an invitee re-accepting
	(or being re-invited after being removed) must not hit QTT Tenant
	Membership's own (user, tenant) unique constraint (patches/v0_1) as
	an unhandled error."""
	existing_name = frappe.db.exists("QTT Tenant Membership", {"user": user, "tenant": tenant})
	if existing_name:
		membership = frappe.get_doc("QTT Tenant Membership", existing_name)
		membership.tenant_role = tenant_role
		membership.status = "active"
		membership.save(ignore_permissions=True)
	else:
		membership = frappe.get_doc(
			{
				"doctype": "QTT Tenant Membership",
				"user": user,
				"tenant": tenant,
				"tenant_role": tenant_role,
				"status": "active",
			}
		)
		membership.insert(ignore_permissions=True)
	return membership


def _ensure_product_access(membership_name: str, tenant: str, product: str, product_role: str):
	existing_name = frappe.db.exists("QTT Product Access", {"membership": membership_name, "product": product})
	if existing_name:
		access = frappe.get_doc("QTT Product Access", existing_name)
		access.product_role = product_role
		access.status = "active"
		access.save(ignore_permissions=True)
	else:
		access = frappe.get_doc(
			{
				"doctype": "QTT Product Access",
				"membership": membership_name,
				"tenant": tenant,
				"product": product,
				"product_role": product_role,
				"status": "active",
			}
		)
		access.insert(ignore_permissions=True)
	return access


def _send_invitation_email(invitation) -> None:
	tenant_name = frappe.db.get_value("QTT Tenant", invitation.tenant, "tenant_name")
	frappe.sendmail(
		recipients=[invitation.email],
		subject=f"You've been invited to join {tenant_name}",
		message=(
			f"<p>You've been invited to join <b>{tenant_name}</b>.</p>"
			f"<p>Your invitation code: <code>{invitation.token}</code></p>"
			f"<p>This invitation expires on {invitation.expires_on}.</p>"
		),
		reference_doctype="QTT Invitation",
		reference_name=invitation.name,
	)
