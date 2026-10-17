"""
QTT Admin → Usage rules — no bench.

    python -m unittest qtt_platform.tests.test_usage_dashboard -v
"""

import importlib
import sys
import types
import unittest

from qtt_platform import saas_admin_logic as logic


class DeepSeekSpend(unittest.TestCase):
	def setUp(self):
		self._modules = dict(sys.modules)
		frappe = types.ModuleType("frappe")
		frappe._ = lambda s: s
		frappe.whitelist = lambda **k: (lambda f: f)
		utils = types.ModuleType("frappe.utils")
		utils.get_datetime = utils.get_url = utils.now_datetime = lambda *a: None
		audit = types.ModuleType("qtt_platform.audit")
		audit.write_audit_event = lambda *a, **k: None
		guards = types.ModuleType("qtt_platform.tenant.guards")
		guards.require_platform_owner = lambda: None
		sys.modules.update({"frappe": frappe, "frappe.utils": utils, "qtt_platform.audit": audit, "qtt_platform.tenant.guards": guards})
		sys.modules.pop("qtt_platform.api.usage_dashboard", None)
		self.m = importlib.import_module("qtt_platform.api.usage_dashboard")

	def tearDown(self):
		sys.modules.clear()
		sys.modules.update(self._modules)

	def test_only_drops_count_and_split_by_day(self):
		points = [("2026-10-10 08:00", 5.00), ("2026-10-10 20:00", 4.40), ("2026-10-11 01:00", 4.10),
				  ("2026-10-11 09:00", 14.10),  # top-up: not spending
				  ("2026-10-11 18:00", 13.60)]
		self.assertEqual(self.m.deepseek_daily_spend(points), [{"date": "2026-10-10", "spent": 0.6}, {"date": "2026-10-11", "spent": 0.8}])
		self.assertEqual(self.m.deepseek_daily_spend([]), [])


class Attention(unittest.TestCase):
	def test_automation_items(self):
		items = logic.attention_items(automation=[{"what": "deepseek_low", "value": 0.95}, {"what": "n8n_errors", "value": 3}], today_str="2026-10-11")
		self.assertEqual([(i["kind"], i["what"], i["area"]) for i in items],
						 [("automation", "deepseek_low", "usage"), ("automation", "n8n_errors", "usage")])

	def test_whatsapp_items(self):
		items = logic.attention_items(whatsapp=[
			{"level": "info", "what": "wa_template_approved", "name": "qtt_report", "value": None},
			{"level": "critical", "what": "wa_quality", "name": "+91 95009 10005", "value": "Low"},
			{"level": "warning", "what": "wa_template_rejected", "name": "promo_x", "value": None}], today_str="2026-10-17")
		self.assertEqual([(i["level"], i["what"], i["area"], i["title"]) for i in items], [
			("critical", "wa_quality", "whatsapp_number", "+91 95009 10005"),
			("warning", "wa_template_rejected", "whatsapp_templates", "promo_x"),
			("info", "wa_template_approved", "whatsapp_templates", "qtt_report")])


class CacheAttention(unittest.TestCase):
	def test_website_cache_item(self):
		items = logic.attention_items(website_cache=[{"label": "Annapoorna Mess website", "tenant": "t1", "tenant_name": "Annapoorna", "task": "TASK-1"}],
									  today_str="2026-10-17")
		self.assertEqual([(i["kind"], i["level"], i["area"], i["target"], i["title"]) for i in items],
						 [("website_cache", "info", "clients", "t1", "Annapoorna Mess website")])

if __name__ == "__main__":
	unittest.main()
