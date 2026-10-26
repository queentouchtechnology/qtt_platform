"""
QTT Admin → Marketing → Approvals / Articles / LinkedIn: content prepared by
QTT's n8n automations, and the decision to publish it.

Flow: an n8n workflow (patched by marketing-ai-os/18_AUTOMATIONS/APPROVALS/
patch_approvals.py) calls create_approval with its own resume URL, posts the
Publish / Reject links to Slack, and waits. A decision — in the app
(decide) or by a Slack link (slack_decide, token-checked) — is saved here
and sent to the waiting run, which continues exactly as the old Slack
buttons did. Whichever decision arrives first wins (row lock).

The person who decides (QTT Marketing Settings → Who decides) is told at once — an email
with one-tap Approve / Reject, and a push on the phone when push is set up — and reminded
before the time runs out. When nobody decides, QTT decides (tick, every 5 minutes) as the
settings say for that kind: send it, or skip it. n8n waits an hour longer and, if it ever
times out itself, gives the same answer (align_workflows).
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
	clean["timeout_action"] = logic.timeout_action(clean["kind"], _settings_dict())  # QTT's policy, not the workflow's
	doc = frappe.get_doc({
		"doctype": DOCTYPE,
		**clean,
		"status": "pending",
		"expires_at": add_to_date(now_datetime(), hours=hours),
		"token": logic.new_token(),
	}).insert(ignore_permissions=True)
	_tell(doc)
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
# Slack and email links (no login: the random token is the permission). Opening a link only shows what it's about
# and a button — Slack's link previews and email scanners open links by themselves, and that used to decide (26 Oct:
# today's cold emails were "rejected" and the LinkedIn post "approved" seconds after the links were posted). The
# decision is the button's POST (slack_confirm).
# --------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["GET"])
def slack_decide(name: str, token: str, decision: str, via: str | None = None):
	"""Opening an Approve / Reject link: the item and one button to confirm — nothing is decided by opening it."""
	doc_token = frappe.db.get_value(DOCTYPE, name, "token") if name else None
	if not logic.token_ok(doc_token, token) or decision not in ("approve", "reject"):
		return _page(_("Link not valid"), _("This approval link is not valid."), "red")
	doc = frappe.db.get_value(DOCTYPE, name, ["title", "status", "summary"], as_dict=True) or {}
	if doc.get("status") != "pending":
		return _page(doc.get("title"), _("Already decided ({0}).").format(_(doc.get("status") or "")), "blue")
	approve = decision == "approve"
	from frappe.utils import escape_html

	form = (f'<p>{escape_html(doc.get("summary") or "")}</p>'
			f'<form method="post" action="/api/method/qtt_platform.api.marketing_content.slack_confirm">'
			f'<input type="hidden" name="name" value="{escape_html(name)}">'
			f'<input type="hidden" name="token" value="{escape_html(token)}">'
			f'<input type="hidden" name="decision" value="{escape_html(decision)}">'
			f'<input type="hidden" name="via" value="{escape_html(via or "")}">'
			f'<button type="submit" class="btn btn-{"primary" if approve else "default"}">'
			f'{escape_html(_("Yes, send it") if approve else _("Yes, reject it"))}</button></form>')
	return _page(doc.get("title"), form, "green" if approve else "orange")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def slack_confirm(name: str, token: str, decision: str, via: str | None = None):
	"""The button on slack_decide's page: the decision (whoever decides first wins)."""
	doc_token = frappe.db.get_value(DOCTYPE, name, "token") if name else None
	if not logic.token_ok(doc_token, token) or decision not in ("approve", "reject"):
		return _page(_("Link not valid"), _("This approval link is not valid."), "red")
	title = frappe.db.get_value(DOCTYPE, name, "title")
	try:
		_decide(name, decision == "approve", via="email" if via == "email" else "slack", note=None, user=None)
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
def tick() -> None:
	"""Scheduler (every 5 minutes): reminders before the deadline, and QTT's decision at it."""
	now = now_datetime()
	minutes = int(frappe.db.get_single_value(SETTINGS, "reminder_minutes") or 0)
	for row in frappe.get_all(DOCTYPE, filters={"status": "pending"},
							  fields=["name", "creation", "expires_at", "reminded_at", "timeout_action"]):
		expires = get_datetime(row.expires_at) if row.expires_at else None
		try:
			if logic.timed_out(status="pending", now=now, expires_at=expires):
				_decide(row.name, row.timeout_action == "approve", via="timeout", note=None, user=None, timeout=True)
			elif logic.reminder_due(status="pending", now=now, created=get_datetime(row.creation), expires_at=expires,
									reminded_at=row.reminded_at, minutes=minutes):
				_tell(frappe.get_doc(DOCTYPE, row.name), reminder=True)
			frappe.db.commit()
		except logic.ApprovalError:
			frappe.db.commit()  # e.g. n8n no longer waiting: already marked expired
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Marketing approval tick failed for {row.name}")


def expire_pending() -> None:
	"""Kept for the old hourly hook: the 5-minute tick does this now."""
	tick()


# --------------------------------------------------------------------------
# Telling the person who decides
# --------------------------------------------------------------------------
KIND_LABELS = {"article": "Article", "linkedin": "LinkedIn post", "email_batch": "Cold email batch", "social": "Social posts", "other": "Content"}


def _settings_dict() -> dict:
	doc = frappe.get_cached_doc(SETTINGS)
	return {f: doc.get(f) for f in logic.POLICY_FIELDS.values()}


