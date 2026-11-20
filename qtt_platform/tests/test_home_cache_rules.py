import sys
import types
import unittest

sys.modules.setdefault("frappe", types.ModuleType("frappe"))  # home_cache's pure rules don't need Frappe

from qtt_platform import home_cache as h  # noqa: E402


class TestHomeCacheRules(unittest.TestCase):
	def test_bumps(self):
		self.assertTrue(h.bumps("qtt_platform.api.leads.add", "POST", 200))
		self.assertTrue(h.bumps("resource:CRM Lead", "PUT", 200))
		self.assertTrue(h.bumps("qtt_platform.api.home.dismiss", "POST", 200))
		self.assertFalse(h.bumps("qtt_platform.api.leads.add", "POST", 417))  # refused: nothing changed
		self.assertFalse(h.bumps("qtt_platform.api.home.overview", "GET", 200))
		self.assertFalse(h.bumps("qtt_platform.api.analytics.ingest", "POST", 200))
		self.assertFalse(h.bumps("qtt_platform.api.perf.screens", "POST", 200))
		self.assertFalse(h.bumps("qtt_services.api.marketing_suggest.suggestions", "POST", 200))
		self.assertFalse(h.bumps(None, "POST", 200))

	def test_key_never_shared(self):
		a = h.key("overview", tenant="t1", user="a@x", access=0, change=0)
		self.assertNotEqual(a, h.key("overview", tenant="t1", user="b@x", access=0, change=0))
		self.assertNotEqual(a, h.key("overview", tenant="t2", user="a@x", access=0, change=0))
		self.assertNotEqual(a, h.key("overview", tenant="t1", user="a@x", access=1, change=0))
		self.assertNotEqual(a, h.key("overview", tenant="t1", user="a@x", access=0, change=1))
		self.assertNotEqual(a, h.key("actions", tenant="t1", user="a@x", access=0, change=0))


if __name__ == "__main__":
	unittest.main()
