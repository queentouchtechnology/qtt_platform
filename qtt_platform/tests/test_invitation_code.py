"""Short invitation codes (qtt_platform.invitation_code) — no bench.

    python -m unittest qtt_platform.tests.test_invitation_code
"""

import unittest

from qtt_platform import invitation_code as c


class InvitationCodeTest(unittest.TestCase):
	def test_codes_are_short_and_without_look_alikes(self):
		codes = {c.new_code() for _ in range(500)}
		self.assertGreater(len(codes), 495)  # random
		for code in codes:
			self.assertEqual(len(code), 8)
			self.assertFalse(set(code) & set("0O1IL"))
			self.assertTrue(c.looks_like_code(code))

	def test_typing_doesnt_have_to_be_exact(self):
		self.assertEqual(c.normalize(" k7m2-qx9p "), "K7M2QX9P")
		self.assertEqual(c.normalize("K7M2 QX9P"), "K7M2QX9P")
		self.assertTrue(c.looks_like_code("k7m2-qx9p"))
		self.assertEqual(c.display("K7M2QX9P"), "K7M2-QX9P")

	def test_old_long_tokens_are_not_codes(self):
		self.assertFalse(c.looks_like_code("a" * 48))
		self.assertFalse(c.looks_like_code("K7M2-QX90"))  # 0 isn't in the alphabet
		self.assertFalse(c.looks_like_code(""))


if __name__ == "__main__":
	unittest.main()
