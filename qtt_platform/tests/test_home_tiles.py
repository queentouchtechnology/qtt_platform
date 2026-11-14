"""
Bench-independent tests for the main dashboard's tiles and numbers (qtt_platform.home_tiles).

    python -m unittest qtt_platform.tests.test_home_tiles -v
"""

import unittest

from qtt_platform import home_tiles as h


def tile(key, label="X", order=None, **kw):
	t = {"key": key, "label": label, "icon": "apps", "open": {"kind": "screen", "target": "a.b"}, **kw}
	if order is not None:
		t["order"] = order
	return t


class TilesTest(unittest.TestCase):
	def test_sorted_by_order_then_label(self):
		out = h.tiles([tile("b", "Beta", 20), tile("a", "Alpha", 20), tile("z", "Zed", 10)])
		self.assertEqual([t["key"] for t in out], ["z", "a", "b"])

	def test_invalid_and_duplicates_dropped(self):
		out = h.tiles([tile("a"), tile("a", "Again"), {"key": "x", "label": "No open"}, tile("", "No key"),
					   {**tile("k"), "open": {"kind": "teleport", "target": "x"}}, "junk", None])
		self.assertEqual([t["key"] for t in out], ["a"])
		self.assertEqual(out[0]["label"], "X")

	def test_badge_and_tone_cleaned(self):
		t = h.tiles([tile("a", badge="3", tone="danger"), tile("b", badge=-2, tone="loud"), tile("c", badge="many")])
		self.assertEqual([(x["badge"], x["tone"]) for x in t], [(3, "danger"), (0, "info"), (0, "info")])

	def test_default_order_and_status_trim(self):
		t = h.tiles([tile("a", status="x" * 80)])[0]
		self.assertEqual(t["order"], 50)
		self.assertEqual(len(t["status"]), 40)


class ArrangeTest(unittest.TestCase):
	def test_no_layout_keeps_standard_order(self):
		out = h.arrange(h.tiles([tile("a", order=10), tile("b", order=20)]), None)
		self.assertEqual([(t["key"], t["hidden"]) for t in out], [("a", False), ("b", False)])

	def test_own_order_first_then_new_apps(self):
		base = h.tiles([tile("a", order=10), tile("b", order=20), tile("c", order=30), tile("new", order=5)])
		out = h.arrange(base, {"order": ["c", "a", "gone"], "hidden": ["b"]})
		self.assertEqual([t["key"] for t in out], ["c", "a", "new", "b"])
		self.assertEqual([t["key"] for t in out if t["hidden"]], ["b"])

	def test_clean_layout(self):
		lay = h.clean_layout(["a", "a", " b ", "", None, 3], "not a list")
		self.assertEqual(lay, {"order": ["a", "b", "3"], "hidden": []})
		self.assertEqual(len(h.clean_layout([f"k{i}" for i in range(99)], [])["order"]), h.MAX_LAYOUT_KEYS)


class NumbersTest(unittest.TestCase):
	def test_at_most_four_with_values(self):
		items = [{"key": f"k{i}", "value": i, "label": "n", "order": 10 - i} for i in range(6)] + [{"key": "e", "value": None, "label": "n"}]
		out = h.numbers(items)
		self.assertEqual(len(out), 4)
		self.assertEqual(out[0]["key"], "k5")
		self.assertEqual(out[0]["value"], "5")

	def test_trend_only_numeric(self):
		out = h.numbers([{"key": "a", "value": 1, "label": "x", "trend": 12}, {"key": "b", "value": 1, "label": "x", "trend": "up"}])
		self.assertEqual([n["trend"] for n in out], [12, None])


class FormatTest(unittest.TestCase):
	def test_money_short(self):
		self.assertEqual(h.money_short(950), "₹950")
		self.assertEqual(h.money_short(18420), "₹18.4K")
		self.assertEqual(h.money_short(230000), "₹2.3L")
		self.assertEqual(h.money_short(12000000), "₹1.2Cr")
		self.assertEqual(h.money_short(5000), "₹5K")

	def test_trend(self):
		self.assertEqual(h.trend(112, 100), 12)
		self.assertIsNone(h.trend(10, 0))


if __name__ == "__main__":
	unittest.main()
