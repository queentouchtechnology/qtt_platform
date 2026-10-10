"""
QTT Admin → App control: which QTT App Settings fields the console may
change, and how incoming values are cleaned. Pure (no frappe) so it can be
tested without a bench; api/app_control.py does the saving.

The DocType's own validate() still runs on save (versions, maintenance
message, flag rules), so this layer only whitelists and normalises.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from qtt_platform.app_config_logic import APP_PLATFORMS, DENSITIES, TEXT_SIZES, parse_version


class ControlInputError(ValueError):
	"""Message is shown to the platform owner as-is."""


THEME_MODES = ("dark", "light", "system")
ANNOUNCEMENT_LEVELS = ("info", "warning", "success")

#: section -> {field: kind}
SECTIONS: dict[str, dict[str, str]] = {
	"status": {
		"maintenance_mode": "check",
		"maintenance_message": "text",
		"announcement": "text",
		"announcement_level": "announcement_level",
	},
	"versions": {
		"min_app_version": "version",
		"latest_app_version": "version",
		"update_url_android": "url",
		"update_url_ios": "url",
		"update_url_desktop": "url",
	},
	"defaults": {
		"default_theme": "link",
		"default_theme_mode": "theme_mode",
		"default_language": "link",
		"default_text_size": "text_size",
		"default_density": "density",
	},
	"analytics": {
		"analytics_enabled": "check",
		"analytics_flush_seconds": "flush_seconds",
		"analytics_retention_days": "retention_days",
	},
}

_CHOICES = {
	"announcement_level": ANNOUNCEMENT_LEVELS,
	"theme_mode": THEME_MODES,
	"text_size": TEXT_SIZES,
	"density": DENSITIES,
}
_FLAG_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,59}$")
MAX_TEXT = 500


def _truthy(value) -> int:
	return 1 if str(value).strip().lower() in ("1", "true", "yes", "on") else 0


def _int(value, lo: int, hi: int, label: str) -> int:
	try:
		number = int(str(value).strip())
	except (TypeError, ValueError) as exc:
		raise ControlInputError(f"{label} must be a whole number.") from exc
	if not lo <= number <= hi:
		raise ControlInputError(f"{label} must be between {lo} and {hi}.")
	return number


def clean_section(section: str, values: dict) -> dict:
	"""Only known fields of the section; unknown keys are rejected so a
	typo can't silently do nothing."""
	fields = SECTIONS.get(section)
	if fields is None:
		raise ControlInputError("Unknown settings section.")
	unknown = set(values) - set(fields)
	if unknown:
		raise ControlInputError(f"Not editable here: {', '.join(sorted(unknown))}.")

	clean: dict = {}
	for field, raw in values.items():
		kind = fields[field]
		value = raw.strip() if isinstance(raw, str) else raw
		if kind == "check":
			clean[field] = _truthy(value)
		elif kind == "text":
			text = (value or "").strip() if isinstance(value, str) else ""
			if len(text) > MAX_TEXT:
				raise ControlInputError(f"Keep messages under {MAX_TEXT} characters.")
			clean[field] = text
		elif kind == "version":
			if value and not parse_version(value):
				raise ControlInputError("Versions must look like 1.2.3.")
			clean[field] = value or ""
		elif kind == "url":
			if value:
				parsed = urlparse(value)
				if parsed.scheme != "https" or not parsed.netloc:
					raise ControlInputError("Update links must be https addresses.")
			clean[field] = value or ""
		elif kind == "link":
			clean[field] = value or None
		elif kind == "flush_seconds":
			clean[field] = _int(value, 5, 600, "Send interval")
		elif kind == "retention_days":
			clean[field] = _int(value, 1, 3650, "Keep events for")
		elif kind in _CHOICES:
			if value not in _CHOICES[kind]:
				raise ControlInputError(f"Choose one of: {', '.join(_CHOICES[kind])}.")
			clean[field] = value
	_check_versions(clean)
	return clean


def _check_versions(clean: dict) -> None:
	low, high = clean.get("min_app_version"), clean.get("latest_app_version")
	if low and high and parse_version(low) > parse_version(high):
		raise ControlInputError("Minimum version can't be newer than the latest version.")


def clean_flag(flag: dict) -> dict:
	key = str(flag.get("flag_key") or "").strip().lower()
	if not _FLAG_KEY.match(key):
		raise ControlInputError("Flag keys use lowercase letters, digits, dots, dashes or underscores, e.g. inbox.voice_notes.")
	platforms = sorted({p.strip().lower() for p in str(flag.get("platforms") or "").split(",") if p.strip()})
	unknown = set(platforms) - set(APP_PLATFORMS)
	if unknown:
		raise ControlInputError(f"Unknown platform: {', '.join(sorted(unknown))}.")
	min_version = str(flag.get("min_app_version") or "").strip()
	if min_version and not parse_version(min_version):
		raise ControlInputError("Versions must look like 1.2.3.")
	description = str(flag.get("description") or "").strip()
	if len(description) > MAX_TEXT:
		raise ControlInputError(f"Keep messages under {MAX_TEXT} characters.")
	return {
		"flag_key": key,
		"enabled": _truthy(flag.get("enabled")),
		"platforms": ", ".join(platforms),
		"min_app_version": min_version,
		"description": description,
	}


def changes(before: dict, after: dict) -> tuple[dict, dict]:
	"""(before, after) limited to the fields that actually changed — what
	the audit log keeps."""
	changed = [k for k in after if (before.get(k) or "") != (after.get(k) or "")]
	return {k: before.get(k) for k in changed}, {k: after.get(k) for k in changed}
