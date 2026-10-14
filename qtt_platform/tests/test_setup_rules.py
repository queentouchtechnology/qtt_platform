"""Set-up guides: order, the step to do now, progress (no bench).

    python -m unittest qtt_platform.tests.test_setup_rules
"""

import unittest

from qtt_platform.setup_rules import arrange


def step(key, stage, done=False):
	return {"key": key, "title": key, "why": "", "stage": stage, "done": done, "screen": key}


class ArrangeTest(unittest.TestCase):
	def test_the_first_unfinished_first_step_is_next(self):
		g = arrange([step("type", "first", True), step("team", "first"), step("shifts", "first"), step("leave", "next"), step("sites", "optional")])
		self.assertEqual(g["next"]["key"], "team")
		self.assertEqual((g["done"], g["total"], g["complete"]), (1, 4, False))  # optional doesn't count
		self.assertEqual([s["stage"] for s in g["stages"]], ["first", "next", "optional"])
		self.assertTrue(next(s for s in g["stages"][0]["steps"] if s["key"] == "team")["now"])

	def test_then_the_next_stage_then_nothing_nags(self):
		g = arrange([step("team", "first", True), step("leave", "next"), step("sites", "optional")])
		self.assertEqual(g["next"]["key"], "leave")
		g = arrange([step("team", "first", True), step("leave", "next", True), step("sites", "optional")])
		self.assertIsNone(g["next"])
		self.assertTrue(g["complete"])


if __name__ == "__main__":
	unittest.main()
