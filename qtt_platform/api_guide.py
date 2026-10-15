"""Desk › QTT API Endpoint — the backend guide, loaded from api_guide.json (generated from the code
by qtt-os/tool/api_guide.py) on every migrate. Endpoints gone from the code are removed."""

import json
import os

import frappe

DOCTYPE = "QTT API Endpoint"
FIELDS = ("product", "area", "status", "used_by", "http_methods", "guest", "arguments", "source", "purpose", "details",
		  "screens", "app_calls", "other_callers")


def sync() -> None:
	path = os.path.join(os.path.dirname(__file__), "api_guide.json")
	if not frappe.db.table_exists(DOCTYPE) or not os.path.exists(path):
		return
	with open(path, encoding="utf-8") as f:
		rows = json.load(f).get("endpoints") or []
	keep = set()
	for r in rows:
		name = r["endpoint"]
		keep.add(name)
		values = {k: r.get(k) for k in FIELDS}
		if frappe.db.exists(DOCTYPE, name):
			frappe.db.set_value(DOCTYPE, name, values, update_modified=False)
		else:
			doc = frappe.new_doc(DOCTYPE)
			doc.update({"endpoint": name, **values})
			doc.flags.ignore_permissions = True
			doc.db_insert()
	for name in frappe.get_all(DOCTYPE, pluck="name"):
		if name not in keep:
			frappe.db.delete(DOCTYPE, {"name": name})
	frappe.db.commit()
