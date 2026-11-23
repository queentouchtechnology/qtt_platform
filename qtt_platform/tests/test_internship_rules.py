"""Internship applications (qtt_platform.internship_rules) — no bench.

    python -m unittest qtt_platform.tests.test_internship_rules -v
"""

import unittest
from datetime import date

from qtt_platform import internship_rules as r

TODAY = date(2026, 11, 23)
GOOD = {"applicant_name": " Priya  S ", "college": "Anna University", "course": "B.E. CSE", "year_of_study": "3rd year",
		"phone": "+91 98765 43210", "email": "Priya@Example.com", "duration": "1 month", "start_date": "2026-12-01",
		"end_date": "2026-12-31", "mode": "Online", "mandatory": "Yes", "has_request_letter": "No", "area": "Flutter app development",
		"languages": "Dart, Python", "tools": "Flutter, Git", "projects": "A shop billing app", "needs_report": "Yes",
		"needs_certificate": "Yes", "needs_progress_reports": "No", "portfolio": "github.com/priya"}


class Clean(unittest.TestCase):
	def test_the_whatsapp_message_in_full(self):
		d = r.clean(GOOD, TODAY)
		self.assertEqual((d["applicant_name"], d["email"], d["area"], d["mode"]), ("Priya S", "priya@example.com", "Flutter app development", "Online"))
		self.assertEqual((d["start_date"], d["end_date"], d["mandatory"], d["needs_certificate"]), ("2026-12-01", "2026-12-31", "Yes", "Yes"))
		self.assertEqual(d["portfolio"], "https://github.com/priya")

	def test_needed(self):
		for change, msg in (({"applicant_name": ""}, "name"), ({"college": ""}, "college"), ({"phone": ""}, "phone"),
							({"email": "nope"}, "email"), ({"area": "Astronaut"}, "area"), ({"end_date": "2026-11-30"}, "end before start")):
			with self.assertRaises(r.AppError, msg=msg):
				r.clean({**GOOD, **change}, TODAY)

	def test_unknown_choices_and_past_dates_dropped(self):
		d = r.clean({**GOOD, "mode": "Mars", "year_of_study": "9th", "duration": "5 years", "mandatory": "maybe",
					 "start_date": "2020-01-01", "end_date": "2020-02-01", "portfolio": "not a link!"}, TODAY)
		self.assertEqual((d["mode"], d["year_of_study"], d["duration"], d["mandatory"], d["start_date"], d["end_date"], d["portfolio"]),
						 ("Either", None, None, None, None, None, ""))


class Documents(unittest.TestCase):
	def test_types_and_size(self):
		self.assertIsNone(r.file_problem("Resume", "CV.PDF", 1000))
		self.assertIsNone(r.file_problem("College ID card", "id.jpg", 1000))
		self.assertIn("PDF, a Word file or a photo", r.file_problem("Resume", "cv.exe", 1000))
		self.assertIn("5 MB", r.file_problem("Resume", "cv.pdf", 6 * 1024 * 1024))

	def test_resume_and_id_needed_letter_optional(self):
		self.assertEqual(r.missing_documents(set()), "Please add your resume.")
		self.assertEqual(r.missing_documents({"resume"}), "Please add your college id card.")
		self.assertIsNone(r.missing_documents({"resume", "college_id"}))
