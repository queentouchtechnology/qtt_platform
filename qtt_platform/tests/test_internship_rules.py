"""Internship applications (qtt_platform.internship_rules) — no bench.

    python -m unittest qtt_platform.tests.test_internship_rules -v
"""

import unittest
from datetime import date

from qtt_platform import internship_rules as r

TODAY = date(2026, 11, 23)
GOOD = {"applicant_name": " Priya  S ", "email": "Priya@Example.com", "phone": "+91 98765 43210", "area": "Flutter app development",
		"mode": "Remote", "year_of_study": "3rd year", "duration": "3 months", "start_date": "2026-12-01",
		"why": "I build small Flutter apps and want to learn how a real product is made.", "portfolio": "github.com/priya"}


class Clean(unittest.TestCase):
	def test_good_form(self):
		d = r.clean(GOOD, TODAY)
		self.assertEqual((d["applicant_name"], d["email"], d["area"], d["start_date"]), ("Priya S", "priya@example.com", "Flutter app development", "2026-12-01"))
		self.assertEqual(d["portfolio"], "https://github.com/priya")

	def test_needs(self):
		for change, msg in (({"applicant_name": ""}, "name"), ({"email": "nope"}, "email"), ({"area": "Astronaut"}, "area"),
							({"why": "hi"}, "why"), ({"phone": "123"}, "phone")):
			with self.assertRaises(r.AppError, msg=msg):
				r.clean({**GOOD, **change}, TODAY)

	def test_unknown_choices_and_past_dates_dropped(self):
		d = r.clean({**GOOD, "mode": "Mars", "year_of_study": "9th", "duration": "5 years", "start_date": "2020-01-01", "portfolio": "not a link!"}, TODAY)
		self.assertEqual((d["mode"], d["year_of_study"], d["duration"], d["start_date"], d["portfolio"]), ("Either", None, None, None, ""))

	def test_long_text_cut(self):
		self.assertEqual(len(r.clean({**GOOD, "why": "x" * 9000}, TODAY)["why"]), 3000)


class Resume(unittest.TestCase):
	def test_types_and_size(self):
		self.assertIsNone(r.resume_problem("CV.PDF", 1000))
		self.assertIsNone(r.resume_problem("cv.docx", 1000))
		self.assertIn("PDF or Word", r.resume_problem("cv.exe", 1000))
		self.assertIn("5 MB", r.resume_problem("cv.pdf", 6 * 1024 * 1024))
		self.assertIn("empty", r.resume_problem("cv.pdf", 0))
