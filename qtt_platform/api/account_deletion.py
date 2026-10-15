"""
Delete my account (account_deletion_rules has the rules):

  status        is a deletion on its way, when, and what stops or closes with it
  request       from the app: signed in, so no email check — it waits GRACE_DAYS
  keep          changed my mind: the request is withdrawn
  request_web   from /delete_account without signing in: an email link confirms it (Frappe's own)
  run_due       daily: deletions whose wait is over — close businesses owned alone, remove their
                devices and usage, then anonymise them (Frappe's Personal Data Deletion Request)

A business owner whose business still has other people can't delete the account until those people
are removed (Business › Team) — nobody is left without their business.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from qtt_platform import account_deletion_rules as rules
from qtt_platform.audit import write_audit_event

PDDR = "Personal Data Deletion Request"
OPEN = ("Pending Verification", "Pending Approval", "On Hold")


def _me() -> str:
	user = frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		frappe.throw(_("Sign in first."), frappe.PermissionError)
	return user


def _open_request(user: str):
	return frappe.db.get_value(PDDR, {"email": user, "status": ["in", OPEN]}, ["name", "status", "modified", "creation"],
							   as_dict=True, order_by="creation desc")


def _owned(user: str) -> list[dict]:
	out = []
	for t in frappe.get_all("QTT Tenant", filters={"owner_user": user, "status": ["not in", ["cancelled", "archived"]], "is_house": 0},
							fields=["name", "tenant_name"]):
		others = frappe.db.count("QTT Tenant Membership", {"tenant": t.name, "status": "active", "user": ["!=", user]})
		out.append({"tenant": t.name, "name": t.tenant_name or t.name, "others": others})
	return out


def _out(user: str) -> dict:
	req = _open_request(user)
	owned = _owned(user)
	confirmed = get_datetime(req.modified) if req and req.status == "Pending Approval" else None
	return {
		"pending": bool(req and req.status == "Pending Approval"),
		"on_hold": bool(req and req.status == "On Hold"),
		"delete_on": str(rules.delete_on(confirmed).date()) if confirmed else None,
		"blockers": rules.blockers(owned),
		"closes": [b["name"] for b in owned if b["tenant"] in rules.closes(owned)],
		"grace_days": rules.GRACE_DAYS,
	}


@frappe.whitelist(methods=["GET"])
def status() -> dict:
	return _out(_me())


@frappe.whitelist(methods=["POST"])
def request() -> dict:
	user = _me()
	blocked = rules.blockers(_owned(user))
	if blocked:
		frappe.throw(_("You own {0}, where other people still work. Remove them in Business › Team first — then you can delete your account.")
					 .format(", ".join(blocked)))
	if not _open_request(user):
		muted = frappe.flags.mute_emails
		frappe.flags.mute_emails = True  # signed in already: no "confirm it's you" email
		try:
			doc = frappe.get_doc({"doctype": PDDR, "email": user}).insert(ignore_permissions=True)
		finally:
			frappe.flags.mute_emails = muted
		doc.db_set("status", "Pending Approval")
	else:
		frappe.db.set_value(PDDR, _open_request(user).name, "status", "Pending Approval")
	out = _out(user)
	write_audit_event("account_deletion_requested", metadata={"user": user, "delete_on": out["delete_on"]})
	_email(user, _("Your QTT OS account will be deleted on {0}").format(out["delete_on"]),
		   _("You asked to delete your QTT OS account. It will be deleted on {0}{1}.<br><br>Changed your mind? Open QTT OS › Account › "
			 "<b>Keep my account</b> before then.").format(
			   out["delete_on"], _(" — and {0} will close with it").format(", ".join(out["closes"])) if out["closes"] else ""))
	return out


@frappe.whitelist(methods=["POST"])
def keep() -> dict:
	user = _me()
	req = _open_request(user)
	if req:
		frappe.delete_doc(PDDR, req.name, ignore_permissions=True, force=True)
		write_audit_event("account_deletion_withdrawn", metadata={"user": user})
	return _out(user)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_web(email: str) -> dict:
	"""From the web page, signed out. Always the same answer (it never says whether an email has an
	account); an account gets Frappe's email with a link that confirms the request."""
	email = (email or "").strip().lower()
	key = f"qtt_delete_web:{frappe.local.request_ip}"
	if int(frappe.cache.get_value(key) or 0) >= 5:
		frappe.throw(_("Too many tries. Try again in an hour."))
	frappe.cache.set_value(key, int(frappe.cache.get_value(key) or 0) + 1, expires_in_sec=3600)
	if frappe.utils.validate_email_address(email) and frappe.db.exists("User", {"name": email, "enabled": 1}) \
			and email not in ("admin@example.com",) and not _open_request(email):
		frappe.get_doc({"doctype": PDDR, "email": email}).insert(ignore_permissions=True)  # sends the confirmation email
	return {"ok": True}


