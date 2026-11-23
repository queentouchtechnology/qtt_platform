"""
Internship applications from queentouchtech.in/internship/ — the rules (pure: no frappe; tests/test_internship_rules.py).

  AREAS / MODES / YEARS / DURATIONS   the choices the form offers (the same as the Desk select fields)
  clean(form)        the form → the application's fields, or AppError with a sentence for the applicant
  resume_problem(name, size)   why a resume file can't be taken (None when it's fine): PDF or Word, up to 5 MB
"""

import re
from datetime import date

AREAS = ("Flutter app development", "Backend (Python, Frappe)", "Websites and SEO", "UI / UX design", "AI and automation",
		 "Digital marketing and content", "Sales and customer success", "Other")
MODES = ("Remote", "In the office", "Either")
YEARS = ("1st year", "2nd year", "3rd year", "4th year", "Final year", "Graduated")
DURATIONS = ("1 month", "2 months", "3 months", "6 months")
RESUME_TYPES = (".pdf", ".doc", ".docx")
RESUME_MAX = 5 * 1024 * 1024
_MAX = {"applicant_name": 120, "email": 140, "phone": 30, "city": 80, "college": 160, "course": 120, "skills": 600, "why": 3000,
		"portfolio": 300}
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


def clean(form: dict, today: date) -> dict:
	"""The applicant's answers → the fields to save. Raises AppError for what they must fix."""
	out = {k: _one_line(form.get(k), n) for k, n in _MAX.items() if k not in ("skills", "why")}
	out["skills"], out["why"] = _text(form.get("skills"), _MAX["skills"]), _text(form.get("why"), _MAX["why"])
	out["email"] = out["email"].lower()
	if not out["applicant_name"]:
		raise AppError("Please write your name.")
	if not EMAIL.fullmatch(out["email"]):
		raise AppError("Please check your email address.")
	if out["phone"] and len(re.sub(r"\D", "", out["phone"])) < 8:
		raise AppError("Please check your phone number.")
	out["area"] = _choice(form.get("area"), AREAS)
	if not out["area"]:
		raise AppError("Please choose the area you'd like to work in.")
	out["mode"] = _choice(form.get("mode"), MODES) or "Either"
	out["year_of_study"] = _choice(form.get("year_of_study"), YEARS)
	out["duration"] = _choice(form.get("duration"), DURATIONS)
	if out["portfolio"] and not re.match(r"^https?://\S+\.\S+", out["portfolio"]):
		out["portfolio"] = "https://" + out["portfolio"] if re.match(r"^[\w.-]+\.\w+(/\S*)?$", out["portfolio"]) else ""
	start = _one_line(form.get("start_date"), 10)
	try:
		d = date.fromisoformat(start) if start else None
	except ValueError:
		d = None
	out["start_date"] = d.isoformat() if d and d >= today else None
	if len(out["why"]) < 20:
		raise AppError("Please tell us in a few lines why you'd like this internship.")
	return out


def resume_problem(filename: str | None, size: int) -> str | None:
	name = (filename or "").lower()
	if not name.endswith(RESUME_TYPES):
		return "Your resume should be a PDF or Word file."
	if size > RESUME_MAX:
		return "Your resume is larger than 5 MB."
	if size <= 0:
		return "That resume file is empty."
	return None
