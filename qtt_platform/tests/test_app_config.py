"""
Bench-independent tests for the QTT OS app's remote-config logic
(qtt_platform.app_config_logic — pure) and analytics event sanitising
(qtt_platform.api.analytics.sanitize_event, imported against a fake frappe
with sys.modules restored afterwards).

    python -m unittest qtt_platform.tests.test_app_config -v
"""

import importlib
import json
import sys
import types
import unittest

from qtt_platform import app_config_logic as logic


class VersionTest(unittest.TestCase):
	def test_parse(self):
		self.assertEqual(logic.parse_version("1.2.10+34"), (1, 2, 10))
		self.assertEqual(logic.parse_version("2"), (2, 0, 0))
		self.assertIsNone(logic.parse_version("abc"))
		self.assertIsNone(logic.parse_version(None))

	def test_compare_numerically_not_lexically(self):
		self.assertTrue(logic.version_lt("1.2.9", "1.2.10"))
		self.assertFalse(logic.version_lt("1.10.0", "1.9.0"))

	def test_unknown_versions_never_older(self):
		self.assertFalse(logic.version_lt(None, "1.0.0"))
		self.assertFalse(logic.version_lt("1.0.0", ""))


class FlagsTest(unittest.TestCase):
	FLAGS = [
		{"flag_key": "inbox.voice_notes", "enabled": 1, "platforms": "android, ios", "min_app_version": ""},
		{"flag_key": "admin.console", "enabled": 1, "platforms": "", "min_app_version": "1.3.0"},
		{"flag_key": "beta.off", "enabled": 0, "platforms": "", "min_app_version": ""},
	]

	def test_targeting(self):
		flags = logic.resolve_flags(self.FLAGS, "android", "1.2.0")
		self.assertEqual(flags, {"inbox.voice_notes": True, "admin.console": False, "beta.off": False})
		flags = logic.resolve_flags(self.FLAGS, "web", "1.3.1")
		self.assertEqual(flags, {"inbox.voice_notes": False, "admin.console": True, "beta.off": False})


class ThemeTest(unittest.TestCase):
	def test_payload_drops_invalid_colours_and_missing_modes(self):
		row = {"theme_key": "qtt-midnight", "label": "QTT Midnight", "corner_radius": 14, "supports_light": 0, "supports_dark": 1,
			   "dark_primary": "#3858f8", "dark_background": "not-a-colour"}
		payload = logic.theme_payload(row)
		self.assertEqual(payload["radius"], 14)
		self.assertNotIn("light", payload["modes"])
		self.assertEqual(payload["modes"]["dark"], {"primary": "#3858F8"})

	def test_default_themes_are_complete_and_valid(self):
		from qtt_platform.app_defaults import DEFAULT_THEMES

		keys = set()
		for theme in DEFAULT_THEMES:
			self.assertNotIn(theme["theme_key"], keys)
			keys.add(theme["theme_key"])
			for mode in ("light", "dark"):
				self.assertEqual(set(theme[mode]), set(logic.THEME_TOKENS), f"{theme['theme_key']} {mode}")
				for value in theme[mode].values():
					self.assertRegex(value, r"^#[0-9A-F]{6}$")
		self.assertIn("qtt-midnight", keys)


class UiOptionsTest(unittest.TestCase):
	def test_component_styles_fall_back_safely(self):
		payload = logic.theme_payload({"theme_key": "x", "supports_dark": 1, "card_style": "elevated", "input_style": "bogus"})
		self.assertEqual(payload["components"], {"card_style": "elevated", "input_style": "filled", "button_shape": "rounded"})

	def test_pick(self):
		self.assertEqual(logic.pick("compact", logic.DENSITIES, "standard"), "compact")
		self.assertEqual(logic.pick("tiny", logic.TEXT_SIZES, "standard"), "standard")
		self.assertEqual(logic.pick(None, logic.TEXT_SIZES, "standard"), "standard")

	def test_seeded_component_styles_are_valid(self):
		from qtt_platform.app_defaults import DEFAULT_THEMES

		for theme in DEFAULT_THEMES:
			for field, value in theme.get("components", {}).items():
				self.assertIn(value, logic.COMPONENT_STYLES[field], theme["theme_key"])


