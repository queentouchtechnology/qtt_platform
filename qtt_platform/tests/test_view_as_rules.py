"""View as rules (qtt_platform.view_as_rules — pure, no bench).

	python -m unittest qtt_platform.tests.test_view_as_rules
"""

import unittest

from qtt_platform import view_as_rules as rules


def why(**kw):
	args = {"owner": "o@x", "owner_role": "Tenant Owner", "target": "p@x", "target_member": True, "target_roles": ["Employee"]}
	return rules.can_view(**{**args, **kw})


class CanViewTest(unittest.TestCase):
	def test_the_owner_views_their_people(self):
		self.assertIsNone(why())
		self.assertIsNone(why(target_roles=["HR Manager", "Employee"]))

	def test_only_the_owner_and_never_staff_or_themselves(self):
		self.assertIsNotNone(why(owner_role="Tenant Admin"))
		self.assertIsNotNone(why(owner_role="Member"))
		self.assertIsNotNone(why(target="o@x"))
		self.assertIsNotNone(why(target_member=False))
		self.assertIsNotNone(why(target_roles=["System Manager"]))
		self.assertIsNotNone(why(target="Administrator"))


class RequestTest(unittest.TestCase):
	def test_reads_of_the_qtt_apps(self):
		for path in ("/api/method/qtt_platform.api.app_context.get", "/api/method/qtt_office_pulse.api.team.today",
					 "/api/method/qtt_orbitra.api.sales.list", "/api/method/frappe.auth.get_logged_user"):
			self.assertEqual(rules.request_allowed("GET", path), (True, ""), path)

	def test_nothing_is_changed_as_them(self):
		for m in ("POST", "PUT", "DELETE", "PATCH"):
			self.assertEqual(rules.request_allowed(m, "/api/method/qtt_office_pulse.api.leave.apply"), (False, "view_only"))

	def test_nothing_outside_the_qtt_apps(self):
		for path in ("/api/resource/Employee", "/api/method/frappe.client.get_list", "/private/files/x.pdf", "/app/user",
					 "/api/method/qtt_platform.api.view_as.start", "/api/method/qtt_platformx.evil"):
			self.assertEqual(rules.request_allowed("GET", path)[0], False, path)


if __name__ == "__main__":
	unittest.main()
