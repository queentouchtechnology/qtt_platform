"""
Verification for QTT's own other sites (Edenza's seller onboarding): the same checks as Business › Profile, called
server-to-server with the token in Desk › QTT Verification Settings (header X-QTT-Token). The service behind it is
never named in the answer.

  check(kind, number, ifsc, name, ref)  kind: gstin | pan | bank | cin · ref: who it's for on that site (e.g. "edenza:user:123")
  → {check, result, record_name, details, name_score, name_match, summary, cached}
"""

import hmac

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from qtt_platform import verification


def _allowed() -> str:
	given = (frappe.get_request_header("X-QTT-Token") or "").strip()
	token = verification.settings().get_password("edenza_token", raise_exception=False) or ""
	if not token or not given or not hmac.compare_digest(given, token):
		frappe.throw(_("Not allowed."), frappe.PermissionError)
	return "Edenza"


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=3600)
def check(kind: str, number: str, ifsc: str | None = None, name: str | None = None, ref: str | None = None) -> dict:
	"""One check for a partner site (token in X-QTT-Token): result and a one-line summary, PAN and account masked. `name` may
	hold several names to compare, separated by | (the business and its owner): the best match counts."""
	source = _allowed()
	frappe.set_user("Administrator")  # the check record is written by the site's token, not a person
	try:
		return verification.check(kind, number, ifsc=ifsc, name=[x.strip() for x in str(name or "").split("|")], source=source, subject=ref)
	except verification.VerificationUnavailable as e:
		frappe.local.response.http_status_code = 503
		return {"result": "failed", "summary": str(e)}