def _email(user: str, subject: str, body: str) -> None:
	try:
		frappe.sendmail(recipients=[user], subject=subject, message=body, now=False)
	except Exception:
		frappe.log_error(title="Account deletion: email failed", message=frappe.get_traceback())


# ---- the daily job ----------------------------------------------------------------------------
def run_due() -> None:
	now = now_datetime()
	for req in frappe.get_all(PDDR, filters={"status": "Pending Approval"}, fields=["name", "email", "modified"]):
		if not rules.is_due(get_datetime(req.modified), now):
			continue
		try:
			_delete(req.name, req.email)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Account deletion failed: {req.name}", message=frappe.get_traceback())


def _delete(request_name: str, user: str) -> None:
	owned = _owned(user)
	blocked = rules.blockers(owned)
	if blocked:
		# Someone joined their business during the wait: hold it and say why (to them and to QTT).
		frappe.db.set_value(PDDR, request_name, "status", "On Hold")
		_email(user, _("Your QTT OS account wasn't deleted"),
			   _("Other people now work in {0}, which you own. Remove them in Business › Team, then ask again from Account › Delete my account.")
			   .format(", ".join(blocked)))
		return
	for tenant in rules.closes(owned):
		_close_business(tenant, user)
	for t in frappe.get_all("QTT Tenant Membership", filters={"user": user, "status": ["!=", "removed"]}, pluck="name"):
		frappe.db.set_value("QTT Tenant Membership", t, "status", "removed")
		for a in frappe.get_all("QTT Product Access", filters={"membership": t, "status": "active"}, pluck="name"):
			frappe.db.set_value("QTT Product Access", a, "status", "removed")
	for doctype in rules.DELETE_ROWS:
		if frappe.db.table_exists(doctype):
			frappe.db.delete(doctype, {"user": user})
	from frappe.sessions import clear_sessions

	clear_sessions(user=user, force=True)
	write_audit_event("account_deleted", metadata={"request": request_name, "closed": rules.closes(owned)})
	frappe.set_user("Administrator")
	doc = frappe.get_doc(PDDR, request_name)
	doc.add_comment("Comment", _("Deleted by QTT OS {0} days after the request (closed: {1}).")
					.format(rules.GRACE_DAYS, ", ".join(rules.closes(owned)) or "—"))
	doc.trigger_data_deletion()  # disables the user and anonymises them everywhere (queued), then emails them


def _close_business(tenant: str, user: str) -> None:
	"""A business owned alone closes with the account: subscriptions stop now (nothing more is billed),
	each app's own clean-up runs (hook qtt_on_business_closed, e.g. managed services), and it's marked
	cancelled — its records are then handled as the Privacy Policy says."""
	from qtt_platform.billing import service as billing_service
	from qtt_platform.subscription import service
	from qtt_platform.subscription.service import OPEN_SUBSCRIPTION_STATUSES

	for product in frappe.get_all("QTT Tenant Product Subscription Pointer", filters={"tenant": tenant}, pluck="product"):
		current = service.get_current_subscription(tenant, product)
		if not current or current.status not in OPEN_SUBSCRIPTION_STATUSES:
			continue
		try:
			current = service.cancel_subscription(tenant, product, at_period_end=False, reason="Owner deleted their account")
			billing_service.cancel_razorpay_subscription(current.name, cancel_at_cycle_end=False)
		except Exception:
			frappe.log_error(title=f"Account deletion: couldn't cancel {tenant} {product}", message=frappe.get_traceback())
	for fn in frappe.get_hooks("qtt_on_business_closed"):
		try:
			frappe.get_attr(fn)(tenant)
		except Exception:
			frappe.log_error(title=f"Account deletion: {fn} failed for {tenant}", message=frappe.get_traceback())
	frappe.db.set_value("QTT Tenant", tenant, "status", "cancelled")
	write_audit_event("business_closed_with_owner", tenant=tenant, metadata={"owner": user})
