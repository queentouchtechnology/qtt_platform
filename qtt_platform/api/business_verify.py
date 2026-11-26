"""
Business › Profile › Verify your business (owner and admins): the GSTIN, PAN and default bank account saved on the
profile, checked against government records. Free: a few checks of each kind a month (Desk › QTT Verification Settings).
A check of the same number within 30 days isn't counted again.

  status()               what's verified now (only while the profile still has the same number), checks left
  verify(kind, consent)  kind: gstin | pan | bank — the number is the one saved on the profile
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_first_day, today

from qtt_platform import verification, verification_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_tenant_membership, require_tenant_role

GOVERNANCE = ["Tenant Owner", "Tenant Admin"]
KINDS = ("gstin", "pan", "bank")


def _tenant() -> str:
	from qtt_platform.api.business import _active_tenant

	tenant = _active_tenant()
	require_tenant_membership(tenant)
	return tenant


def _subject(tenant: str) -> dict:
	"""The numbers on the profile now, and the name each should match."""
	t = frappe.db.get_value("QTT Tenant", tenant, ["tenant_name", "legal_name"], as_dict=True) or frappe._dict()
	p = frappe.db.get_value("QTT Business Profile", tenant, ["gstin", "pan", "bank_account_number", "bank_ifsc", "bank_account_name"], as_dict=True) or frappe._dict()
	business = t.legal_name or t.tenant_name or ""
	return {
		"gstin": {"number": p.gstin or "", "ifsc": None, "name": business},
		"pan": {"number": p.pan or "", "ifsc": None, "name": business},
		"bank": {"number": p.bank_account_number or "", "ifsc": p.bank_ifsc or "", "name": p.bank_account_name or business},
	}


def _used(tenant: str, kind: str) -> int:
	return frappe.db.count(verification.CHECK, {"tenant": tenant, "source": "QTT OS", "kind": kind, "cached": 0, "creation": [">=", get_first_day(today())]})


@frappe.whitelist(methods=["GET"])
def status() -> dict:
	"""{verified (the business), items: [{kind, title, number, result, summary, record_name, checked_at, checks_left, has_number}]}"""
	tenant = _tenant()
	s = verification.settings()
	free = int(s.get("free_per_month") or 3)
	subject = _subject(tenant)
	items = []
	for kind in KINDS:
		want = subject[kind]
		try:
			n, i = rules.clean(kind, want["number"], want["ifsc"]) if want["number"] else ("", None)
			fp = rules.fingerprint(kind, n, i) if n else None
		except rules.VerifyError:
			fp = None
		last = frappe.db.get_value(verification.CHECK, {"tenant": tenant, "source": "QTT OS", "kind": kind, "fingerprint": fp or "-"},
								   ["result", "record_name", "given_name", "name_score", "name_match", "details", "creation", "number"], as_dict=True,
								   order_by="creation desc")
		items.append({"kind": kind, "title": rules.TITLES[kind], "has_number": bool(want["number"]),
					  "number": last.number if last else (rules.mask(kind, want["number"].upper()) if want["number"] else ""),
					  "result": last.result if last else None, "record_name": last.record_name if last else "",
					  "name_match": bool(last.name_match) if last else None,
					  "summary": rules.summary(kind, last.result, last.record_name or "", frappe.parse_json(last.details or "{}"), last.given_name or None,
											   last.name_score, int(s.get("match_threshold") or 80)) if last else "",
					  "checked_at": str(last.creation)[:10] if last else None, "checks_left": max(0, free - _used(tenant, kind))})
	ok = {x["kind"]: x["result"] == "verified" and x["name_match"] for x in items}
	return {"enabled": bool(s.get("enabled")), "verified": bool(ok.get("gstin") or ok.get("pan")), "items": items}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def verify(kind: str, consent=0) -> dict:
	"""Checks the profile's GSTIN, PAN or bank account. PAN and bank need the owner's consent (it's personal data; the bank
	check may send ₹1 to the account). Answers like status()."""
	tenant = _tenant()
	require_tenant_role(tenant, GOVERNANCE)
	if kind not in KINDS:
		frappe.throw(_("Unknown check."))
	if kind in ("pan", "bank") and str(consent).lower() not in ("1", "true", "yes"):
		frappe.throw(_("Please confirm first that you may check these details."))
	want = _subject(tenant)[kind]
	if not want["number"]:
		frappe.throw(_("Add it to the business profile first."))
	free = int(verification.settings().get("free_per_month") or 3)
	if _used(tenant, kind) >= free:
		frappe.throw(_("You've used this month's {0} checks of this kind. Try again next month.").format(free))
	try:
		r = verification.check(kind, want["number"], ifsc=want["ifsc"], name=want["name"], source="QTT OS", tenant=tenant, subject=tenant)
	except verification.VerificationUnavailable as e:
		frappe.throw(str(e))
	write_audit_event("business_verification", tenant=tenant, target_doctype=verification.CHECK, target_name=r["check"],
					  metadata={"kind": kind, "result": r["result"], "name_match": r["name_match"]})
	return status()
