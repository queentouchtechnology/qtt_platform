"""
Bench-independent tests for one-time codes (qtt_platform.otp_logic — pure).

    python -m unittest qtt_platform.tests.test_otp_logic -v
"""

import unittest

from qtt_platform import otp_logic as logic

SECRET = "s3cret"


class NormalizeTest(unittest.TestCase):
	def test_email(self):
		self.assertEqual(logic.normalize_target("email", "  Owner@Shop.IN "), "owner@shop.in")
		with self.assertRaises(logic.OtpError) as ctx:
			logic.normalize_target("email", "nope")
		self.assertEqual(ctx.exception.code, "INVALID_EMAIL")

	def test_phone(self):
		self.assertEqual(logic.normalize_target("whatsapp", "95009 10005"), "+919500910005")
		self.assertEqual(logic.normalize_target("whatsapp", "+971 50 123 4567"), "+971501234567")
		for bad in ("", "12345", "+1234567890123456"):
			with self.assertRaises(logic.OtpError):
				logic.normalize_target("whatsapp", bad)

	def test_unknown_channel(self):
		with self.assertRaises(logic.OtpError) as ctx:
			logic.normalize_target("sms", "x")
		self.assertEqual(ctx.exception.code, "INVALID_CHANNEL")

	def test_mask_hides_most(self):
		self.assertEqual(logic.mask("email", "owner@shop.in"), "ow•••@shop.in")
		self.assertEqual(logic.mask("whatsapp", "+919500910005"), "+91••••••0005")


class IssueVerifyTest(unittest.TestCase):
	def _issue(self, now=1000.0, state=None, code="123456", target="+919500910005"):
		return logic.issue(SECRET, "signup", "whatsapp", target, state, now, code=code)

	def test_code_is_six_random_digits(self):
		codes = {logic.new_code() for _ in range(50)}
		self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))
		self.assertGreater(len(codes), 40)

	def test_only_a_hash_is_stored(self):
		_, state = self._issue()
		self.assertNotIn("123456", str(state))

	def test_right_code_verifies_once(self):
		_, state = self._issue()
		state = logic.verify(SECRET, "signup", "whatsapp", "+919500910005", " 123 456 ", state, 1100)
		with self.assertRaises(logic.OtpError) as ctx:
			logic.verify(SECRET, "signup", "whatsapp", "+919500910005", "123456", state, 1101)
		self.assertEqual(ctx.exception.code, "NO_CODE")

	def test_code_is_bound_to_target_and_purpose(self):
		_, state = self._issue()
		with self.assertRaises(logic.OtpError):
			logic.verify(SECRET, "signup", "whatsapp", "+919999999999", "123456", state, 1100)
		with self.assertRaises(logic.OtpError):
			logic.verify(SECRET, "reset", "whatsapp", "+919500910005", "123456", state, 1100)

	def test_expiry(self):
		_, state = self._issue()
		with self.assertRaises(logic.OtpError) as ctx:
			logic.verify(SECRET, "signup", "whatsapp", "+919500910005", "123456", state, 1000 + logic.CODE_TTL + 1)
		self.assertEqual(ctx.exception.code, "EXPIRED")

	def test_wrong_tries_lock_the_code(self):
		_, state = self._issue()
		for left in range(logic.MAX_ATTEMPTS - 1, -1, -1):
			with self.assertRaises(logic.OtpError) as ctx:
				logic.verify(SECRET, "signup", "whatsapp", "+919500910005", "000000", state, 1100)
			self.assertEqual(ctx.exception.extra["left"], left)
			state = ctx.exception.extra["state"]
		with self.assertRaises(logic.OtpError) as ctx:
			logic.verify(SECRET, "signup", "whatsapp", "+919500910005", "123456", state, 1100)
		self.assertEqual(ctx.exception.code, "LOCKED")

	def test_resend_waits_and_hourly_cap(self):
		_, state = self._issue(now=1000)
		with self.assertRaises(logic.OtpError) as ctx:
			self._issue(now=1030, state=state)
		self.assertEqual(ctx.exception.code, "TOO_SOON")
		self.assertEqual(ctx.exception.extra["wait"], 31)
		now = 1000
		for _ in range(logic.MAX_SENDS_PER_HOUR - 1):
			now += logic.RESEND_AFTER
			_, state = self._issue(now=now, state=state)
		with self.assertRaises(logic.OtpError) as ctx:
			self._issue(now=now + logic.RESEND_AFTER, state=state)
		self.assertEqual(ctx.exception.code, "TOO_MANY")
		_, state = self._issue(now=1000 + 3600 + 1, state=state)  # an hour later the oldest drops off

	def test_new_code_replaces_old(self):
		_, state = self._issue(now=1000, code="111111")
		_, state = self._issue(now=1100, state=state, code="222222")
		with self.assertRaises(logic.OtpError):
			logic.verify(SECRET, "signup", "whatsapp", "+919500910005", "111111", state, 1110)
		logic.verify(SECRET, "signup", "whatsapp", "+919500910005", "222222", state, 1110)


if __name__ == "__main__":
	unittest.main()
