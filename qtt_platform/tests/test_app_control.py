"""
Bench-independent tests for QTT Admin → App control input rules
(qtt_platform.app_control_logic — no frappe import).

    python -m unittest qtt_platform.tests.test_app_control -v
"""

import unittest

from qtt_platform import app_control_logic as logic
from qtt_platform.app_control_logic import ControlInputError


class SectionTest(unittest.TestCase):
	def test_status_cleans_and_coerces(self):
		clean = logic.clean_section("status", {
			"maintenance_mode": "true", "maintenance_message": "  Back at 10:00  ",
			"announcement": "", "announcement_level": "warning",
		})
		self.assertEqual(clean, {"maintenance_mode": 1, "maintenance_message": "Back at 10:00",
								 "announcement": "", "announcement_level": "warning"})

	def test_rejects_fields_outside_the_section(self):
		with self.assertRaises(ControlInputError):
			logic.clean_section("status", {"min_app_version": "9.9.9"})
		with self.assertRaises(ControlInputError):
			logic.clean_section("secrets", {})

	def test_versions(self):
		ok = logic.clean_section("versions", {"min_app_version": "1.2.0", "latest_app_version": "1.3.0",
											  "update_url_android": "https://play.google.com/store/apps/details?id=in.queentouchtech.qtt"})
		self.assertEqual(ok["min_app_version"], "1.2.0")
		bad = [
			{"min_app_version": "one"},
			{"min_app_version": "2.0.0", "latest_app_version": "1.9.9"},
			{"update_url_ios": "http://example.com"},
			{"update_url_desktop": "javascript:alert(1)"},
		]
		for values in bad:
			with self.subTest(values=values), self.assertRaises(ControlInputError):
				logic.clean_section("versions", values)

	def test_choices_and_numbers(self):
		with self.assertRaises(ControlInputError):
			logic.clean_section("defaults", {"default_text_size": "huge"})
		with self.assertRaises(ControlInputError):
			logic.clean_section("analytics", {"analytics_flush_seconds": "1"})
		with self.assertRaises(ControlInputError):
			logic.clean_section("analytics", {"analytics_retention_days": "abc"})
		self.assertEqual(logic.clean_section("analytics", {"analytics_flush_seconds": "30"}), {"analytics_flush_seconds": 30})
		self.assertEqual(logic.clean_section("defaults", {"default_theme": ""}), {"default_theme": None})

	def test_long_messages_rejected(self):
		with self.assertRaises(ControlInputError):
			logic.clean_section("status", {"announcement": "x" * 501})


class FlagTest(unittest.TestCase):
	def test_normalises(self):
		flag = logic.clean_flag({"flag_key": " Inbox.Voice_Notes ", "enabled": True, "platforms": "ios, Android,ios", "min_app_version": "1.2"})
		self.assertEqual(flag, {"flag_key": "inbox.voice_notes", "enabled": 1, "platforms": "android, ios",
								"min_app_version": "1.2", "description": ""})

	def test_rejects_bad_input(self):
		for bad in ({"flag_key": "has space"}, {"flag_key": "x"}, {"flag_key": "ok.key", "platforms": "symbian"},
					{"flag_key": "ok.key", "min_app_version": "latest"}):
			with self.subTest(bad=bad), self.assertRaises(ControlInputError):
				logic.clean_flag(bad)


class ChangesTest(unittest.TestCase):
	def test_only_changed_fields(self):
		old, new = logic.changes({"a": 1, "b": "x", "c": None}, {"a": 1, "b": "y", "c": ""})
		self.assertEqual((old, new), ({"b": "x"}, {"b": "y"}))


if __name__ == "__main__":
	unittest.main()
