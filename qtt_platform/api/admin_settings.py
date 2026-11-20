"""
QTT Admin › Settings: the money and limits every app runs on, in the app instead of Desk — free use (all 8 apps for
everyone, free until the limit, each app's free amount), the one plan's prices, the plan's fair use and the top-up
packs (QTT App Settings). QTT Platform Owners only; every change is written to the audit log (before → after).

  get()          the groups, each with its fields (label from Desk, type, value)
  save(values)   only these fields; whole numbers 0 or more (0 = no limit), prices 0 or more
"""

import json

import frappe
from frappe import _

from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_platform_owner

DOC = "QTT App Settings"

# (group key, title, explanation, Desk section that starts it) — the group runs until the next Section Break.
GROUPS = [
	("free", "Free use", "Every business can use all 8 apps free until one of these amounts. 0 = no limit.", "section_free_use"),
	("fair", "The plan's fair use", "What the one plan includes each month (or at a time). 0 = unlimited.", "section_fair_use"),
	("topups", "Top-up packs", "Extra amounts a business on the plan can buy for the rest of its month.", "section_topups"),
]
_TYPES = {"Check": "switch", "Int": "number", "Currency": "money"}


def _fields() -> list[tuple[str, str, str, dict]]:
	"""(group, fieldname, type, docfield) for every editable field in the groups, in Desk's order."""
	meta = frappe.get_meta(DOC)
	starts = {section: key for key, _t, _e, section in GROUPS}
	out, group = [], None
	for f in meta.fields:
		if f.fieldtype == "Section Break":
			group = starts.get(f.fieldname)
			continue
		if group and f.fieldtype in _TYPES and not f.hidden and not f.read_only:
			out.append((group, f.fieldname, _TYPES[f.fieldtype], f))
	return out


@frappe.whitelist(methods=["GET"])
def get() -> dict:
	"""QTT Admin › Settings: free use, the one plan's prices, the plan's fair use and the top-up packs — each field with
	its Desk label, its type (switch / number / money) and its value."""
	require_platform_owner()
	doc = frappe.get_cached_doc(DOC)
	fields = _fields()
	return {
		"groups": [
			{
				"key": key,
				"title": _(title),
				"explain": _(explain),
				"fields": [{"field": f, "label": _(df.label or f), "type": t, "value": doc.get(f)} for g, f, t, df in fields if g == key],
			}
			for key, title, explain, _s in GROUPS
		],
		"currency": "INR",
	}


def clean(kind: str, value):
	"""Pure: a value as Settings saves it — switch 0/1, number a whole number ≥ 0, money ≥ 0 (2 decimals)."""
	if kind == "switch":
		return 1 if value in (1, True, "1", "true", "True") else 0
	try:
		n = float(value)
	except (TypeError, ValueError):
		raise ValueError("not a number")
	if n < 0:
		raise ValueError("below zero")
	return int(n) if kind == "number" else round(n, 2)


@frappe.whitelist(methods=["POST"])
def save(values) -> dict:
	"""Save Settings: `values` {field: value} — only the fields Settings shows. The change reaches every app at once
	(app config refresh) and is written to the audit log."""
	require_platform_owner()
	if isinstance(values, str):
		values = json.loads(values or "{}")
	kinds = {f: t for _g, f, t, _df in _fields()}
	doc = frappe.get_doc(DOC)
	before, after = {}, {}
	for field, value in (values or {}).items():
		if field not in kinds:
			frappe.throw(_("{0} can't be changed here.").format(field))
		try:
			v = clean(kinds[field], value)
		except ValueError:
			frappe.throw(_("{0}: a number of 0 or more.").format(frappe.get_meta(DOC).get_label(field)))
		if doc.get(field) != v:
			before[field], after[field] = doc.get(field), v
			doc.set(field, v)
	if after:
		doc.save(ignore_permissions=True)
		write_audit_event("settings.changed", target_doctype=DOC, target_name=DOC, before_state=before, after_state=after)
	return {"changed": sorted(after), **get()}
