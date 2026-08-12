"""
Machine-readable API error codes and a consistent {success, data|error}
response envelope (SaaS lifecycle spec, error handling / response format
sections) — scoped to qtt_platform.api.saas only.

Deliberately NOT a replacement for how the rest of this app already
signals failure. Every existing whitelisted method (session.py,
product_access.py, subscription.py, billing.py, ...) raises
frappe.PermissionError / frappe.ValidationError directly and lets
Frappe's own request-handling turn that into a non-2xx response with an
`exc_type` body — that mechanism is unchanged, still authoritative
everywhere else, and still what every guard function in tenant/guards.py,
product/guards.py, and document_security.py raises. Retrofitting a new
response shape onto those endpoints would be exactly the kind of
"weaken/redesign existing behavior" the SaaS lifecycle brief prohibits.

This module exists only for qtt_platform.api.saas — the new,
customer-facing onboarding surface — which explicitly asks for a
{"success": true/false, ...} body instead of relying on HTTP status +
exc_type the way the Desk-oriented APIs do.
"""

import frappe


class QttApiError(frappe.ValidationError):
	"""Raise with an explicit, machine-readable `code` from within an
	api.saas endpoint. Caught at that endpoint's own boundary and turned
	into fail(code, message) — never allowed to propagate as a raw
	traceback to the caller."""

	def __init__(self, code: str, message: str):
		self.code = code
		super().__init__(message)


def ok(data: dict | None = None) -> dict:
	return {"success": True, "data": data if data is not None else {}}


def fail(code: str, message: str) -> dict:
	return {"success": False, "error": {"code": code, "message": message}}
