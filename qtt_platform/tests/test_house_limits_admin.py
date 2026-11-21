import sys
import types
import unittest

for name in ("frappe",):
	sys.modules.setdefault(name, types.ModuleType(name))


class TestCleanLimits(unittest.TestCase):
	def setUp(self):
		import importlib

		fr = sys.modules["frappe"]
		fr._ = lambda s: s
		fr.whitelist = lambda **k: (lambda f: f)
		for mod in ("qtt_platform.audit", "qtt_platform.tenant.guards"):
			m = types.ModuleType(mod)
			m.write_audit_event = lambda *a, **k: None
			m.require_platform_owner = lambda: None
			sys.modules.setdefault(mod, m)
		self.s = importlib.import_module("qtt_platform.api.admin_settings")

	def test_clean(self):
		products = {"QTT_ORBITRA": {"max_users", "max_items"}}
		rows = self.s.clean_limits([
			{"product": "QTT_ORBITRA", "limit_key": "max_users", "limit_value": "25", "note": "  QTT  team "},
			{"product": "QTT_ORBITRA", "limit_key": "max_users", "limit_value": "30"},  # the same app+key again: the first wins
			{"product": "QTT_ORBITRA", "limit_key": "max_items", "limit_value": "Unlimited"},
		], products)
		self.assertEqual(rows, [
			{"product": "QTT_ORBITRA", "limit_key": "max_users", "limit_value": "25", "note": "QTT team"},
			{"product": "QTT_ORBITRA", "limit_key": "max_items", "limit_value": "unlimited", "note": None},
		])
		with self.assertRaises(ValueError):
			self.s.clean_limits([{"product": "QTT_ORBITRA", "limit_key": "nope", "limit_value": "1"}], products)
		with self.assertRaises(ValueError):
			self.s.clean_limits([{"product": "QTT_ORBITRA", "limit_key": "max_users", "limit_value": "-5"}], products)
		self.assertEqual(self.s.clean_limits([], products), [])


if __name__ == "__main__":
	unittest.main()
