"""
QTT Admin › Servers › Errors: the open errors from QTT's own error monitoring (GlitchTip, errors.queentouchtech.in) — the
QTT OS app (phone and web) and the Frappe server. Read with a read-only token (QTT Ops Settings › Error monitoring);
every 10 minutes new errors, and old ones suddenly happening a lot, go to the ops Telegram. Rules: ops/errors_rules.py.

  list_errors   the open errors, newest first (Platform Owners)
  sync          the 10-minute look (scheduler)
"""

import json
from datetime import datetime, timezone

import frappe
import requests
from frappe.utils import get_datetime

from qtt_platform.ops import errors_rules as rules
from qtt_platform.tenant.guards import require_platform_owner

SETTINGS = "QTT Ops Settings"
TIMEOUT = 15
SEEN_KEY = "qtt_errors_counts"


def _conf() -> tuple[str, str, str | None]:
	s = frappe.get_cached_doc(SETTINGS)
	return ((s.get("errors_url") or "https://errors.queentouchtech.in").rstrip("/"), s.get("errors_org") or "queen-touch-technology",
			s.get_password("errors_token", raise_exception=False))


def _fetch() -> list[dict]:
	base, org, token = _conf()
	if not token:
		return []
	r = requests.get(f"{base}/api/0/organizations/{org}/issues/", params={"query": "is:unresolved", "limit": 100},
					 headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
	r.raise_for_status()
	return [rules.issue_out(i, base, org) for i in r.json() or []]


@frappe.whitelist(methods=["GET"])
def list_errors() -> dict:
	"""{errors: [...], summary, url, configured, error}: the open errors, the latest seen first."""
	require_platform_owner()
	base, org, token = _conf()
	if not token:
		return {"errors": [], "summary": rules.summary([]), "url": base, "configured": False, "error": None}
	try:
		issues = _fetch()
	except requests.RequestException as e:
		return {"errors": [], "summary": rules.summary([]), "url": base, "configured": True, "error": str(e)[:200]}
	issues.sort(key=lambda i: i["last_seen"] or "", reverse=True)
	return {"errors": issues, "summary": rules.summary(issues), "url": f"{base}/{org}/issues", "configured": True, "error": None}


def sync() -> None:
	"""Every 10 minutes: tell the ops Telegram about new errors (and old ones suddenly happening a lot)."""
	from qtt_platform.api.servers import _alert

	if not _conf()[2]:
		return
	try:
		issues = _fetch()
	except requests.RequestException:
		return  # the monitor itself is down — the site watch reports that
	s = frappe.get_single(SETTINGS)
	since = get_datetime(s.errors_seen_until) if s.get("errors_seen_until") else None
	before = json.loads(frappe.db.get_default(SEEN_KEY) or "{}")
	for kind, i in rules.to_alert(issues, since, before)[:10]:
		_alert(rules.alert_text(kind, i))
	frappe.db.set_default(SEEN_KEY, json.dumps({i["id"]: i["count"] for i in issues}))
	frappe.db.set_single_value(SETTINGS, "errors_seen_until", datetime.now(timezone.utc).replace(tzinfo=None))  # UTC, as GlitchTip
	frappe.db.commit()
