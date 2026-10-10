"""
QTT Admin → Marketing → Approvals / Articles / LinkedIn: content prepared by
QTT's n8n automations, and the decision to publish it.

Flow: an n8n workflow (patched by marketing-ai-os/18_AUTOMATIONS/APPROVALS/
patch_approvals.py) calls create_approval with its own resume URL, posts the
Publish / Reject links to Slack, and waits. A decision — in the app
(decide) or by a Slack link (slack_decide, token-checked) — is saved here
and sent to the waiting run, which continues exactly as the old Slack
buttons did. Whichever decision arrives first wins (row lock).
"""

import json

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_url, now_datetime
from frappe.utils.data import convert_utc_to_system_timezone

from qtt_platform.audit import write_audit_event
from qtt_platform.marketing import approvals as logic
from qtt_platform.marketing.n8n import N8nClient, N8nError
from qtt_platform.tenant.guards import require_platform_owner

DOCTYPE = "QTT Marketing Content"
SETTINGS = "QTT Marketing Settings"
LIST_FIELDS = ["name", "kind", "status", "title", "site", "summary", "preview_url", "live_url", "expires_at", "timeout_action",
			   "decided_by", "decided_at", "decided_via", "decision_note", "published_at", "workflow_name", "execution_id", "creation"]


# --------------------------------------------------------------------------
# Called by n8n
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def create_approval(**kwargs) -> dict:
	require_platform_owner()
	try:
		clean = logic.clean_new(kwargs)
	except logic.ApprovalError as exc:
		frappe.throw(_(str(exc)))
	hours = clean.pop("expires_in_hours")
	doc = frappe.get_doc({
		"doctype": DOCTYPE,
		**clean,
		"status": "pending",
		"expires_at": add_to_date(now_datetime(), hours=hours),
		"token": logic.new_token(),
	}).insert(ignore_permissions=True)
	links = logic.decision_links(get_url(), doc.name, doc.token)
	return {"name": doc.name, **links, "app": "QTT OS → QTT Admin → Marketing → Approvals"}


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_content(kind: str | None = None, status: str | None = None, limit: int = 60) -> dict:
	require_platform_owner()
	_refresh_finished()
	filters = {}
	if kind:
		filters["kind"] = ["in", [k for k in str(kind).split(",") if k in logic.KINDS]]
	if status:
		filters["status"] = ["in", str(status).split(",")]
	rows = frappe.get_all(DOCTYPE, filters=filters, fields=LIST_FIELDS, order_by="creation desc", page_length=min(int(limit or 60), 200))
	for r in rows:
		for f in ("expires_at", "decided_at", "published_at", "creation"):
			r[f] = str(r[f]) if r.get(f) else None
	counts = frappe.db.sql(
		f"SELECT kind, status, COUNT(*) AS n FROM `tab{DOCTYPE}` GROUP BY kind, status", as_dict=True
	)
	month = now_datetime().strftime("%Y-%m")
	published_month = frappe.db.sql(
		f"""SELECT kind, COUNT(*) AS n FROM `tab{DOCTYPE}`
		    WHERE status='published' AND DATE_FORMAT(COALESCE(published_at, decided_at, creation), '%%Y-%%m') = %(m)s GROUP BY kind""",
		{"m": month}, as_dict=True,
	)
	return {
		"items": rows,
		"counts": [{"kind": c.kind, "status": c.status, "count": c.n} for c in counts],
		"published_this_month": {c.kind: c.n for c in published_month},
		"pending": frappe.db.count(DOCTYPE, {"status": "pending"}),
	}


@frappe.whitelist(methods=["GET"])
def get_content(name: str) -> dict:
	require_platform_owner()
	doc = frappe.get_doc(DOCTYPE, name)
	data = {f: doc.get(f) for f in LIST_FIELDS + ["body"]}
	for f in ("expires_at", "decided_at", "published_at", "creation"):
		data[f] = str(data[f]) if data.get(f) else None
	return data


@frappe.whitelist(methods=["POST"])
def decide(name: str, approve, note: str | None = None) -> dict:
	require_platform_owner()
	approved = str(approve).lower() in ("1", "true", "yes", "approve")
	try:
		_decide(name, approved, via="app", note=note, user=frappe.session.user)
	except logic.ApprovalError as exc:
		frappe.throw(_(str(exc)))
	return get_content(name)


