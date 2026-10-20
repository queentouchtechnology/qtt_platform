"""
Office Pulse Calendar (PROJ-0016 C1) — repeats, who sees what, reminders, calendar files. No bench.

    python -m unittest qtt_platform.tests.test_calendar -v
"""

import unittest
from datetime import date, datetime, timedelta

from qtt_platform import calendar_rules as c

D = datetime


class Repeats(unittest.TestCase):
	def test_once(self):
		s, e = D(2026, 10, 21, 10), D(2026, 10, 21, 11)
		self.assertEqual(c.occurrences(s, e, "", None, D(2026, 10, 1), D(2026, 11, 1)), [(s, e)])
		self.assertEqual(c.occurrences(s, e, "", None, D(2026, 11, 1), D(2026, 12, 1)), [])
		# an event that started before the range but is still on
		self.assertEqual(len(c.occurrences(D(2026, 10, 20, 22), D(2026, 10, 21, 2), "", None, D(2026, 10, 21), D(2026, 10, 22))), 1)

	def test_weekly_and_until(self):
		s = D(2026, 10, 5, 9)  # Monday
		occ = c.occurrences(s, s + timedelta(hours=1), "weekly", date(2026, 10, 26), D(2026, 10, 1), D(2026, 12, 1))
		self.assertEqual([o[0].day for o in occ], [5, 12, 19, 26])

	def test_weekdays_skip_weekends(self):
		s = D(2026, 10, 23, 9)  # Friday
		occ = c.occurrences(s, s + timedelta(minutes=30), "weekdays", None, D(2026, 10, 23), D(2026, 10, 28))
		self.assertEqual([o[0].strftime("%a") for o in occ], ["Fri", "Mon", "Tue"])

	def test_monthly_31st_skips_short_months(self):
		s = D(2026, 1, 31, 10)
		occ = c.occurrences(s, s, "monthly", None, D(2026, 1, 1), D(2026, 6, 1))
		self.assertEqual([o[0].month for o in occ], [1, 3, 5])

	def test_yearly_29_feb(self):
		s = D(2028, 2, 29, 9)
		occ = c.occurrences(s, s, "yearly", None, D(2028, 1, 1), D(2033, 1, 1))
		self.assertEqual([o[0].year for o in occ], [2028, 2032])

	def test_capped(self):
		s = D(2020, 1, 1, 9)
		self.assertLessEqual(len(c.occurrences(s, s, "daily", None, D(2020, 1, 1), D(2030, 1, 1))), c.MAX_OCCURRENCES)


class Who(unittest.TestCase):
	def test_visible(self):
		self.assertTrue(c.visible({"visibility": "team", "organizer": "a"}, "b", []))
		self.assertFalse(c.visible({"visibility": "private", "organizer": "a"}, "b", []))
		self.assertTrue(c.visible({"visibility": "private", "organizer": "a"}, "b", ["b"]))
		self.assertTrue(c.visible({"visibility": "private", "organizer": "a"}, "a", []))

	def test_reminders(self):
		start = D(2026, 10, 21, 10, 0)
		self.assertTrue(c.due_reminders(start, 15, D(2026, 10, 21, 9, 46)))
		self.assertFalse(c.due_reminders(start, 15, D(2026, 10, 21, 9, 40)))
		self.assertFalse(c.due_reminders(start, 15, D(2026, 10, 21, 9, 51)))
		self.assertFalse(c.due_reminders(start, -1, D(2026, 10, 21, 9, 46)))


class Files(unittest.TestCase):
	def test_invite(self):
		ev = c.ics_event(uid="e1@qtt", title="Review; budget, Q3", start=D(2026, 10, 21, 10), end=D(2026, 10, 21, 11), location="Madurai office",
						 repeat="weekly", until=date(2026, 12, 31), organizer=("ann@x.com", "Ann"), attendees=[("bo@y.com", "Bo", "yes")],
						 stamp=D(2026, 10, 20, 8))
		ics = c.ics_calendar([ev], method="REQUEST")
		self.assertIn("METHOD:REQUEST", ics)
		self.assertIn("SUMMARY:Review\\; budget\\, Q3", ics)
		self.assertIn("DTSTART;TZID=Asia/Kolkata:20261021T100000", ics)
		self.assertIn("RRULE:FREQ=WEEKLY;UNTIL=20261231T235959Z", ics)
		self.assertIn("PARTSTAT=ACCEPTED", ics)
		self.assertTrue(all(len(l.encode()) <= 75 for l in ics.split("\r\n")))
		self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))

	def test_all_day(self):
		ev = c.ics_event(uid="e2", title="Diwali", start=D(2026, 11, 8), end=D(2026, 11, 8), all_day=True)
		self.assertIn("DTSTART;VALUE=DATE:20261108", ev)
		self.assertIn("DTEND;VALUE=DATE:20261109", ev)

	def test_long_lines_fold_without_breaking_letters(self):
		ev = c.ics_event(uid="e3", title="கூட்டம் " * 20, start=D(2026, 1, 1, 9), end=D(2026, 1, 1, 10))
		ics = c.ics_calendar([ev])
		self.assertIn("கூட்டம்", ics.replace("\r\n ", ""))

	def test_parse_when(self):
		self.assertEqual(c.parse_when("2026-10-21T10:30:00"), D(2026, 10, 21, 10, 30))
		self.assertEqual(c.parse_when("2026-10-21 10:30"), D(2026, 10, 21, 10, 30))
		self.assertEqual(c.parse_when("2026-10-21"), D(2026, 10, 21))
		self.assertIsNone(c.parse_when("tomorrow"))


if __name__ == "__main__":
	unittest.main()
