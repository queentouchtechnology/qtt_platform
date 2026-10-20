"""
Two-step login for a business (PROJ-0016 B3): the owner turns it on and everyone in the business confirms each new
sign-in with a code sent to their email. Enforced by Frappe itself at login (frappe.twofactor): QTT gives these people
the role "QTT Two-Step Login", which requires two-factor; the app already asks for the code (auth_provider verifyOtp).

  two_step / set_two_step   the switch (owners and admins change it)
  sync_user                 whether a person needs the role: in any business with two-step on → yes
  on_membership             someone joins, leaves or changes business → sync them
  ensure_setup              (after migrate) the role, and Frappe's two-factor on with codes by email
"""

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership

ROLE = "QTT Two-Step Login"
GOVERNANCE = ("Tenant Owner", "Tenant Admin")


def ensure_setup() -> None:
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0, "two_factor_auth": 1}).insert(ignore_permissions=True)
	elif not frappe.db.get_value("Role", ROLE, "two_factor_auth"):
		frappe.db.set_value("Role", ROLE, "two_factor_auth", 1)
	s = frappe.get_single("System Settings")
	changed = False
	for field, value in (("enable_two_factor_auth", 1), ("two_factor_method", "Email"), ("otp_issuer_name", "QTT OS")):
		if s.get(field) != value:
			s.set(field, value)
			changed = True
	if changed:
		s.flags.ignore_permissions = True
		s.save()


def needs_role(user: str) -> bool:
	return bool(frappe.db.sql("""select 1 from `tabQTT Tenant Membership` m join `tabQTT Tenant` t on t.name = m.tenant
		where m.user = %s and m.status = 'active' and t.require_two_step = 1 limit 1""", user))


def sync_user(user: str) -> None:
	if not user or user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
		return
	have = bool(frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": ROLE}))
	want = needs_role(user)
	if want == have:
		return
	u = frappe.get_doc("User", user)
	u.flags.ignore_permissions = True
	u.add_roles(ROLE) if want else u.remove_roles(ROLE)


def on_membership(doc, method=None) -> None:
	"""doc_events: QTT Tenant Membership after_insert / on_update / on_trash."""
	try:
		sync_user(doc.user)
	except Exception:
		frappe.log_error(title="Two-step login: couldn't update a person")


def _ctx():
	tenant = resolve_active_tenant()
	if not tenant:
		frappe.throw(_("Choose your business first."), frappe.PermissionError)
	m = require_tenant_membership(tenant)
	return tenant, m.tenant_role


@frappe.whitelist(methods=["GET"])
def two_step() -> dict:
	"""Is two-step login on for this business? Who may change it."""
	tenant, role = _ctx()
	return {"on": bool(frappe.db.get_value("QTT Tenant", tenant, "require_two_step")), "can_change": role in GOVERNANCE, "method": "email"}


@frappe.whitelist(methods=["POST"])
def set_two_step(on: int = 1) -> dict:
	"""Turn two-step login on or off for everyone in this business (owners and admins). With it on, each new sign-in
	needs a code sent to the person's email; signing in with Google or a phone's fingerprint stays as it is."""
	tenant, role = _ctx()
	if role not in GOVERNANCE:
		frappe.throw(_("Only the owner or an admin can change how people sign in."), frappe.PermissionError)
	value = 1 if str(on).lower() in ("1", "true", "yes") else 0
	frappe.db.set_value("QTT Tenant", tenant, "require_two_step", value)
	for u in frappe.get_all("QTT Tenant Membership", filters={"tenant": tenant, "status": "active"}, pluck="user"):
		sync_user(u)
	write_audit_event("two_step_login_on" if value else "two_step_login_off", tenant=tenant, target_doctype="QTT Tenant", target_name=tenant)
	return two_step()
