import unittest

from qtt_platform import app_areas as a


class TestAppAreas(unittest.TestCase):
	def test_screens(self):
		self.assertEqual(a.area("pulse.team"), "hr")
		self.assertEqual(a.area("orbitra.pos"), "erp")
		self.assertEqual(a.area("services.marketing.leads"), "content")
		self.assertEqual(a.area("services.marketing.content"), "content")
		self.assertEqual(a.area("services.marketing.social"), "social")
		self.assertEqual(a.area("services.store.orders"), "store")
		self.assertEqual(a.area("services.sites"), "website")
		self.assertEqual(a.area("services.whatsapp"), "whatsapp")
		self.assertEqual(a.area("services.intro"), "suite")
		self.assertEqual(a.area("p:QTT_ONBOX"), "inbox")
		self.assertEqual(a.area("team.chat"), "team")
		self.assertEqual(a.area("admin.servers"), "admin")
		self.assertEqual(a.area("home"), "os")
		self.assertEqual(a.area("/"), "os")

	def test_product_and_no_screen(self):
		self.assertEqual(a.area(None, "QTT_ORBITRA"), "erp")
		self.assertEqual(a.area(None, None), "os")  # app.open, auth.login
		self.assertEqual(a.area("pulse.leave", "QTT_SERVICES"), "hr")  # the screen wins
		self.assertEqual(a.product_for("hr", None), "QTT_OFFICE_PULSE")
		self.assertEqual(a.product_for("hr", "X"), "X")
		self.assertIsNone(a.product_for("os", None))

	def test_calls(self):
		self.assertEqual(a.area_of_call("qtt_office_pulse.api.session.bootstrap"), "hr")
		self.assertEqual(a.area_of_call("qtt_services.api.marketing.write_article"), "content")
		self.assertEqual(a.area_of_call("qtt_services.api.marketing.posts"), "social")
		self.assertEqual(a.area_of_call("qtt_services.api.store_hooks.ingest"), "store")
		self.assertEqual(a.area_of_call("qtt_services.api.my_whatsapp.setup"), "whatsapp")
		self.assertEqual(a.area_of_call("qtt_platform.api.leads.overview"), "content")
		self.assertEqual(a.area_of_call("qtt_platform.api.studio_admin.list"), "admin")
		self.assertEqual(a.area_of_call("qtt_platform.api.studio.home"), "studio")
		self.assertEqual(a.area_of_call("qtt_services.api.portal.x"), "suite")
		self.assertEqual(a.area_of_call("qtt_platform.api.home.overview"), "os")
		self.assertEqual(a.area_of_call("resource:CRM Lead"), "os")
		for key in list(a.FREE_KEYS) + list(a.PLAN_KEYS):
			self.assertIn(key, a.LABELS)

	def test_every_area_has_a_label(self):
		for key, _l, _p, _s in a.AREAS:
			self.assertIn(key, a.LABELS)


if __name__ == "__main__":
	unittest.main()
