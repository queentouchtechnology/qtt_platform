"""
Internship applications from queentouchtech.in/internship/ — the rules (pure: no frappe; tests/test_internship_rules.py).
The form asks what the team's WhatsApp message asked (owner, 23 Nov 2026), so the link replaces that message:

  1 Personal & academic   name, college, department / specialization, current year, contact number, email
  2 Requirements          duration, start and end date, mode (online / offline), mandatory as per curriculum?,
                          college request letter available?
  3 Technical background  area of interest, programming languages, tools / technologies, previous projects and internship
  4 What the college needs  project report?, completion certificate?, mentor evaluation / progress reports?, guidelines
  Documents               resume and college ID card (needed), the college's request letter (if there is one)

  AREAS / MODES / YEARS / DURATIONS / YES_NO   the choices (the same as the Desk select fields)
  clean(form, today)       the form → the application's fields, or AppError with a sentence for the applicant
  file_problem(label, name, size)   why a document can't be taken (None when fine): PDF, Word or a photo, up to 5 MB
"""

import re
from datetime import date

AREAS = ("Flutter app development", "Backend (Python, Frappe)", "Websites and SEO", "UI / UX design", "AI and automation",
		 "Digital marketing and content", "Sales and customer success", "Other")
MODES = ("Online", "Offline", "Either")
YEARS = ("1st year", "2nd year", "3rd year", "4th year", "Final year", "Graduated")
DURATIONS = ("2 weeks", "1 month", "2 months", "3 months", "6 months")
YES_NO = ("Yes", "No")
DOCUMENTS = (("resume", "Resume", True), ("college_id", "College ID card", True), ("request_letter", "Request letter", False))
FILE_TYPES = (".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp")
FILE_MAX = 5 * 1024 * 1024
_LINE = {"applicant_name": 120, "email": 140, "phone": 30, "city": 80, "college": 160, "course": 120, "portfolio": 300}
_TEXT = {"languages": 400, "tools": 600, "projects": 3000, "previous_internship": 600, "why": 3000, "college_guidelines": 1500}
_YES_NO = ("mandatory", "has_request_letter", "needs_report", "needs_certificate", "needs_progress_reports")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class AppError(ValueError):
	pass


def _one_line(v, n: int) -> str:
	return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _text(v, n: int) -> str:
	return re.sub(r"[ \t]+", " ", str(v or "").replace("\r\n", "\n")).strip()[:n]


def _choice(v, allowed: tuple) -> str | None:
	v = _one_line(v, 80)
	return v if v in allowed else None


def _day(v) -> date | None:
	try:
		return date.fromisoformat(_one_line(v, 10)) if v else None
	except ValueError:
		return None


def clean(form: dict, today: date) -> dict:
	"""The applicant's answers → the fields to save. Raises AppError for what they must fix."""
	out = {k: _one_line(form.get(k), n) for k, n in _LINE.items()}
	out.update({k: _text(form.get(k), n) for k, n in _TEXT.items()})
	out["email"] = out["email"].lower()
	if not out["applicant_name"]:
		raise AppError("Please write your full name.")
	if not out["college"]:
		raise AppError("Please write your college or university.")
	if len(re.sub(r"\D", "", out["phone"])) < 8:
		raise AppError("Please give a contact number.")
	if not EMAIL.fullmatch(out["email"]):
		raise AppError("Please check your email address.")
	out["area"] = _choice(form.get("area"), AREAS)
	if not out["area"]:
		raise AppError("Please choose your area of interest.")
	out["mode"] = _choice(form.get("mode"), MODES) or "Either"
	out["year_of_study"] = _choice(form.get("year_of_study"), YEARS)
	out["duration"] = _choice(form.get("duration"), DURATIONS)
	for k in _YES_NO:
		out[k] = _choice(form.get(k), YES_NO)
	start, end = _day(form.get("start_date")), _day(form.get("end_date"))
	start = start if start and start >= today else None
	if start and end and end < start:
		raise AppError("The end date is before the start date.")
	out["start_date"], out["end_date"] = (start.isoformat() if start else None), (end.isoformat() if end and end >= today else None)
	if out["portfolio"] and not re.match(r"^https?://\S+\.\S+", out["portfolio"]):
		out["portfolio"] = "https://" + out["portfolio"] if re.match(r"^[\w.-]+\.\w+(/\S*)?$", out["portfolio"]) else ""
	return out


def file_problem(label: str, filename: str | None, size: int) -> str | None:
	name = (filename or "").lower()
	if not name.endswith(FILE_TYPES):
		return f"{label}: send a PDF, a Word file or a photo."
	if size > FILE_MAX:
		return f"{label} is larger than 5 MB."
	if size <= 0:
		return f"{label}: that file is empty."
	return None


def missing_documents(have: set[str]) -> str | None:
	"""The first document still needed (None when every needed one is there)."""
	need = next((label for key, label, required in DOCUMENTS if required and key not in have), None)
	return f"Please add your {need.lower()}." if need else None
