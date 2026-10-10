"""
App event tracking: the QTT OS app batches events and posts them here.
Stored in QTT App Event; purged daily after the retention period set in
QTT App Settings. Collection can be switched off centrally there.

Privacy by construction: events carry only a short name plus a small
dict of scalar properties — free text is truncated and nested data is
dropped. The user/tenant are taken from the session server-side, never
from the payload.
"""

import json
import re

import frappe
from frappe import _

from qtt_platform.tenant.context import resolve_active_tenant

MAX_EVENTS_PER_CALL = 50
MAX_PROPERTIES = 20
MAX_VALUE_LENGTH = 200
_NAME = re.compile(r"^[a-z][a-z0-9_.]{1,63}$")
_PLATFORMS = {"android", "ios", "web", "windows", "macos", "linux"}


@frappe.whitelist(methods=["POST"])
def ingest(events, platform: str | None = None, app_version: str | None = None, session_id: str | None = None) -> dict:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Login required."), frappe.PermissionError)
	if not frappe.db.get_single_value("QTT App Settings", "analytics_enabled"):
		return {"accepted": 0, "disabled": True}

	if isinstance(events, str):
		events = json.loads(events or "[]")
	if not isinstance(events, list):
		frappe.throw(_("events must be a list."))

	tenant = resolve_active_tenant(user)
	platform = platform if platform in _PLATFORMS else None
	clean = [e for e in (sanitize_event(raw) for raw in events[:MAX_EVENTS_PER_CALL]) if e]
	if not clean:
		return {"accepted": 0}

	now = frappe.utils.now_datetime()
	fields = [
		"name", "creation", "modified", "owner", "modified_by",
		"event", "occurred_at", "user", "tenant", "product", "platform", "app_version", "session_id", "screen", "properties",
	]
	values = [
		(
			frappe.generate_hash(length=12), now, now, user, user,
			e["event"], e["occurred_at"] or now, user, tenant, e["product"], platform,
			(app_version or "")[:32] or None, (session_id or "")[:64] or None, e["screen"], e["properties"],
		)
		for e in clean
	]
	frappe.db.bulk_insert("QTT App Event", fields, values)
	return {"accepted": len(values)}


def sanitize_event(raw) -> dict | None:
	"""Pure; returns None for anything malformed."""
	if not isinstance(raw, dict):
		return None
	name = str(raw.get("name") or "")
	if not _NAME.match(name):
		return None
	props = raw.get("props") if isinstance(raw.get("props"), dict) else {}
	clean_props = {}
	for key, value in list(props.items())[:MAX_PROPERTIES]:
		if not isinstance(key, str) or not key:
			continue
		if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
			clean_props[key[:40]] = value
		elif isinstance(value, str):
			clean_props[key[:40]] = value[:MAX_VALUE_LENGTH]
		# lists / dicts dropped on purpose
	product = raw.get("product")
	screen = raw.get("screen")
	return {
		"event": name,
		"occurred_at": _parse_ts(raw.get("ts")),
		"product": product if isinstance(product, str) and product.isupper() and len(product) <= 40 else None,
		"screen": screen[:80] if isinstance(screen, str) else None,
		"properties": json.dumps(clean_props) if clean_props else None,
	}


def _parse_ts(value):
	"""Client timestamps are ISO-8601 or epoch milliseconds; anything else
	means 'now' (set by the caller)."""
	try:
		if isinstance(value, (int, float)):
			import datetime

			return datetime.datetime.fromtimestamp(value / 1000)
		if isinstance(value, str) and value:
			return frappe.utils.get_datetime(value.replace("Z", "").split("+")[0])
	except Exception:
		return None
	return None


def purge_old_events() -> None:
	days = frappe.db.get_single_value("QTT App Settings", "analytics_retention_days") or 180
	cutoff = frappe.utils.add_days(frappe.utils.now_datetime(), -int(days))
	frappe.db.delete("QTT App Event", {"occurred_at": ["<", cutoff]})
	frappe.db.commit()
