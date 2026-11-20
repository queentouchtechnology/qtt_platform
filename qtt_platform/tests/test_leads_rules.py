"""
Bench-independent tests for the Content Hub's leads (qtt_platform.leads_rules — pure).

    python -m unittest qtt_platform.tests.test_leads_rules -v
"""

import unittest
from datetime import datetime, timedelta

from qtt_platform import leads_rules as r

NOW = datetime(2026, 11, 20, 10, 30)  # a Friday


class StageTest(unittest.TestCase):
	def test_lead_and_deal_statuses(self):
		self.assertEqual(r.stage("CRM Lead", "New"), "New")
		for s in ("Contacted", "Nurture", "Qualified"):
			self.assertEqual(r.stage("CRM Lead", s), "Talking")
		self.assertEqual(r.stage("CRM Lead", "Junk"), "Lost")
		self.assertEqual(r.stage("CRM Deal", "Proposal/Quotation"), "Quote sent")
		self.assertEqual(r.stage("CRM Deal", "Negotiation"), "Quote sent")
		self.assertEqual(r.stage("CRM Deal", "Won"), "Won")
		self.assertEqual(r.stage("CRM Deal", "Lost"), "Lost")


class TodoTest(unittest.TestCase):
	def test_due_today_or_overdue(self):
		self.assertTrue(r.on_todo("Talking", NOW - timedelta(days=30), NOW + timedelta(hours=5), NOW))
		self.assertTrue(r.on_todo("Quote sent", NOW - timedelta(days=30), NOW - timedelta(days=2), NOW))
		self.assertFalse(r.on_todo("Talking", NOW - timedelta(days=30), NOW + timedelta(days=1), NOW))

	def test_new_without_a_step_for_three_days(self):
		self.assertTrue(r.on_todo("New", NOW - timedelta(days=1), None, NOW))
		self.assertFalse(r.on_todo("New", NOW - timedelta(days=5), None, NOW))
		self.assertFalse(r.on_todo("Talking", NOW - timedelta(days=1), None, NOW))

	def test_closed_never(self):
		self.assertFalse(r.on_todo("Won", NOW, NOW, NOW))
		self.assertFalse(r.on_todo("Lost", NOW, NOW, NOW))


class NextLineTest(unittest.TestCase):
	def test_task_and_overdue(self):
		self.assertEqual(r.next_line("Talking", "Send the quote", NOW - timedelta(hours=1), NOW, None), ("Send the quote", True))
		self.assertEqual(r.next_line("Talking", "Call", NOW + timedelta(hours=1), NOW, None), ("Call", False))

	def test_without_a_task(self):
		self.assertEqual(r.next_line("New", None, None, NOW, "WhatsApp"), ("Say hello · came on {source}", False))
		self.assertEqual(r.next_line("New", None, None, NOW, None), ("Say hello", False))
		self.assertEqual(r.next_line("Quote sent", None, None, NOW, None)[0], "Ask if the quote is OK")


class RemindTest(unittest.TestCase):
	def test_choices(self):
		self.assertEqual(r.remind_at("2h", NOW), datetime(2026, 11, 20, 12, 30))
		self.assertEqual(r.remind_at("tomorrow", NOW), datetime(2026, 11, 21, 9, 0))
		self.assertEqual(r.remind_at("week", NOW), datetime(2026, 11, 23, 9, 0))  # next Monday
		self.assertEqual(r.remind_at("day", NOW, datetime(2026, 11, 25)), datetime(2026, 11, 25, 9, 0))

	def test_a_day_in_the_past(self):
		with self.assertRaises(r.LeadError):
			r.remind_at("day", NOW, datetime(2026, 11, 19))
		with self.assertRaises(r.LeadError):
			r.remind_at("soon", NOW)


class CleanLeadTest(unittest.TestCase):
	def test_name_and_a_way_to_reach(self):
		v = r.clean_lead({"name": " Karthik  Raja ", "phone": "+91 98400 12345", "need": "400 gift boxes", "value": "200000", "source": "Walk-in"})
		self.assertEqual((v["first_name"], v["last_name"], v["mobile_no"]), ("Karthik", "Raja", "+919840012345"))
		self.assertEqual((v["qtt_need"], v["annual_revenue"], v["source"]), ("400 gift boxes", 200000.0, "Walk In"))

	def test_missing_or_wrong(self):
		for data, msg in [({"phone": "98400"}, "name"), ({"name": "A"}, "phone number or an email"), ({"name": "A", "phone": "12"}, "phone"),
						  ({"name": "A", "email": "nope"}, "email"), ({"name": "A", "phone": "9840012345", "value": "lots"}, "number")]:
			with self.assertRaisesRegex(r.LeadError, msg):
				r.clean_lead(data)

	def test_unknown_source_dropped(self):
		self.assertIsNone(r.clean_lead({"name": "A", "email": "a@b.in", "source": "Spam"})["source"])


class QuoteTest(unittest.TestCase):
	def test_totals(self):
		q = r.clean_quote([{"name": "Gift box", "qty": 400, "rate": 490}, {"name": "Name sticker", "qty": 400, "rate": 10}, {"name": ""}], 5)
		self.assertEqual((q["net"], q["tax"], q["total"]), (200000.0, 10000.0, 210000.0))
		self.assertEqual(len(q["rows"]), 2)

	def test_wrong(self):
		with self.assertRaisesRegex(r.LeadError, "at least one"):
			r.clean_quote([], 0)
		with self.assertRaisesRegex(r.LeadError, "quantity"):
			r.clean_quote([{"name": "Box", "qty": 0, "rate": 1}], 0)
		with self.assertRaisesRegex(r.LeadError, "GST"):
			r.clean_quote([{"name": "Box", "qty": 1, "rate": 1}], 40)

	def test_money_and_message(self):
		self.assertEqual(r.money(210000), "₹2,10,000")
		self.assertEqual(r.money(12345678.5), "₹1,23,45,678.50")
		self.assertEqual(r.money(999), "₹999")
		self.assertEqual(r.money(1200, "AED"), "AED 1,200")
		q = r.clean_quote([{"name": "Gift box", "qty": 2, "rate": 500}], 5)
		m = r.quote_message("Karthik", "Sri Sweets", q)
		self.assertIn("• Gift box × 2 — ₹1,000", m)
		self.assertIn("• GST 5% — ₹50", m)
		self.assertIn("Total: ₹1,050", m)
		self.assertTrue(m.endswith("Thank you — Sri Sweets"))
		self.assertNotIn("PDF", m)
		m2 = r.quote_message("Karthik", "Sri Sweets", q, pdf_url="https://x.in/files/Quote-ab.pdf")
		self.assertIn("The quote (PDF): https://x.in/files/Quote-ab.pdf", m2)

	def test_phone_key(self):
		self.assertEqual(r.phone_key("+91 98400 12345"), "9840012345")
		self.assertEqual(r.phone_key("098400-12345"), "9840012345")
		self.assertEqual(r.phone_key("12345"), "")


if __name__ == "__main__":
	unittest.main()
