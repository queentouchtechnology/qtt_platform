"""
QTT Admin → App control: change what every QTT OS app shows and allows —
maintenance, announcement, versions, defaults, themes, languages, feature
flags, analytics — from the app instead of Desk. Platform Owners only.

Every save goes through the normal DocType save, so its validate() runs
and the existing doc_events push `qtt:config_changed` to running apps
(api/app_config.config_changed). Every change is audited with only the
fields that changed.
"""

import json

import frappe
from frappe import _

from qtt_platform import app_control_logic as logic
from qtt_platform.audit import write_audit_event
from qtt_platform.tenant.guards import require_platform_owner

SETTINGS = "QTT App Settings"


@frappe.whitelist(methods=["GET"])
def get_app_control() -> dict:
	require_platform_owner()
	doc = frappe.get_doc(SETTINGS)
	values = {field: doc.get(field) for fields in logic.SECTIONS.values() for field in fields}
	themes = frappe.get_all(
		"QTT App Theme", fields=["name", "label", "enabled", "sort_order"], order_by="sort_order asc, label asc"
	)
	languages = frappe.get_all("Language", fields=["name", "language_name", "enabled"], order_by="language_name asc")
	return {
		"values": values,
		"flags": [
			{k: f.get(k) for k in ("flag_key", "enabled", "platforms", "min_app_version", "description")}
			for f in doc.get("feature_flags") or []
		],
		"themes": [{"key": t.name, "label": t.label or t.name, "enabled": bool(t.enabled)} for t in themes],
		"languages": [{"code": l.name, "name": l.language_name or l.name, "enabled": bool(l.enabled)} for l in languages],
		"choices": {
			"announcement_level": list(logic.ANNOUNCEMENT_LEVELS),
			"theme_mode": list(logic.THEME_MODES),
			"text_size": list(logic.TEXT_SIZES),
			"density": list(logic.DENSITIES),
			"platforms": list(logic.APP_PLATFORMS),
		},
	}


@frappe.whitelist(methods=["POST"])
def save_section(section: str, values) -> dict:
	require_platform_owner()
	values = _json(values)
	clean = _clean(lambda: logic.clean_section(section, values))
	if section == "defaults":
		_check_default_links(clean)
	doc = frappe.get_doc(SETTINGS)
	before = {k: doc.get(k) for k in clean}
	doc.update(clean)
	doc.save(ignore_permissions=True)
	_audit("app_settings_changed", before, clean, {"section": section})
	return get_app_control()


@frappe.whitelist(methods=["POST"])
def save_flag(flag, original_key: str | None = None) -> dict:
	"""Add or edit one feature flag (original_key = key before a rename)."""
	require_platform_owner()
	clean = _clean(lambda: logic.clean_flag(_json(flag)))
	doc = frappe.get_doc(SETTINGS)
	match = (original_key or clean["flag_key"]).strip().lower()
	row = next((f for f in doc.get("feature_flags") or [] if f.flag_key == match), None)
	if row is None and any(f.flag_key == clean["flag_key"] for f in doc.get("feature_flags") or []):
		frappe.throw(_("A flag with this key already exists."))
	before = {k: row.get(k) for k in clean} if row else {}
	if row is None:
		doc.append("feature_flags", clean)
	else:
		row.update(clean)
	doc.save(ignore_permissions=True)
	_audit("app_feature_flag_saved", before, clean, {"flag_key": clean["flag_key"]})
	return get_app_control()


@frappe.whitelist(methods=["POST"])
def delete_flag(flag_key: str) -> dict:
	require_platform_owner()
	doc = frappe.get_doc(SETTINGS)
	rows = [f for f in doc.get("feature_flags") or [] if f.flag_key != flag_key]
	if len(rows) == len(doc.get("feature_flags") or []):
		frappe.throw(_("Unknown feature flag."), frappe.DoesNotExistError)
	doc.set("feature_flags", rows)
	doc.save(ignore_permissions=True)
	write_audit_event("app_feature_flag_deleted", target_doctype=SETTINGS, target_name=SETTINGS, metadata={"flag_key": flag_key})
	return get_app_control()


@frappe.whitelist(methods=["POST"])
def set_theme_enabled(theme_key: str, enabled) -> dict:
	require_platform_owner()
	enabled = logic._truthy(enabled)
	if not enabled and frappe.db.get_single_value(SETTINGS, "default_theme") == theme_key:
		frappe.throw(_("This is the default theme. Choose another default first."))
	doc = frappe.get_doc("QTT App Theme", theme_key)
	if not enabled and frappe.db.count("QTT App Theme", {"enabled": 1}) <= 1:
		frappe.throw(_("Keep at least one theme switched on."))
	_toggle(doc, "enabled", enabled, "app_theme_toggled", {"theme": theme_key})
	return get_app_control()


@frappe.whitelist(methods=["POST"])
def set_language_enabled(code: str, enabled) -> dict:
	require_platform_owner()
	enabled = logic._truthy(enabled)
	if not enabled and (code == "en" or frappe.db.get_single_value(SETTINGS, "default_language") == code):
		frappe.throw(_("English and the default language always stay on."))
	doc = frappe.get_doc("Language", code)
	_toggle(doc, "enabled", enabled, "app_language_toggled", {"language": code})
	return get_app_control()


# --------------------------------------------------------------------------
def _json(value):
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid data."))
	if not isinstance(value, dict):
		frappe.throw(_("Invalid data."))
	return value


def _clean(fn):
	try:
		return fn()
	except logic.ControlInputError as exc:
		frappe.throw(_(str(exc)))


def _check_default_links(clean: dict) -> None:
	theme = clean.get("default_theme")
	if theme and not frappe.db.get_value("QTT App Theme", {"name": theme, "enabled": 1}):
		frappe.throw(_("Switch the theme on before making it the default."))
	language = clean.get("default_language")
	if language and not frappe.db.get_value("Language", {"name": language, "enabled": 1}):
		frappe.throw(_("Switch the language on before making it the default."))


def _toggle(doc, field: str, value: int, event: str, metadata: dict) -> None:
	before = int(doc.get(field) or 0)
	if before == value:
		return
	doc.set(field, value)
	doc.save(ignore_permissions=True)
	write_audit_event(event, target_doctype=doc.doctype, target_name=doc.name,
					  before_state={field: before}, after_state={field: value}, metadata=metadata)


def _audit(event: str, before: dict, after: dict, metadata: dict) -> None:
	old, new = logic.changes(before, after)
	if old or new or not before:
		write_audit_event(event, target_doctype=SETTINGS, target_name=SETTINGS, before_state=old, after_state=new, metadata=metadata)
