"""Delete my account — the rules (qtt_platform.account_deletion_rules), no bench.

    python -m unittest qtt_platform.tests.test_account_deletion_rules -v
"""

import unittest
from datetime import datetime

from qtt_platform import account_deletion_rules as r


class Rules(unittest.TestCase):
	def test_waits_seven_days(self):
		asked = datetime(2026, 10, 15, 10, 0)
		self.assertEqual(r.delete_on(asked), datetime(2026, 10, 22, 10, 0))
		self.assertFalse(r.is_due(asked, datetime(2026, 10, 22, 9, 59)))
		self.assertTrue(r.is_due(asked, datetime(2026, 10, 22, 10, 0)))
		self.assertFalse(r.is_due(None, datetime(2030, 1, 1)))

	def test_businesses(self):
		owned = [{"tenant": "T1", "name": "Acme Bakery", "others": 3}, {"tenant": "T2", "name": "Solo Shop", "others": 0}]
		self.assertEqual(r.blockers(owned), ["Acme Bakery"])  # people still work there: can't delete yet
		self.assertEqual(r.closes(owned), ["T2"])  # owned alone: closes with the account
		self.assertEqual(r.blockers([]), [])

	def test_devices_and_usage_go(self):
		self.assertIn("QTT Push Device", r.DELETE_ROWS)
		self.assertIn("QTT Trusted Device", r.DELETE_ROWS)


if __name__ == "__main__":
	unittest.main()
