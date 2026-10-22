"""
QTT Studio › Business documents (PROJ-0012 S3) — the rules, no bench.

    python -m unittest qtt_platform.tests.test_docs_rules -v
"""

import json
import unittest

from qtt_platform.studio import docs_rules as rules


class Styles(unittest.TestCase):
	def test_free_style_without_studio(self):
		self.assertEqual(rules.style_for("classic", has_studio=False), "band")
		self.assertEqual(rules.style_for("classic", has_studio=True), "classic")
		self.assertEqual(rules.style_for("nonsense", has_studio=True), "band")
		self.assertEqual(rules.style_for(None, has_studio=True), "band")

	def test_every_style_has_its_colours(self):
		for s in rules.STYLES:
			c = rules.colours("#1d4ed8", s)
			self.assertEqual(set(c), {"head_bg", "head_ink", "head_muted", "th_bg", "th_ink", "soft", "tint", "deep"})

	def test_text_on_the_brand_colour_reads(self):
		self.assertEqual(rules.colours("#1d4ed8", "colour")["head_ink"], "#ffffff")  # dark blue → white words
		self.assertEqual(rules.colours("#fde047", "colour")["head_ink"], "#0B0D12")  # yellow → dark words
		self.assertEqual(rules.colours("#1d4ed8", "colour")["head_bg"], "#1d4ed8")
		self.assertEqual(rules.colours("#1d4ed8", "band")["head_bg"], "#0B0D12")  # QTT's own dark band


class Letter(unittest.TestCase):
	def test_prompt_never_invents(self):
		m = rules.letter_prompt(request="thank Mr Ravi for the order", to="Mr Ravi", brief="Sri Bakery, Madurai", language="en")
		system = m[0]["content"]
		for must in ("never invent", "[ ]", "JSON"):
			self.assertIn(must, system)
		self.assertIn("Sri Bakery", m[1]["content"])
		self.assertIn("Tamil", rules.letter_prompt(request="x", to="", brief="", language="ta")[0]["content"])

	def test_parse(self):
		d = rules.parse_letter("Sure! " + json.dumps({"subject": "Thanks", "greeting": "Dear Ravi,", "body": "One.\n\nTwo.", "closing": "Regards,"}))
		self.assertEqual(d["subject"], "Thanks")
		self.assertEqual(rules.paragraphs(d["body"]), ["One.", "Two."])
		self.assertIsNone(rules.parse_letter('{"subject": "x"}'))
		self.assertIsNone(rules.parse_letter("no json"))

	def test_paragraphs(self):
		self.assertEqual(rules.paragraphs("a\nb\n\n\n c \n\n"), ["a\nb", "c"])
		self.assertEqual(rules.paragraphs(""), [])


if __name__ == "__main__":
	unittest.main()
