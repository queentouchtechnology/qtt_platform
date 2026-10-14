"""Who may see what in a business (qtt_platform.abilities_rules) — no bench.

    python -m unittest qtt_platform.tests.test_abilities
"""

import unittest

from qtt_platform.abilities_rules import rules


class AbilitiesTest(unittest.TestCase):
	def test_owners_and_admins_see_everything(self):
		for role in ("Tenant Owner", "Tenant Admin"):
			self.assertEqual(rules(role, []), {"customers": True, "business": True})

	def test_an_office_pulse_employee_sees_neither(self):
		self.assertEqual(rules("Tenant Member", ["QTT_OFFICE_PULSE"]), {"customers": False, "business": False})
		self.assertEqual(rules("Tenant Member", []), {"customers": False, "business": False})

	def test_people_who_bill_or_chat_see_customers_not_the_business(self):
		self.assertEqual(rules("Tenant Member", ["QTT_ORBITRA"]), {"customers": True, "business": False})
		self.assertEqual(rules("Tenant Member", ["QTT_ONBOX", "QTT_OFFICE_PULSE"]), {"customers": True, "business": False})
		self.assertEqual(rules(None, ["QTT_SERVICES"]), {"customers": False, "business": False})


if __name__ == "__main__":
	unittest.main()
