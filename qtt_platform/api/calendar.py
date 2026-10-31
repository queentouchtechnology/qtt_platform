"""
The one Calendar for every role (rules: calendar_items_rules.py). Meetings, posts going out, renewals and expiries,
leave, holidays and birthdays in one place — each person sees what their role lets them.

  items(start, end)   everything dated between two dates for this person in this business: the team calendar (with
                      Office Pulse) and every app's own things (hook qtt_calendar_sources — each source decides who
                      sees what; one that fails is left out, never the whole calendar)
"""

import frappe
from frappe import _

from qtt_platform import calendar_items_rules as rules
from qtt_platform.calendar_rules import parse_when
from qtt_platform.tenant.context import resolve_active_tenant
from qtt_platform.tenant.guards import require_tenant_membership

GOVERNANCE = ("Tenant Owner", "Tenant Admin")
PULSE = "QTT_OFFICE_PULSE"


@frappe.whitelist(methods=["GET"])
def items(start: str, end: str) -> dict:
	"""{items, layers, can_add_event} between start and end (dates; at most 100 days)."""
	tenant = resolve_active_tenant()
	m = require_tenant_membership(tenant)
	try:
		frm, to = rules.window(parse_when(start), parse_when(end))
	except ValueError as exc:
		frappe.throw(_(str(exc)))
	user = frappe.session.user
	from qtt_platform.product.guards import has_product_access

	who = frappe._dict(tenant=tenant, user=user, role=m.tenant_role, admin=m.tenant_role in GOVERNANCE,
					   has=lambda product: has_product_access(tenant, product, user))
	pulse = who.has(PULSE)
	out, available = [], set()
	for path in ["qtt_platform.api.calendar.team_events", *frappe.get_hooks("qtt_calendar_sources")]:
		try:
			got = frappe.get_attr(path)(who, frm, to)
		except Exception:
			frappe.log_error(title=f"Calendar source failed: {path}")
			continue
		if got is None:
			continue  # not for this person
		if isinstance(got, dict):  # {"layers": [...], "items": [...]}: the layers it covers even when empty
			available |= set(got.get("layers") or [])
			got = got.get("items") or []
		for it in got:
			c = rules.clean(it)
			if c:
				out.append(c)
	out.sort(key=rules.sort_key)
	return {"items": out, "layers": rules.layer_summary(out, available), "can_add_event": pulse}


def team_events(who, frm, to):
	"""The team calendar (comes with Office Pulse): meetings, with this person's answer."""
	if not who.has(PULSE):
		return None
	from qtt_platform.api import team_calendar

	got = team_calendar.events(str(frm), str(to))
	return {"layers": ["events"], "items": [{
		"key": f"event:{e['name']}:{e['start']}", "layer": "events", "title": e["title"], "start": e["start"], "end": e["end"],
		"all_day": e["all_day"], "color": e["color"], "event": e["name"], "location": e.get("location"), "meeting_url": e.get("meeting_url"),
		"organizer": None if e.get("mine") else e.get("organizer"), "response": e.get("response"),
		"status": "Answer" if e.get("response") == "needs" else None, "tone": "warning" if e.get("response") == "needs" else None,
		"subtitle": e.get("location") or None} for e in got["events"]]}
