"""
Approvals for marketing content (articles, LinkedIn posts, email batches,
social posts): token links for Slack, what a decision sends back to the
waiting n8n run, and how an n8n run's state maps to the content's status.

Pure (no frappe): api/marketing_content.py does the saving and HTTP.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime

KINDS = ("article", "linkedin", "email_batch", "social", "other")
DECIDABLE = ("pending",)

# "If nobody decides in time" — QTT Marketing Settings, one per kind. Articles (and anything
# unknown) are only published on an explicit yes; the rest go out unless rejected.
POLICY_FIELDS = {"email_batch": "email_batch_on_timeout", "linkedin": "linkedin_on_timeout",
				 "social": "social_on_timeout", "article": "article_on_timeout"}
POLICY_DEFAULTS = {"email_batch": "Send it", "linkedin": "Send it", "social": "Send it", "article": "Skip it", "other": "Skip it"}
WAIT_SPARE_HOURS = 1  # n8n waits this much longer than QTT, so QTT's decision always arrives first


class ApprovalError(ValueError):
	"""Message is shown to the person deciding."""


def new_token() -> str:
	return secrets.token_urlsafe(24)


def token_ok(expected: str | None, given: str | None) -> bool:
	return bool(expected) and bool(given) and hmac.compare_digest(str(expected), str(given))


def decision_links(base_url: str, name: str, token: str) -> dict:
	"""One-tap Slack links (open in the browser; Frappe records the
	decision and continues the n8n run)."""
	base = f"{base_url.rstrip('/')}/api/method/qtt_platform.api.marketing_content.slack_decide?name={name}&token={token}"
	return {"approve_url": base + "&decision=approve", "reject_url": base + "&decision=reject"}


def check_decidable(*, status: str, expires_at: datetime | None, now: datetime) -> None:
	if status not in DECIDABLE:
		raise ApprovalError(f"Already decided ({status}).")
	if expires_at and now > expires_at:
		raise ApprovalError("This approval has expired.")


def resume_payload(approved: bool, *, via: str, note: str | None, user: str | None) -> dict:
	"""Body the 'Decision' node in n8n reads: same shape as Slack's
	send-and-wait result ({data: {approved}}), plus who decided."""
	return {"data": {"approved": bool(approved)}, "decided_via": via, "note": note or "", "decided_by": user or ""}


def status_after_run(current: str, run_status: str | None) -> str:
	"""Approved content becomes published / failed once its n8n run ends."""
	if current != "approved" or not run_status:
		return current
	if run_status == "success":
		return "published"
	if run_status in ("error", "crashed", "failed"):
		return "failed"
	return current


def timeout_action(kind: str, settings: dict | None) -> str:
	"""'approve' or 'reject': what happens when nobody decides in time (QTT Marketing Settings)."""
	field = POLICY_FIELDS.get(kind)
	value = ((settings or {}).get(field) if field else None) or POLICY_DEFAULTS.get(kind, "Skip it")
	return "approve" if str(value).lower().startswith("send") else "reject"


def reminder_due(*, status: str, now: datetime, created: datetime, expires_at: datetime | None,
				 reminded_at: datetime | None, minutes: int) -> bool:
	"""Remind once, `minutes` before the deadline — not for a window shorter than twice that
	(the first email is reminder enough)."""
	if status != "pending" or not expires_at or reminded_at or minutes <= 0:
		return False
	window = (expires_at - created).total_seconds() / 60
	left = (expires_at - now).total_seconds() / 60
	return window >= 2 * minutes and 0 < left <= minutes


def timed_out(*, status: str, now: datetime, expires_at: datetime | None) -> bool:
	return status == "pending" and bool(expires_at) and now >= expires_at


def with_policy(workflow: dict, approve_on_timeout: bool, hours: float, node_keys) -> dict | None:
	"""PUT body for an approval workflow (patched by patch_approvals.py) whose own timeout matches
	QTT's: n8n waits `hours` + WAIT_SPARE_HOURS (QTT decides at `hours`), and if it ever times out
	itself the Decision step answers as the policy says. None when it's already like that."""
	nodes, changed = [], False
	want_js = "true" if approve_on_timeout else "false"
	for n in workflow.get("nodes") or []:
		n = {k: v for k, v in n.items() if k in node_keys}
		params = dict(n.get("parameters") or {})
		if n.get("name") == "Wait for decision" and params.get("resumeAmount") != hours + WAIT_SPARE_HOURS:
			params["resumeAmount"], changed = hours + WAIT_SPARE_HOURS, True
		if n.get("name") == "Decision":
			js = params.get("jsCode") or ""
			for old in ("b.data.approved : true", "b.data.approved : false"):
				new = "b.data.approved : " + want_js
				if old in js and old != new:
					js, changed = js.replace(old, new), True
			params["jsCode"] = js
		n["parameters"] = params
		nodes.append(n)
	if not changed:
		return None
	return {"name": workflow.get("name"), "nodes": nodes, "connections": workflow.get("connections") or {},
			"settings": {k: v for k, v in (workflow.get("settings") or {}).items() if k in ("executionOrder", "timezone")}}


def expired_status(timeout_action: str | None) -> str:
	"""What a pending item becomes when nobody decided in time — n8n's Wait
	step times out the same way (see the patch script's Decision node)."""
	return "approved" if timeout_action == "approve" else "expired"


def clean_new(data: dict) -> dict:
	kind = str(data.get("kind") or "other").strip().lower()
	if kind not in KINDS:
		kind = "other"
	title = str(data.get("title") or "").strip()[:140]
	if not title:
		raise ApprovalError("An approval needs a title.")
	try:
		hours = float(data.get("expires_in_hours") or 72)
	except (TypeError, ValueError):
		hours = 72
	return {
		"kind": kind,
		"title": title,
		"site": str(data.get("site") or "").strip()[:140] or None,
		"summary": str(data.get("summary") or "").strip()[:5000] or None,
		"body": str(data.get("body") or "").strip()[:200000] or None,
		"preview_url": _url(data.get("preview_url")),
		"live_url": _url(data.get("live_url")),
		"workflow_id": str(data.get("workflow_id") or "").strip()[:40] or None,
		"workflow_name": str(data.get("workflow_name") or "").strip()[:140] or None,
		"execution_id": str(data.get("execution_id") or "").strip()[:40] or None,
		"resume_url": _url(data.get("resume_url")),
		"timeout_action": "approve" if data.get("timeout_action") == "approve" else "reject",
		"expires_in_hours": max(0.25, min(hours, 24 * 14)),
	}


def plain_text(text: str) -> str:
	"""n8n's Slack-style text (`*bold*`, `<url|label>`) made readable for an email."""
	import re

	text = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2 (\1)", text or "")
	text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", text)
	return re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text).strip()


def _url(value) -> str | None:
	v = str(value or "").strip()
	return v if v.startswith(("https://", "http://")) and len(v) < 2000 else None
