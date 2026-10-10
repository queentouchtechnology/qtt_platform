"""
Remote configuration for the QTT OS client app. Everything the app looks
like and can do — themes, languages + translations, feature flags,
announcements, maintenance mode, minimum app version, analytics settings —
is read from here at startup, cached on the device, and re-read whenever
the server broadcasts `qtt:config_changed`. Changing any of it in Desk
reaches running apps without a release.

Sources (existing Frappe DocTypes reused wherever they fit):
  Language     enabled languages            (frappe core)
  Translation  app strings, context=qtt_app  (frappe core — scoped so Desk
                                             translations are untouched)
  Currency     symbols / number formats      (frappe core)
  QTT App Settings / QTT App Theme           (this app)

get_app_config is guest-accessible on purpose: the login screen needs the
theme and its translated strings before anyone signs in. It exposes no
tenant or user data.
"""

import frappe

from qtt_platform import app_config_logic as logic

CONFIG_CHANGED_EVENT = "qtt:config_changed"
TRANSLATION_CONTEXT = "qtt_app"
_CACHE_KEY = "qtt_app_config"
_CACHE_TTL = 60 * 60 * 6


@frappe.whitelist(allow_guest=True)
def get_app_config(lang: str | None = None, platform: str | None = None, app_version: str | None = None) -> dict:
	settings = _settings()
	language = _resolve_language(lang, settings.get("default_language"))

	cache_key = f"{_CACHE_KEY}:{language}"
	shared = frappe.cache().get_value(cache_key)
	if not shared:
		shared = _shared_config(settings, language)
		frappe.cache().set_value(cache_key, shared, expires_in_sec=_CACHE_TTL)

	# Per-client parts (cheap, never cached): flags and update policy depend
	# on the caller's platform/version.
	config = {
		**shared,
		"features": logic.resolve_flags(settings.get("feature_flags") or [], platform, app_version),
		"update": logic.update_policy(settings, app_version, platform),
	}
	config["version"] = logic.content_version(config)
	return config


@frappe.whitelist()
def get_currencies() -> list[dict]:
	"""Enabled currencies with Frappe's own formatting metadata — the app
	formats money exactly like Desk (e.g. Indian 1,00,000.00 grouping)."""
	rows = frappe.get_all(
		"Currency",
		filters={"enabled": 1},
		fields=[
			"name",
			"currency_name",
			"symbol",
			"symbol_on_right",
			"fraction_units",
			"smallest_currency_fraction_value",
			"number_format",
		],
		order_by="name asc",
	)
	return [
		{
			"code": r.name,
			"name": r.currency_name or r.name,
			"symbol": r.symbol or r.name,
			"symbol_on_right": bool(r.symbol_on_right),
			"decimals": _decimals(r.fraction_units),
			"number_format": r.number_format or None,
		}
		for r in rows
	]


# --------------------------------------------------------------------------
def _shared_config(settings: dict, language: str) -> dict:
	themes = [
		logic.theme_payload(t)
		for t in frappe.get_all("QTT App Theme", filters={"enabled": 1}, fields=["*"], order_by="sort_order asc, label asc")
	]
	default_theme = settings.get("default_theme")
	if themes and default_theme not in {t["key"] for t in themes}:
		default_theme = themes[0]["key"]
	return {
		"themes": themes,
		"default_theme": default_theme,
		"default_theme_mode": settings.get("default_theme_mode") or "dark",
		"language": language,
		"rtl": logic.is_rtl(language),
		"languages": _languages(),
		"translations": _translations(language),
		"maintenance": {
			"enabled": bool(settings.get("maintenance_mode")),
			"message": settings.get("maintenance_message") or None,
		},
		"announcement": (
			{"text": settings["announcement"], "level": settings.get("announcement_level") or "info"}
			if settings.get("announcement")
			else None
		),
		"analytics": {
			"enabled": bool(settings.get("analytics_enabled", 1)),
			"flush_seconds": max(10, int(settings.get("analytics_flush_seconds") or 30)),
		},
		"realtime": {"config_event": CONFIG_CHANGED_EVENT},
	}


def _settings() -> dict:
	doc = frappe.get_cached_doc("QTT App Settings")
	data = doc.as_dict()
	data["feature_flags"] = [f.as_dict() for f in doc.get("feature_flags") or []]
	return data


def _languages() -> list[dict]:
	rows = frappe.get_all(
		"Language", filters={"enabled": 1}, fields=["name", "language_name"], order_by="language_name asc"
	)
	return [{"code": r.name, "name": r.language_name or r.name, "rtl": logic.is_rtl(r.name)} for r in rows]


def _resolve_language(requested: str | None, default: str | None) -> str:
	"""Requested if enabled; else its base ('pt-BR' -> 'pt'); else the
	configured default; else English."""
	for candidate in (requested, (requested or "").replace("_", "-").split("-")[0], default, "en"):
		if candidate and frappe.db.get_value("Language", {"name": candidate, "enabled": 1}):
			return candidate
	return "en"


def _translations(language: str) -> dict:
	if language == "en":
		return {}
	base = frappe.db.get_value("Language", language, "based_on")
	layers = [_translation_rows(base)] if base else []
	layers.append(_translation_rows(language))
	return logic.merge_translations(*layers)


def _translation_rows(language: str) -> dict:
	rows = frappe.get_all(
		"Translation",
		filters={"language": language, "context": TRANSLATION_CONTEXT},
		fields=["source_text", "translated_text"],
	)
	return {r.source_text: r.translated_text for r in rows}


def _decimals(fraction_units) -> int:
	try:
		units = int(fraction_units or 100)
	except (TypeError, ValueError):
		return 2
	return max(0, len(str(units)) - 1) if units > 1 else 0


# --------------------------------------------------------------------------
# Invalidation + live push (hooks.py doc_events)
# --------------------------------------------------------------------------
def config_changed(doc=None, method=None):
	"""Clear every language's cached config and tell all connected apps to
	re-fetch. Translation rows outside the app's context don't affect the
	app, so they're ignored."""
	if doc is not None and doc.doctype == "Translation" and doc.get("context") != TRANSLATION_CONTEXT:
		return
	frappe.cache().delete_keys(_CACHE_KEY)
	frappe.publish_realtime(CONFIG_CHANGED_EVENT, {}, after_commit=True)
