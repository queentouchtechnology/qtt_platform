"""
The one Calendar — items checked, ordered, layers, birthdays. No bench.

    python -m unittest qtt_platform.tests.test_calendar_items -v
"""

import unittest
from datetime import date, datetime

from qtt_platform import calendar_items_rules as r


class Clean(unittest.TestCase):
	def test_fills_layer_look_and_all_day(self):
		c = r.clean({"layer": "reminders", "title": "Domain expires", "start": date(2026, 11, 3)})
		self.assertEqual((c["start"], c["all_day"], c["color"], c["icon"], c["end"]), ("2026-11-03", True, "#F59E0B", "alarm", None))
		t = r.clean({"layer": "posts", "title": "Post", "start": datetime(2026, 11, 3, 7, 0), "tone": "danger", "screen": "services.marketing"})
		self.assertEqual((t["start"], t["all_day"], t["tone"], t["screen"]), ("2026-11-03 07:00:00", False, "danger", "services.marketing"))

	def test_refuses_what_cant_show(self):
		for bad in ({"layer": "nope", "title": "x", "start": "2026-11-03"}, {"layer": "posts", "title": " ", "start": "2026-11-03"},
					{"layer": "posts", "title": "x"}, "not a dict"):
			self.assertIsNone(r.clean(bad))
		self.assertIsNone(r.clean({"layer": "posts", "title": "x", "start": "2026-11-03", "tone": "loud"})["tone"])

	def test_all_day_end_is_the_last_day(self):
		c = r.clean({"layer": "people", "title": "Leave", "start": "2026-11-03", "end": "2026-11-05", "all_day": True})
		self.assertEqual((c["start"], c["end"]), ("2026-11-03", "2026-11-05"))


class Order(unittest.TestCase):
	def test_all_day_first_then_time(self):
		got = [r.clean(x) for x in (
			{"layer": "posts", "title": "b", "start": "2026-11-03 09:00"}, {"layer": "people", "title": "Holiday", "start": "2026-11-03"},
			{"layer": "events", "title": "a", "start": "2026-11-03 08:00"}, {"layer": "events", "title": "z", "start": "2026-11-02 18:00"})]
		self.assertEqual([x["title"] for x in sorted(got, key=r.sort_key)], ["z", "Holiday", "a", "b"])


class Layers(unittest.TestCase):
	def test_layers_this_person_has(self):
		items = [r.clean({"layer": "posts", "title": "p", "start": "2026-11-03"})]
		got = r.layer_summary(items, {"events"})
		self.assertEqual([(x["key"], x["count"]) for x in got], [("events", 0), ("posts", 1)])
		self.assertEqual(r.layer_summary([], set()), [])

	def test_window(self):
		self.assertEqual(r.window(datetime(2026, 11, 1), datetime(2026, 12, 1))[0], datetime(2026, 11, 1))
		for frm, to in ((None, datetime(2026, 1, 1)), (datetime(2026, 2, 1), datetime(2026, 1, 1)), (datetime(2026, 1, 1), datetime(2026, 6, 1))):
			with self.assertRaises(ValueError):
				r.window(frm, to)


class Birthdays(unittest.TestCase):
	def test_in_window_and_leap_day(self):
		people = [("Ann", date(1990, 11, 4)), ("Bo", date(1992, 2, 29)), ("Cy", date(1985, 6, 1)), ("Dee", None)]
		self.assertEqual(r.birthdays(people, date(2026, 11, 1), date(2026, 11, 30)), [("Ann", date(2026, 11, 4))])
		self.assertEqual(r.birthdays(people, date(2027, 2, 27), date(2027, 3, 1)), [("Bo", date(2027, 2, 28))])
		self.assertEqual(len(r.birthdays(people, date(2026, 12, 1), date(2027, 11, 30))), 3)  # across the new year


if __name__ == "__main__":
	unittest.main()