class MiscTest(unittest.TestCase):
	def test_rtl(self):
		for code in ("ar", "ar-EG", "he", "fa", "ur_PK"):
			self.assertTrue(logic.is_rtl(code), code)
		for code in ("en", "ta", "hi", "", None):
			self.assertFalse(logic.is_rtl(code), code)

	def test_update_policy(self):
		settings = {"min_app_version": "1.1.0", "latest_app_version": "1.4.0", "update_url_android": "https://play/x"}
		p = logic.update_policy(settings, "1.0.5", "android")
		self.assertTrue(p["force_update"])
		self.assertEqual(p["update_url"], "https://play/x")
		p = logic.update_policy(settings, "1.2.0", "web")
		self.assertFalse(p["force_update"])
		self.assertTrue(p["update_available"])

	def test_merge_and_version_hash(self):
		self.assertEqual(logic.merge_translations({"Hi": "Olá", "Bye": ""}, {"Hi": "Oi"}), {"Hi": "Oi"})
		self.assertEqual(logic.content_version({"a": 1, "b": 2}), logic.content_version({"b": 2, "a": 1}))


class SanitizeEventTest(unittest.TestCase):
	def setUp(self):
		self._modules = dict(sys.modules)
		fake = types.ModuleType("frappe")
		fake._ = lambda s: s
		fake.whitelist = lambda *a, **k: (lambda fn: fn)
		fake.utils = types.SimpleNamespace(get_datetime=lambda v: v)
		sys.modules["frappe"] = fake
		for name in [n for n in sys.modules if n.startswith("qtt_platform.") and "tests" not in n]:
			sys.modules.pop(name)
		self.analytics = importlib.import_module("qtt_platform.api.analytics")

	def tearDown(self):
		for name in list(sys.modules):
			if name not in self._modules:
				del sys.modules[name]
		sys.modules.update(self._modules)

	def test_valid_event(self):
		e = self.analytics.sanitize_event(
			{"name": "inbox.message_sent", "screen": "chat", "product": "QTT_ONBOX", "props": {"private": True, "len": 12}}
		)
		self.assertEqual(e["event"], "inbox.message_sent")
		self.assertEqual(e["product"], "QTT_ONBOX")
		self.assertEqual(json.loads(e["properties"]), {"private": True, "len": 12})

	def test_rejects_bad_names_and_strips_unsafe_props(self):
		self.assertIsNone(self.analytics.sanitize_event({"name": "Bad Name!"}))
		self.assertIsNone(self.analytics.sanitize_event("nope"))
		e = self.analytics.sanitize_event(
			{"name": "app.open", "product": "lower_case", "props": {"nested": {"x": 1}, "list": [1], "text": "x" * 500}}
		)
		self.assertIsNone(e["product"])
		props = json.loads(e["properties"])
		self.assertEqual(set(props), {"text"})
		self.assertEqual(len(props["text"]), self.analytics.MAX_VALUE_LENGTH)

	def test_property_count_capped(self):
		e = self.analytics.sanitize_event({"name": "app.open", "props": {f"k{i}": i for i in range(50)}})
		self.assertEqual(len(json.loads(e["properties"])), self.analytics.MAX_PROPERTIES)


if __name__ == "__main__":
	unittest.main()


class SeedTranslationsTest(unittest.TestCase):
	"""qtt_platform/app_i18n/<lang>.json — seeded into Frappe Translation
	(context qtt_app). Placeholders like {name} must survive translation."""

	def test_files_are_valid_and_keep_placeholders(self):
		import pathlib
		import re

		folder = pathlib.Path(__file__).resolve().parents[1] / "app_i18n"
		files = sorted(folder.glob("*.json"))
		self.assertTrue(files)
		placeholder = re.compile(r"\{[a-z_]+\}")
		for path in files:
			with self.subTest(language=path.stem):
				data = json.loads(path.read_text(encoding="utf-8"))
				self.assertIsInstance(data, dict)
				for source, translated in data.items():
					self.assertTrue(translated.strip(), source)
					self.assertEqual(sorted(placeholder.findall(source)), sorted(placeholder.findall(translated)), source)
