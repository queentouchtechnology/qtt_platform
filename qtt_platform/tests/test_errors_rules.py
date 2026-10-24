"""QTT Admin › Servers › Errors — the rules, no bench.

    python -m unittest qtt_platform.tests.test_errors_rules -v
"""

import unittest
from datetime import datetime

from qtt_platform.ops import errors_rules as r

RAW = {"id": "7", "title": "TypeError: x is null", "culprit": "studio_root.dart in build", "level": "error", "count": "12", "userCount": 3,
	   "firstSeen": "2026-10-24T05:18:13.028Z", "lastSeen": "2026-10-24T06:00:00.000Z", "shortId": "QTT-OS-APP-7",
	   "project": {"slug": "qtt-os-app"}}


class Errors(unittest.TestCase):
	def test_issue_in_plain_words(self):
		i = r.issue_out(RAW, "https://errors.queentouchtech.in/", "queen-touch-technology")
		self.assertEqual((i["source"], i["count"], i["users"], i["first_seen"]), ("App", 12, 3, "2026-10-24 05:18:13"))
		self.assertEqual(i["url"], "https://errors.queentouchtech.in/queen-touch-technology/issues/7")

	def test_alerts_new_and_spikes_but_not_on_the_first_look(self):
		i = r.issue_out(RAW, "https://e", "o")
		self.assertEqual(r.to_alert([i], None, {}), [])  # monitoring just started: no flood
		self.assertEqual([k for k, _ in r.to_alert([i], datetime(2026, 10, 24, 5, 0), {})], ["new"])
		self.assertEqual(r.to_alert([i], datetime(2026, 10, 24, 6, 0), {"7": 10}), [])  # old, 2 more: quiet
		big = {**i, "count": 80}
		self.assertEqual([k for k, _ in r.to_alert([big], datetime(2026, 10, 24, 6, 0), {"7": 12})], ["again"])
		self.assertIn("New error (App): TypeError", r.alert_text("new", i))

	def test_summary(self):
		i = r.issue_out(RAW, "https://e", "o")
		s = r.issue_out({**RAW, "id": "8", "project": {"slug": "qtt-os-server-frappe"}, "count": "3"}, "https://e", "o")
		self.assertEqual(r.summary([i, s]), {"open": 2, "app": 1, "server": 1, "events": 15})
