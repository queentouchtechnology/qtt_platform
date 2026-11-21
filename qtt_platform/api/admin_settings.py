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


# House limits (QTT's own businesses — QTT, Truth of Bible) -----------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def house() -> dict:
	"""QTT Admin › Settings › House limits: QTT's own businesses (every app, no plan, never invoiced) and the limits set
	for each — app, what is limited (a plan feature key), the amount and a note. Empty: everything, no limits. Also each
	app's keys to choose from."""
	require_platform_owner()
	from qtt_platform.house import house_tenants

	houses = []
	for t in house_tenants():
		name = frappe.db.get_value("QTT Tenant", t, "tenant_name") or t
		rows = frappe.get_all("QTT House Limit", filters={"parent": t, "parenttype": "QTT Tenant"}, fields=["product", "limit_key", "limit_value", "note"],
							  order_by="idx")
		houses.append({"tenant": t, "name": name, "limits": rows})
	products = frappe.get_all("QTT Product", filters={"status": "active"}, fields=["name", "display_name"], order_by="display_name")
	keys: dict[str, set] = {}
	for r in frappe.db.sql("""SELECT p.product, f.feature_key FROM `tabQTT Plan Feature` f JOIN `tabQTT Plan` p ON p.name = f.parent
							  WHERE f.parenttype = 'QTT Plan' AND IFNULL(f.feature_key, '') != ''""", as_dict=True):
		keys.setdefault(r.product, set()).add(r.feature_key)
	return {
		"houses": houses,
		"products": [{"product": p.name, "name": p.display_name or p.name, "keys": sorted(keys.get(p.name, ()))} for p in products],
	}


def clean_limits(rows, products: dict[str, set]) -> list[dict]:
	"""Pure: house limit rows as saved — a known app, one of its keys, a whole number ≥ 0 or "unlimited"; one per app+key."""
	out, seen = [], set()
	for r in rows or []:
		product, key = str(r.get("product") or ""), str(r.get("limit_key") or "").strip()
		if product not in products or key not in products[product]:
			raise ValueError(f"{product} · {key}")
		value = str(r.get("limit_value") if r.get("limit_value") is not None else "").strip().lower()
		if value not in ("unlimited", "-1") and not value.isdigit():
			raise ValueError(f"{key}: {value}")
		if (product, key) in seen:
			continue
		seen.add((product, key))
		out.append({"product": product, "limit_key": key, "limit_value": value, "note": " ".join(str(r.get("note") or "").split())[:200] or None})
	return out


@frappe.whitelist(methods=["POST"])
def save_house(tenant: str, limits) -> dict:
	"""Save one house business's limits (`limits`: [{product, limit_key, limit_value, note}] — the whole list; empty =
	no limits). In the audit log (before → after)."""
	require_platform_owner()
	from qtt_platform.house import is_house

	if not is_house(tenant):
		frappe.throw(_("Only QTT's own businesses have house limits."))
	if isinstance(limits, str):
		limits = json.loads(limits or "[]")
	h = house()
	products = {p["product"]: set(p["keys"]) for p in h["products"]}
	try:
		rows = clean_limits(limits, products)
	except ValueError as e:
		frappe.throw(_("Not a limit this app has, or not a whole number: {0}").format(e))
	doc = frappe.get_doc("QTT Tenant", tenant)
	before = [{"product": r.product, "limit_key": r.limit_key, "limit_value": r.limit_value} for r in doc.house_limits]
	doc.set("house_limits", [])
	for r in rows:
		doc.append("house_limits", r)
	doc.save(ignore_permissions=True)
	write_audit_event("house.limits_changed", tenant=tenant, target_doctype="QTT Tenant", target_name=tenant, before_state={"limits": before},
					  after_state={"limits": [{k: r[k] for k in ("product", "limit_key", "limit_value")} for r in rows]})
	return house()
