"""
QTT Admin › Businesses › Internship applications: what came from queentouchtech.in/internship/ (api/internship.py →
QTT Internship Application). QTT Platform Owners only.

  applications(status, q, start)   newest first, 30 at a time, with the count in each status
  application(name)                every answer, the documents that came, the team's notes
  save(name, status, notes)        move it on and note why (audited)
  document(name, key)              the resume / college ID card / request letter itself (private files: only through here)
"""

import frappe
from frappe import _

from qtt_platform import internship_rules as rules
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_platform_owner

DOC = "QTT Internship Application"
STATUSES = ("New", "Shortlisted", "Interview", "Selected", "Rejected", "Withdrawn")
PAGE = 30
# what the detail page shows, in the form's own order
SECTIONS = (
	("The internship they need", (("duration", "Duration"), ("start_date", "Start date"), ("end_date", "End date"), ("mode", "Mode"),
								  ("mandatory", "Mandatory as per curriculum"), ("has_request_letter", "Request letter available"))),
	("Study", (("college", "College / university"), ("course", "Department / specialization"), ("year_of_study", "Current year"), ("city", "City"))),
	("Technical background", (("area", "Area of interest"), ("languages", "Programming languages"), ("tools", "Tools / technologies"),
							  ("projects", "Previous projects"), ("previous_internship", "Previous internship"), ("portfolio", "Portfolio"),
							  ("skills", "Skills"), ("why", "Why this internship"))),
	("What the college needs", (("needs_report", "Project report"), ("needs_certificate", "Completion certificate"),
								("needs_progress_reports", "Progress reports"), ("college_guidelines", "College guidelines"))),
)


def _get(name: str):
	if not frappe.db.exists(DOC, name):
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	return frappe.get_doc(DOC, name)


@frappe.whitelist(methods=["GET"])
def applications(status: str | None = None, q: str | None = None, start: int = 0) -> dict:
	"""Internship applications, newest first (30 at a time): {applications, counts by status, has_more}. q: name, email,
	phone, college or area."""
	require_platform_owner()
	filters = {"status": status} if status in STATUSES else {}
	q = " ".join(str(q or "").split())[:80]
	or_filters = [[f, "like", f"%{q}%"] for f in ("applicant_name", "email", "phone", "college", "area")] if q else None
	rows = frappe.get_all(DOC, filters=filters, or_filters=or_filters, order_by="creation desc", start=max(0, int(start or 0)),
						  page_length=PAGE + 1,
						  fields=["name", "applicant_name", "area", "college", "year_of_study", "mode", "duration", "status", "creation"])
	counts = {s: frappe.db.count(DOC, {"status": s}) for s in STATUSES}
	return {"applications": [{**r, "creation": str(r.creation)} for r in rows[:PAGE]], "has_more": len(rows) > PAGE,
			"counts": {"all": sum(counts.values()), **counts}}


@frappe.whitelist(methods=["GET"])
def application(name: str) -> dict:
	"""One internship application: who, every answer in the form's sections (empty ones left out), its documents, status
	and notes."""
	require_platform_owner()
	d = _get(name)
	sections = [{"title": t, "rows": [{"label": label, "value": str(d.get(f))} for f, label in fields if d.get(f)]} for t, fields in SECTIONS]
	return {
		"name": d.name, "applicant_name": d.applicant_name, "email": d.email, "phone": d.phone, "status": d.status,
		"statuses": list(STATUSES), "notes": d.notes or "", "creation": str(d.creation), "area": d.area,
		"sections": [s for s in sections if s["rows"]],
		"documents": [{"key": k, "label": label, "file": d.get(k).rsplit("/", 1)[-1]} for k, label, _needed in rules.DOCUMENTS if d.get(k)],
	}


@frappe.whitelist(methods=["POST"])
def save(name: str, status: str, notes: str | None = None) -> dict:
	"""Move an internship application to a status and keep the team's notes. The applicant isn't told."""
	require_platform_owner()
	if status not in STATUSES:
		frappe.throw(_("Choose a status."))
	d = _get(name)
	before = d.status
	d.status = status
	if notes is not None:
		d.notes = str(notes).strip()[:2000]
	d.save(ignore_permissions=True)
	if before != status:
		write_audit_event("internship_status", target_doctype=DOC, target_name=name, before_state={"status": before},
						  after_state={"status": status})
	return application(name)


@frappe.whitelist(methods=["GET"])
def document(name: str, key: str):
	"""A document an applicant sent (resume, college_id or request_letter), as a download."""
	require_platform_owner()
	if key not in {k for k, _label, _needed in rules.DOCUMENTS}:
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	url = _get(name).get(key)
	file = frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": DOC, "attached_to_name": name}, "name") if url else None
	if not file:
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	f = frappe.get_doc("File", file)
	frappe.response.filename = f.file_name
	frappe.response.filecontent = f.get_content()
	frappe.response.type = "download"