def _tell(doc, *, reminder: bool = False) -> None:
	"""Email (one-tap links) and push to the person who decides. Never fails the caller."""
	settings = frappe.get_cached_doc(SETTINGS)
	user = settings.get("approver")
	if not user:
		return
	try:
		when = _local_time(doc.expires_at)
		goes = doc.timeout_action == "approve"
		label = KIND_LABELS.get(doc.kind, "Content")
		subject = (f"Reminder: {doc.title} — " if reminder else f"Approve? {doc.title} — ") + (f"goes out at {when}" if goes else f"decide by {when}")
		if settings.get("notify_email", 1):
			links = logic.decision_links(get_url(), doc.name, doc.token)
			frappe.sendmail(recipients=[frappe.db.get_value("User", user, "email") or user], subject=subject,
							message=_email_html(doc, label, when, goes, links), reference_doctype=DOCTYPE, reference_name=doc.name)
		from qtt_platform import push

		push.notify(user, title=f"{label} {'— reminder' if reminder else 'waiting for you'}",
					body=f"{doc.title} · {'goes out' if goes else 'skipped'} at {when} unless you {'reject' if goes else 'approve'}",
					data={"kind": "marketing_approval", "name": doc.name}, collapse_key=f"approval-{doc.name}")
		doc.db_set("reminded_at" if reminder else "notified_at", now_datetime(), update_modified=False)
	except Exception:
		frappe.log_error(title=f"Marketing approval: couldn't tell {user}")


def _local_time(value) -> str:
	if not value:
		return ""
	dt = get_datetime(value)
	return dt.strftime("%-I:%M %p, %-d %b") if hasattr(dt, "strftime") else str(value)


def _email_html(doc, label: str, when: str, goes: bool, links: dict) -> str:
	from html import escape

	body = logic.plain_text(doc.body or doc.summary or "")[:1800]
	button = ("display:inline-block;padding:12px 22px;border-radius:8px;font-weight:600;text-decoration:none;"
			  "font-family:Arial,sans-serif;margin:4px 8px 4px 0;")
	preview = f'<p><a href="{escape(doc.preview_url)}">Open the preview</a></p>' if doc.preview_url else ""
	rule = (f"If you do nothing, it <b>goes out at {when}</b>." if goes else f"If you do nothing, it is <b>skipped at {when}</b>.")
	return f"""
<div style="font-family:Arial,sans-serif;max-width:640px">
  <p style="color:#666;margin:0">{escape(label)}{' · ' + escape(doc.site) if doc.site else ''}</p>
  <h2 style="margin:4px 0 12px">{escape(doc.title)}</h2>
  <p>{rule}</p>
  <p>
    <a href="{links['approve_url']}&via=email" style="{button}background:#2e7d32;color:#fff">✓ {'Send' if doc.kind in ('email_batch', 'social') else 'Publish'}</a>
    <a href="{links['reject_url']}&via=email" style="{button}background:#fff;color:#c62828;border:1px solid #c62828">✕ Reject</a>
  </p>
  {preview}
  <pre style="white-space:pre-wrap;font-family:Arial,sans-serif;background:#f6f7f9;padding:14px;border-radius:8px">{escape(body)}</pre>
  <p style="color:#888;font-size:12px">Also in QTT OS → QTT Admin → Marketing. One tap decides — no login needed.</p>
</div>"""


# --------------------------------------------------------------------------
# n8n's own timeout follows QTT's policy
# --------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def align_workflows() -> dict:
	"""Every approval workflow in n8n waits an hour longer than QTT and, if it ever times out
	itself, answers as QTT Marketing Settings say. Safe to run again (QTT Admin, or after a change
	in the settings)."""
	require_platform_owner()
	from qtt_platform.marketing.n8n_schedule import NODE_KEYS

	settings = frappe.get_cached_doc(SETTINGS)
	client = N8nClient(settings.n8n_url, settings.get_password("n8n_api_key", raise_exception=False) or "")
	policy, changed, checked = _settings_dict(), [], 0
	for w in client.workflows():
		wf = client.workflow(str(w.get("id")))
		create = next((n for n in wf.get("nodes") or [] if n.get("name") == "Create approval (QTT OS)"), None)
		if not create or not any(n.get("name") == "Wait for decision" for n in wf.get("nodes") or []):
			continue
		checked += 1
		params = {p.get("name"): p.get("value") for p in (((create.get("parameters") or {}).get("bodyParameters") or {}).get("parameters") or [])}
		kind = str(params.get("kind") or "other")
		try:
			hours = float(params.get("expires_in_hours") or 72)
		except ValueError:
			hours = 72.0
		body = logic.with_policy(wf, logic.timeout_action(kind, policy) == "approve", hours, NODE_KEYS)
		if body:
			client.update_workflow(str(w.get("id")), body)
			changed.append(wf.get("name"))
	write_audit_event("marketing_approvals_aligned", target_doctype=SETTINGS, target_name=SETTINGS, metadata={"changed": changed})
	return {"checked": checked, "changed": changed}


# --------------------------------------------------------------------------
def _decide(name: str, approved: bool, *, via: str, note: str | None, user: str | None, timeout: bool = False) -> None:
	# Lock the row: a Slack tap and an app tap at the same moment can't both win.
	frappe.db.sql(f"SELECT name FROM `tab{DOCTYPE}` WHERE name=%s FOR UPDATE", name)
	doc = frappe.get_doc(DOCTYPE, name)
	# QTT's own decision at the deadline (timeout=True) is the one allowed after it.
	logic.check_decidable(status=doc.status, expires_at=None if timeout else (get_datetime(doc.expires_at) if doc.expires_at else None),
						  now=now_datetime())

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

	doc.status = "approved" if approved else ("expired" if timeout else "rejected")  # skipped by the policy, not by a person
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
