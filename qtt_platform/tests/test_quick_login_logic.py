"""
Bench-independent tests for one-time sign-in rules (qtt_platform.quick_login_logic — pure).

    python -m unittest qtt_platform.tests.test_quick_login_logic -v
"""

import unittest

from qtt_platform import quick_login_logic as logic

WEB = "52903987029-web.apps.googleusercontent.com"
NOW = 1_800_000_000


def claims(**over):
	c = {"aud": WEB, "iss": "https://accounts.google.com", "exp": str(NOW + 600), "email": "Owner@Shop.in",
		 "email_verified": "true", "name": "Owner One"}
	c.update(over)
	return c


class GoogleClaimsTest(unittest.TestCase):
	def test_good_token(self):
		self.assertEqual(logic.check_google_claims(claims(), [WEB], NOW), ("owner@shop.in", "Owner One"))

	def test_name_from_parts(self):
		c = claims(name=None, given_name="Owner", family_name="One")
		self.assertEqual(logic.check_google_claims(c, [WEB], NOW)[1], "Owner One")

	def test_refusals(self):
		cases = {
			"wrong app": (claims(aud="someone-elses-app"), "GOOGLE_INVALID"),
			"not google": (claims(iss="evil.example"), "GOOGLE_INVALID"),
			"expired": (claims(exp=str(NOW - 1)), "GOOGLE_EXPIRED"),
			"bad exp": (claims(exp="soon"), "GOOGLE_EXPIRED"),
			"unverified": (claims(email_verified="false"), "GOOGLE_UNVERIFIED"),
			"no email": (claims(email=""), "GOOGLE_UNVERIFIED"),
			"google error": ({"error": "invalid_token"}, "GOOGLE_INVALID"),
			"empty": ({}, "GOOGLE_INVALID"),
		}
		for label, (c, code) in cases.items():
			with self.subTest(label), self.assertRaises(logic.QuickLoginError) as ctx:
				logic.check_google_claims(c, [WEB], NOW)
			self.assertEqual(ctx.exception.code, code)

	def test_no_audience_configured_refuses_everything(self):
		with self.assertRaises(logic.QuickLoginError):
			logic.check_google_claims(claims(aud=""), [], NOW)

	def test_audiences(self):
		self.assertEqual(logic.audiences(WEB, "a.apps\n b.apps , a.apps\n\n"), [WEB, "a.apps", "b.apps"])
		self.assertEqual(logic.audiences(None, None), [])


class DeviceSecretTest(unittest.TestCase):
	def test_secret_is_long_random_and_only_hash_matches(self):
		a, b = logic.new_secret(), logic.new_secret()
		self.assertNotEqual(a, b)
		self.assertGreaterEqual(len(a), 40)
		h = logic.secret_hash(a)
		self.assertNotIn(a, h)
		self.assertTrue(logic.secret_matches(h, a))
		self.assertFalse(logic.secret_matches(h, b))
		self.assertFalse(logic.secret_matches(h, ""))
		self.assertFalse(logic.secret_matches(None, a))

	def test_idle(self):
		day = 86400
		self.assertFalse(logic.idle_too_long(NOW - 89 * day, NOW))
		self.assertTrue(logic.idle_too_long(NOW - 91 * day, NOW))
		self.assertFalse(logic.idle_too_long(None, NOW))


if __name__ == "__main__":
	unittest.main()
