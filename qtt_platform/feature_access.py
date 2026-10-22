"""
Who can open what (QTT Feature Access) — every screen and feature of QTT OS with its product, where it is, who can open it
and what it does, from the assistant's screen registry (assistant/screens.json, the same rules the app and the assistant
use). Synced after every migrate; rows for screens that are gone are removed.

  who_can     role words → plain words ("Owner and admins", "Office Pulse: HR Admin")
  rows        the registry → the rows to keep (pure; tests/test_feature_access.py)
  sync        writes them into QTT Feature Access
"""

import json
from pathlib import Path

DT = "QTT Feature Access"
PRODUCTS = {"QTT_OFFICE_PULSE": "Office Pulse", "QTT_ORBITRA": "Orbitra", "QTT_ONBOX": "Onbox", "QTT_SERVICES": "QTT Business Suite",
			"QTT_STUDIO": "QTT Studio", None: "QTT OS"}
WORDS = {"*": "Everyone in the business", "@owner": "Owner and admins", "@manager": "Managers (people with a team)",
		 "@customers": "People with customer access (and owners)"}


def who_can(roles: list, product: str | None) -> str:
	out = []
	for r in roles or []:
		if r in WORDS:
			out.append(WORDS[r])
		else:
			out.append(f"{PRODUCTS.get(product, product or 'QTT OS')}: {r}")
	return "; ".join(dict.fromkeys(out)) or "Nobody (hidden)"


def rows(registry: dict) -> list[dict]:
	out = []
	for s in registry.get("screens") or []:
		qs = [q["q"] if isinstance(q, dict) else str(q) for q in s.get("ask") or []]
		out.append({"screen_id": s["id"], "title": s.get("title") or s["id"], "product": PRODUCTS.get(s.get("product"), s.get("product")),
					"who_can_open": who_can(s.get("roles") or [], s.get("product")), "path": s.get("path") or "",
					"roles": ", ".join(s.get("roles") or []), "description": s.get("what") or "", "questions": "\n".join(qs)})
	return out


def registry() -> dict:
	return json.loads((Path(__file__).parent / "assistant" / "screens.json").read_text(encoding="utf-8"))


def sync() -> None:
	import frappe

	if not frappe.db.table_exists(DT):
		return
	want = {r["screen_id"]: r for r in rows(registry())}
	have = set(frappe.get_all(DT, pluck="name"))
	for sid, r in want.items():
		if sid in have:
			doc = frappe.get_doc(DT, sid)
			if any(str(doc.get(k) or "") != str(v or "") for k, v in r.items()):
				doc.update(r)
				doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": DT, **r}).insert(ignore_permissions=True)
	for gone in have - set(want):
		frappe.delete_doc(DT, gone, ignore_permissions=True, force=True)
	frappe.db.commit()
