"""
Pure helpers behind api.app_config — no frappe import, unit-testable
without a bench.
"""

import hashlib
import json
import re

#: Scripts written right-to-left. Matched on the primary language subtag
#: (so "ar-EG" and "ur-PK" match too).
RTL_LANGUAGES = frozenset({"ar", "he", "fa", "ur", "ps", "sd", "ug", "yi", "dv", "ku", "ckb"})

#: Colour tokens every theme mode carries — the app's ThemeData is built
#: from exactly these names.
THEME_TOKENS = (
	"primary",
	"secondary",
	"background",
	"surface",
	"surface_variant",
	"text",
	"text_muted",
	"border",
	"error",
	"success",
	"warning",
)

APP_PLATFORMS = ("android", "ios", "web", "windows", "macos", "linux")

#: Global UI options (QTT App Settings defaults, user-overridable in the app).
TEXT_SIZES = ("small", "standard", "large", "extra_large")
DENSITIES = ("comfortable", "standard", "compact")

#: Per-theme component style, value -> allowed options (first = fallback).
COMPONENT_STYLES = {
	"card_style": ("outlined", "elevated", "flat"),
	"input_style": ("filled", "outlined"),
	"button_shape": ("rounded", "pill"),
}
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_VERSION = re.compile(r"^\d+(\.\d+){0,3}")


def is_rtl(language: str | None) -> bool:
	return bool(language) and language.replace("_", "-").split("-")[0].lower() in RTL_LANGUAGES


def parse_version(version: str | None) -> tuple[int, ...] | None:
	"""'1.2.10+34' -> (1, 2, 10). None for blank/garbage."""
	match = _VERSION.match((version or "").strip())
	if not match:
		return None
	parts = [int(p) for p in match.group(0).split(".")]
	while len(parts) < 3:
		parts.append(0)
	return tuple(parts)


def version_lt(a: str | None, b: str | None) -> bool:
	"""a < b; unknown versions never count as 'older' (fail open for display,
	the server still enforces its own rules on every request)."""
	pa, pb = parse_version(a), parse_version(b)
	return bool(pa and pb and pa < pb)


def flag_applies(flag: dict, platform: str | None, app_version: str | None) -> bool:
	if not flag.get("enabled"):
		return False
	platforms = {p.strip().lower() for p in (flag.get("platforms") or "").split(",") if p.strip()}
	if platforms and (platform or "").lower() not in platforms:
		return False
	if flag.get("min_app_version") and version_lt(app_version, flag["min_app_version"]):
		return False
	return True


def resolve_flags(flags: list[dict], platform: str | None, app_version: str | None) -> dict[str, bool]:
	"""Every configured flag key maps to true/false for this client, so the
	app can tell 'off' apart from 'unknown flag'."""
	result: dict[str, bool] = {}
	for flag in flags:
		key = (flag.get("flag_key") or "").strip()
		if key:
			result[key] = result.get(key, False) or flag_applies(flag, platform, app_version)
	return result


def theme_payload(row: dict) -> dict:
	"""QTT App Theme row -> app payload. Invalid/missing colours are dropped
	(the app falls back to its built-in defaults for those tokens)."""
	modes = {}
	for mode in ("light", "dark"):
		if not row.get(f"supports_{mode}"):
			continue
		colors = {t: row.get(f"{mode}_{t}") for t in THEME_TOKENS}
		modes[mode] = {k: v.upper() for k, v in colors.items() if isinstance(v, str) and _HEX.match(v)}
	return {
		"key": row["theme_key"],
		"label": row.get("label") or row["theme_key"],
		"radius": int(row.get("corner_radius") or 12),
		"components": {
			field: (row.get(field) if row.get(field) in allowed else allowed[0])
			for field, allowed in COMPONENT_STYLES.items()
		},
		"modes": modes,
	}


def pick(value, allowed: tuple, fallback: str) -> str:
	return value if value in allowed else fallback


def update_policy(settings: dict, app_version: str | None, platform: str | None) -> dict:
	url_field = {"android": "update_url_android", "ios": "update_url_ios", "macos": "update_url_ios"}.get(
		(platform or "").lower(), "update_url_desktop"
	)
	return {
		"min_version": settings.get("min_app_version") or None,
		"latest_version": settings.get("latest_app_version") or None,
		"force_update": version_lt(app_version, settings.get("min_app_version")),
		"update_available": version_lt(app_version, settings.get("latest_app_version")),
		"update_url": settings.get(url_field) or None,
	}


def merge_translations(*layers: dict) -> dict:
	"""Later layers win (base language, then the specific locale)."""
	merged: dict = {}
	for layer in layers:
		merged.update({k: v for k, v in layer.items() if k and v})
	return merged


def content_version(payload: dict) -> str:
	"""Stable short hash of a config payload — the app skips re-applying an
	unchanged config and uses it as its cache key."""
	return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def push_config(settings: dict) -> dict | None:
	"""The Firebase values the app starts push with (public: they name the project, they don't unlock it).
	None until the project and sender are set; a platform without its app ID is left out (no push there)."""
	def v(k):
		return str(settings.get(k) or "").strip()

	if not (v("firebase_project_id") and v("firebase_sender_id")):
		return None
	out = {"project_id": v("firebase_project_id"), "sender_id": v("firebase_sender_id")}
	if v("firebase_android_app_id") and v("firebase_android_api_key"):
		out["android"] = {"app_id": v("firebase_android_app_id"), "api_key": v("firebase_android_api_key")}
	if v("firebase_web_app_id") and v("firebase_web_api_key") and v("web_push_key"):
		out["web"] = {"app_id": v("firebase_web_app_id"), "api_key": v("firebase_web_api_key"), "vapid_key": v("web_push_key")}
	return out
