"""Apps billed by invoice (qtt_platform.invoice_billing_rules) — no bench.

    python -m unittest qtt_platform.tests.test_invoice_billing_rules -v
"""

import unittest
from datetime import date

from qtt_platform import invoice_billing_rules as r


class Rules(unittest.TestCase):
	def test_periods(self):
		self.assertEqual(r.months_for("monthly"), 1)
		self.assertEqual(r.months_for("yearly"), 12)
		self.assertEqual(r.months_for(None), 1)
		self.assertEqual(r.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
		self.assertEqual(r.add_months(date(2026, 10, 16), 12), date(2027, 10, 16))

	def test_paying_extends_from_where_it_ended(self):
		today = date(2026, 10, 16)
		self.assertEqual(r.paid_through(today, today, 1), date(2026, 11, 16))  # the first invoice
		self.assertEqual(r.paid_through(date(2026, 11, 16), date(2026, 11, 14), 1), date(2026, 12, 16))  # renewal paid early
		self.assertEqual(r.paid_through(date(2026, 9, 1), today, 1), date(2026, 11, 16))  # ran out: from today

	def test_next_step(self):
		kw = dict(status="active", price=999, cancelling=False)
		paid = date(2026, 11, 16)
		self.assertIsNone(r.next_step(**kw, paid_until=paid, has_open_invoice=False, today=date(2026, 11, 12)))
		self.assertEqual(r.next_step(**kw, paid_until=paid, has_open_invoice=False, today=date(2026, 11, 13)), "invoice")  # 3 days before
		self.assertIsNone(r.next_step(**kw, paid_until=paid, has_open_invoice=True, today=date(2026, 11, 23)))  # within 7 days after
		self.assertEqual(r.next_step(**kw, paid_until=paid, has_open_invoice=True, today=date(2026, 11, 24)), "suspend")
		self.assertIsNone(r.next_step(status="suspended", price=999, cancelling=False, paid_until=paid, has_open_invoice=True, today=date(2026, 12, 30)))
		self.assertIsNone(r.next_step(**{**kw, "price": 0}, paid_until=paid, has_open_invoice=False, today=date(2026, 11, 20)))  # free plan
		self.assertIsNone(r.next_step(**{**kw, "cancelling": True}, paid_until=paid, has_open_invoice=False, today=date(2026, 11, 15)))

	def test_line(self):
		self.assertEqual(r.line("Orbitra", "Growth", date(2026, 10, 16), 1, 999),
						 {"description": "Orbitra — Growth, 16 Oct 2026 to 15 Nov 2026", "amount": 999.0})


if __name__ == "__main__":
	unittest.main()
