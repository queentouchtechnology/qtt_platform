"""
The one function every event-writing call site in this app uses —
qtt_platform.audit.write_audit_event(). Closes out the TODO(audit)
comments left across Phases 1/3/4/9 (grep the codebase's history for
`TODO(Phase 8+ audit)`/`TODO(audit)` if any remain — this module existing
means there should be none left unresolved).
"""

import json

import frappe


def write_audit_event(
	event_type: str,
	*,
	tenant: str | None = None,
	product: str | None = None,
	actor: str | None = None,
	target_doctype: str | None = None,
	target_name: str | None = None,
	before_state: dict | None = None,
	after_state: dict | None = None,
	metadata: dict | None = None,
) -> None:
	actor = actor or (frappe.session.user if frappe.session and frappe.session.user != "Guest" else None)
	ip_address = frappe.local.request_ip if getattr(frappe.local, "request_ip", None) else None

	frappe.get_doc(
		{
			"doctype": "QTT Audit Log",
			"tenant": tenant,
			"product": product,
			"actor": actor,
			"event_type": event_type,
			"target_doctype": target_doctype,
			"target_name": target_name,
			"ip_address": ip_address,
			"occurred_at": frappe.utils.now_datetime(),
			"before_state": json.dumps(before_state) if before_state is not None else None,
			"after_state": json.dumps(after_state) if after_state is not None else None,
			"metadata": json.dumps(metadata) if metadata is not None else None,
		}
	).insert(ignore_permissions=True)
