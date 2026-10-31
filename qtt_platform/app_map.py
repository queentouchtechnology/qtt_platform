"""
The App Map (app_map.json, made by qtt-os/tool/app_map.py on every commit): the whole of QTT OS as one tree for new
developers — products, screens, endpoints, data tables, jobs, folders.

  load()      the map
  publish()   after every migrate: the map into QTT's own Files — Developers / QTT App Map.qttmap (only when it
              changed; the one it replaces is kept as a version). Share it from Office Pulse › Files like any file
              (expiry, password, preview only): the link shows the map, always the latest. QTT staff: /app_map.

QTT's workspace: site_config qtt_own_tenant, else the house workspace named Queen Touch Technology.
"""

import json
import os

import frappe

FOLDER = "Developers"
NAME = "QTT App Map.qttmap"


def load() -> dict:
	with open(os.path.join(os.path.dirname(__file__), "app_map.json"), encoding="utf-8") as f:
		return json.load(f)


def own_tenant() -> str | None:
	t = frappe.conf.get("qtt_own_tenant")
	if t and frappe.db.exists("QTT Tenant", t):
		return t
	if not frappe.db.has_column("QTT Tenant", "is_house"):
		return None
	return frappe.db.get_value("QTT Tenant", {"is_house": 1, "tenant_name": ["like", "%Queen Touch%"]}, "name")


def publish() -> str | None:
	"""→ the file's key, or None when there's nowhere to put it (no Files store, no QTT workspace)."""
	try:
		from qtt_platform import file_store as store
		from qtt_platform import files_core as core

		tenant = own_tenant()
		if not tenant:
			return None
		key = f"{tenant}/team/{FOLDER}/{NAME}"
		data = json.dumps(load(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
		if store.head(key):
			try:
				if store.read(key) == data:
					return key  # unchanged
			except Exception:
				pass
		else:
			store.mkdir(f"{tenant}/team/{FOLDER}/")
		core.save(tenant, key, data, "Administrator", "application/json")
		core.log(tenant, key, "team", f"{FOLDER}/{NAME}", "upload", "Administrator", detail="App Map updated by the deploy")
		frappe.db.commit()
		return key
	except Exception:
		frappe.log_error(title="App Map: not published to Files")
		return None
