"""
Push notifications: the Firebase values the app gets (app_config_logic.push_config — pure) and the message a
phone or browser gets (qtt_platform.push.message — imported against a fake frappe, sys.modules restored).

    python -m unittest qtt_platform.tests.test_push -v
"""

import importlib
import sys
import types
import unittest

from qtt_platform import app_config_logic as logic

FULL = {
	"firebase_project_id": "qtt-os", "firebase_sender_id": "123",
	"firebase_android_app_id": "1:123:android:a", "firebase_android_api_key": "AIza-android",
	"firebase_web_app_id": "1:123:web:w", "firebase_web_api_key": "AIza-web", "web_push_key": "BPk",
}


class PushConfigTest(unittest.TestCase):
	def test_nothing_until_project_and_sender(self):
		self.assertIsNone(logic.push_config({}))
		self.assertIsNone(logic.push_config({"firebase_project_id": "qtt-os"}))

	def test_each_platform_only_when_complete(self):
		self.assertEqual(logic.push_config(FULL), {
			"project_id": "qtt-os", "sender_id": "123",
			"android": {"app_id": "1:123:android:a", "api_key": "AIza-android"},
			"web": {"app_id": "1:123:web:w", "api_key": "AIza-web", "vapid_key": "BPk"},
		})
		no_web_key = {**FULL, "web_push_key": " "}
		self.assertNotIn("web", logic.push_config(no_web_key))  # a browser can't subscribe without it
		self.assertIn("android", logic.push_config(no_web_key))


class MessageTest(unittest.TestCase):
	def setUp(self):
		self._modules = dict(sys.modules)
		sys.modules["frappe"] = types.ModuleType("frappe")
		sys.modules["requests"] = types.ModuleType("requests")
		sys.modules.pop("qtt_platform.push", None)
		self.push = importlib.import_module("qtt_platform.push")

	def tearDown(self):
		for name in list(sys.modules):
			if name not in self._modules:
				del sys.modules[name]
		sys.modules.update(self._modules)

	def test_a_tap_on_the_web_opens_its_screen(self):
		m = self.push.message("tok", title="Leave: Asha", body="Waiting for you", data={"screen": "pulse.approvals", "tenant": "t1"},
							  web_app="https://staging.queentouchtech.in/app/")["message"]
		self.assertEqual(m["data"], {"screen": "pulse.approvals", "tenant": "t1"})
		self.assertEqual(m["webpush"]["fcm_options"]["link"], "https://staging.queentouchtech.in/app/#/?p=pulse.approvals")

	def test_no_screen_no_link_and_values_are_strings(self):
		m = self.push.message("tok", title="t", body="b", data={"n": 3, "x": None}, web_app="https://queentouchtech.in/app/")["message"]
		self.assertEqual(m["data"], {"n": "3", "x": ""})
		self.assertNotIn("fcm_options", m["webpush"])


if __name__ == "__main__":
	unittest.main()