# --------------------------------------------------------------------------
# Slack links (one tap, no login: the random token is the permission)
# --------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["GET"])
def slack_decide(name: str, token: str, decision: str):
	doc_token = frappe.db.get_value(DOCTYPE, name, "token") if name else None
	if not logic.token_ok(doc_token, token) or decision not in ("approve", "reject"):
		return _page(_("Link not valid"), _("This approval link is not valid."), "red")
	title = frappe.db.get_value(DOCTYPE, name, "title")
	try:
		_decide(name, decision == "approve", via="slack", note=None, user=None)
	except logic.ApprovalError as exc:
		return _page(title, _(str(exc)), "orange")
	if decision == "approve":
		return _page(title, _("Approved. The automation continues now."), "green")
	return _page(title, _("Rejected. Nothing will be published."), "blue")


def _page(title, message, color):
	frappe.respond_as_web_page(title, message, indicator_color=color, http_status_code=200)


# --------------------------------------------------------------------------
# Scheduler (hourly)
# --------------------------------------------------------------------------
def expire_pending() -> None:
	"""Pending items past their deadline follow their timeout rule, the same
	way the n8n Wait step does when it times out."""
	for row in frappe.get_all(DOCTYPE, filters={"status": "pending", "expires_at": ["<", now_datetime()]}, fields=["name", "timeout_action"]):
		frappe.db.set_value(DOCTYPE, row.name, {
			"status": logic.expired_status(row.timeout_action),
			"decided_via": "timeout",
			"decided_at": now_datetime(),
		})


# --------------------------------------------------------------------------
def _decide(name: str, approved: bool, *, via: str, note: str | None, user: str | None) -> None:
	# Lock the row: a Slack tap and an app tap at the same moment can't both win.
	frappe.db.sql(f"SELECT name FROM `tab{DOCTYPE}` WHERE name=%s FOR UPDATE", name)
	doc = frappe.get_doc(DOCTYPE, name)
	logic.check_decidable(status=doc.status, expires_at=get_datetime(doc.expires_at) if doc.expires_at else None, now=now_datetime())

	if doc.resume_url:
		settings = frappe.get_cached_doc(SETTINGS)
		password = settings.get_password("approval_password", raise_exception=False)
		if not password:
			raise logic.ApprovalError("Approval password missing in QTT Marketing Settings, so the automation can't be continued.")
		try:
			response = requests.post(
				doc.resume_url,
				json=logic.resume_payload(approved, via=via, note=note, user=user),
				auth=(settings.approval_user or "qtt-os", password),
				timeout=20,
			)
		except requests.RequestException as exc:
			raise logic.ApprovalError("Couldn't reach n8n. Try again in a minute.") from exc
		if response.status_code in (404, 409, 410):
			doc.db_set({"status": "expired", "decided_via": "timeout", "decided_at": now_datetime()})
			raise logic.ApprovalError("The automation is no longer waiting (it timed out or was stopped).")
		if response.status_code in (401, 403):
			raise logic.ApprovalError("n8n refused the approval password. Check QTT Marketing Settings.")
		if response.status_code >= 400:
			raise logic.ApprovalError(f"n8n returned an error ({response.status_code}). Nothing was changed.")

	doc.status = "approved" if approved else "rejected"
	doc.decided_via = via
	doc.decided_at = now_datetime()
	doc.decided_by = user if user and user != "Guest" else None
	doc.decision_note = (note or "").strip()[:500] or None
	doc.save(ignore_permissions=True)
	write_audit_event(
		"marketing_content_" + doc.status,
		target_doctype=DOCTYPE,
		target_name=doc.name,
		metadata={"kind": doc.kind, "title": doc.title, "via": via},
		actor=user if user and user != "Guest" else None,
	)


def _refresh_finished() -> None:
	"""Approved items whose n8n run has finished become published / failed."""
	rows = frappe.get_all(DOCTYPE, filters={"status": "approved", "execution_id": ["is", "set"]}, fields=["name", "execution_id"], page_length=20)
	if not rows:
		return
	settings = frappe.get_cached_doc(SETTINGS)
	key = settings.get_password("n8n_api_key", raise_exception=False) if settings.n8n_url else None
	if not key:
		return
	try:
		client = N8nClient(settings.n8n_url, key)
		for r in rows:
			run = client.execution(r.execution_id)
			new = logic.status_after_run("approved", run.get("status") or ("success" if run.get("finished") else None))
			if new != "approved":
				stopped = run.get("stoppedAt")
				at = convert_utc_to_system_timezone(get_datetime(stopped[:19].replace("T", " "))).replace(tzinfo=None) if stopped else None
				frappe.db.set_value(DOCTYPE, r.name, {"status": new, "published_at": at})
	except N8nError:
		pass
