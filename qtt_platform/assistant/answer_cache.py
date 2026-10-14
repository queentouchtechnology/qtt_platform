"""
QTT Assistant answer cache: one model call per question per person (rules: logic.answer_key /
answer_version / cacheable). A kept answer is reused while everything it was built from is the same;
when the knowledge, plans, services, screens, the person's roles or the model change, the next ask
calls the model once and replaces it. Rows: QTT Assistant Answer (Desk shows hits per question).
"""

import json

import frappe
from frappe.utils import add_days, now_datetime

DT = "QTT Assistant Answer"
KEEP_DAYS = 90


def get(key: str, version: str) -> dict | None:
	"""The kept answer for this question, if it's still current (counts the reuse)."""
	row = frappe.db.get_value(DT, key, ["answer", "version", "hits"], as_dict=True)
	if not row or row.version != version:
		return None  # never asked, or outdated
	try:
		reply = json.loads(row.answer)
	except ValueError:
		return None
	frappe.db.set_value(DT, key, {"hits": (row.hits or 0) + 1, "last_used": now_datetime()}, update_modified=False)
	return reply


def put(key: str, version: str, *, user: str, tenant: str, screen: str | None, question: str, model: str, reply: dict) -> None:
	"""Keep (or replace an outdated) answer. Never fails the ask."""
	values = {"version": version, "model": model, "answer": json.dumps(reply, ensure_ascii=False), "last_used": now_datetime(),
			  "question": question[:1000], "screen": screen}
	try:
		if frappe.db.exists(DT, key):
			frappe.db.set_value(DT, key, values)
		else:
			frappe.get_doc({"doctype": DT, "question_key": key, "user": user, "tenant": tenant, "hits": 0, **values}).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		pass  # the same question answered twice at once: one is enough
	except Exception:
		frappe.log_error(title="QTT Assistant: keeping an answer")


def purge_unused() -> None:
	"""Daily: answers nobody has reused for 90 days."""
	frappe.db.delete(DT, {"last_used": ["<", add_days(now_datetime(), -KEEP_DAYS)]})
