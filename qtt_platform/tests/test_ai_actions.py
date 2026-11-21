import sys
import types
import unittest

sys.modules.setdefault("frappe", types.ModuleType("frappe"))

from qtt_platform import ai_actions as a  # noqa: E402
from qtt_platform import app_areas  # noqa: E402


class TestAiActions(unittest.TestCase):
	def test_catalogue(self):
		codes = [x[0] for x in a.ACTIONS]
		self.assertEqual(len(codes), len(set(codes)))  # one doc per code
		for code, label, area, product, counts, where in a.ACTIONS:
			self.assertRegex(code, r"^[a-z]+(\.[a-z_]+)+$")
			self.assertTrue(label and where)
			self.assertIn(area, app_areas.LABELS)
			self.assertIn(counts, (0, 1))
			self.assertTrue(product.startswith("QTT_"))

	def test_customer_replies_and_reports_dont_count(self):
		counts = {x[0]: x[4] for x in a.ACTIONS}
		self.assertEqual(counts["receptionist.reply"], 0)
		self.assertEqual(counts["whatsapp.daily.report"], 0)
		self.assertEqual(counts["content.article.write"], 1)


if __name__ == "__main__":
	unittest.main()
