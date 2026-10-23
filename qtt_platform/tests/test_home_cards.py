"""
Bench-independent tests for the home's adaptive action cards (qtt_platform.home_cards — pure).

	python -m unittest qtt_platform.tests.test_home_cards -v
"""

import unittest

from qtt_platform import home_cards as hc


def card(key, priority=50, **kw):
	return {"key": key, "title": key, "priority": priority, **kw}


class RankTest(unittest.TestCase):
	def test_highest_priority_first_and_limited(self):
		cards = [card(f"c{i}", i * 10) for i in range(10)]
		out = hc.rank(cards)
		self.assertEqual([c["key"] for c in out], ["c9", "c8", "c7", "c6", "c5", "c4"])

	def test_same_priority_more_urgent_tone_first(self):
		out = hc.rank([card("a", 50, tone="info"), card("b", 50, tone="danger"), card("c", 50, tone="warning")])
		self.assertEqual([c["key"] for c in out], ["b", "c", "a"])

	def test_dismissed_hidden_and_duplicates_merged(self):
		out = hc.rank([card("a", 30), card("a", 70), card("b", 50)], dismissed={"b"})
		self.assertEqual([(c["key"], c["priority"]) for c in out], [("a", 70)])

	def test_invalid_cards_dropped_and_values_cleaned(self):
		out = hc.rank([{"title": "no key"}, {"key": "no title"}, "junk",
					   card("x", 400, tone="loud", args={"n": 3, "bad": object()},
							action={"kind": "teleport", "target": "mars"})])
		self.assertEqual(len(out), 1)
		x = out[0]
		self.assertEqual((x["priority"], x["tone"], x["args"], x["action"]), (100, "info", {"n": 3}, None))

	def test_action_kept_with_default_label(self):
		x = hc.rank([card("x", action={"kind": "product", "target": "QTT_ORBITRA"})])[0]
		self.assertEqual(x["action"], {"label": "Open", "kind": "product", "target": "QTT_ORBITRA"})


class PlatformCardsTest(unittest.TestCase):
	def test_members_get_no_business_cards(self):
		self.assertEqual(hc.platform_cards(can_manage=False, sub_status="past_due", trial_days_left=1, profile_missing=["logo"], team_size=1), [])

	def test_owner_sees_what_needs_doing_in_order(self):
		out = hc.rank(hc.platform_cards(can_manage=True, sub_status="past_due", trial_days_left=3,
										profile_missing=["logo", "GSTIN"], team_size=1))
		self.assertEqual([c["key"] for c in out], ["billing.past_due", "billing.trial_ending", "profile.incomplete", "team.invite"])
		self.assertEqual(out[1]["args"], {"n": 3})
		self.assertEqual(out[2]["args"], {"missing": "logo, GSTIN"})

	def test_quiet_when_all_is_well(self):
		self.assertEqual(hc.platform_cards(can_manage=True, sub_status="active", trial_days_left=None, profile_missing=[], team_size=5), [])
		# trial far away: no card
		self.assertEqual(hc.platform_cards(can_manage=True, sub_status="trialing", trial_days_left=20, profile_missing=[], team_size=5), [])

	def test_whatsapp_number_card_for_owners_without_one(self):
		out = hc.platform_cards(can_manage=True, sub_status="active", trial_days_left=None, profile_missing=[], team_size=5, whatsapp_missing=True)
		self.assertEqual([c["key"] for c in out], ["whatsapp.verify"])
		self.assertEqual(out[0]["action"]["target"], "account.whatsapp")
		self.assertEqual(hc.platform_cards(can_manage=False, sub_status=None, trial_days_left=None, profile_missing=[], team_size=5,
										   whatsapp_missing=True), [])

if __name__ == "__main__":
	unittest.main()
