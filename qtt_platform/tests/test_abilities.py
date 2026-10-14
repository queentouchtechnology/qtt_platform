"""Who may see what in a business (qtt_platform.abilities_rules) — no bench.

    python -m unittest qtt_platform.tests.test_abilities
"""

import unittest

from qtt_platform.abilities_rules import rules


def seen(*args, **kw):
	r = rules(*args, **kw)
	return {"customers": r["customers"], "business": r["business"]}


class AbilitiesTest(unittest.TestCase):
	def test_owners_and_admins_see_everything(self):
		for role in ("Tenant Owner", "Tenant Admin"):
			self.assertEqual(seen(role, []), {"customers": True, "business": True})

	def test_an_office_pulse_employee_sees_neither(self):
		self.assertEqual(seen("Tenant Member", ["QTT_OFFICE_PULSE"]), {"customers": False, "business": False})
		self.assertEqual(seen("Tenant Member", []), {"customers": False, "business": False})

	def test_people_who_bill_or_chat_see_customers_not_the_business(self):
		self.assertEqual(seen("Tenant Member", ["QTT_ORBITRA"]), {"customers": True, "business": False})
		self.assertEqual(seen("Tenant Member", ["QTT_ONBOX", "QTT_OFFICE_PULSE"]), {"customers": True, "business": False})
		self.assertEqual(seen(None, ["QTT_SERVICES"]), {"customers": False, "business": False})

	def test_customers_live_in_orbitra_only_when_its_role_can_use_them(self):
		self.assertTrue(rules("Tenant Owner", ["QTT_ORBITRA", "QTT_ONBOX"], orbitra_customers=True)["customers_in_orbitra"])
		self.assertFalse(rules("Tenant Member", ["QTT_ORBITRA"], orbitra_customers=False)["customers_in_orbitra"])  # switched off: the shared list stays
		self.assertFalse(rules("Tenant Member", ["QTT_ONBOX"], orbitra_customers=True)["customers_in_orbitra"])  # Onbox only: the shared list
		self.assertFalse(rules("Tenant Owner", [])["customers_in_orbitra"])  # no Orbitra: the shared list


if __name__ == "__main__":
	unittest.main()
