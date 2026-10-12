"""
Seeds the QTT OS app's backend-controlled defaults on install/migrate:
the QTT Platform Owner role, QTT App Settings defaults, the built-in themes, and app-string
translations (Frappe Translation rows, context=qtt_app) from
qtt_platform/app_i18n/<language>.json.

Insert-only: anything an admin has already created or edited in Desk is
never overwritten — after the first migrate, Desk is the source of truth.
"""

import json
import os

import frappe

from qtt_platform.api.app_config import TRANSLATION_CONTEXT, config_changed
from qtt_platform.app_defaults import DEFAULT_THEMES

_I18N_DIR = os.path.join(os.path.dirname(__file__), "app_i18n")

def seed_app_defaults() -> None:
	_ensure_platform_owner_role()
	_seed_themes()
	_seed_settings()
	_seed_translations()
	from qtt_platform.marketing.seed import seed_marketing_defaults

	seed_marketing_defaults()
	from qtt_platform.api.servers import seed_servers

	seed_servers()
	config_changed()


def _ensure_platform_owner_role() -> None:
	"""The Frappe Role that unlocks QTT Admin (tenant/guards.require_platform_owner).
	Created if missing; never given to anyone automatically — assign it to
	QTT staff in Desk → User → Roles."""
	from qtt_platform.tenant.guards import PLATFORM_OWNER_ROLE

	if frappe.db.exists("Role", PLATFORM_OWNER_ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": PLATFORM_OWNER_ROLE, "desk_access": 1}).insert(ignore_permissions=True)


def _seed_themes() -> None:
	for theme in DEFAULT_THEMES:
		if frappe.db.exists("QTT App Theme", theme["theme_key"]):
			continue
		doc = frappe.new_doc("QTT App Theme")
		doc.theme_key = theme["theme_key"]
		doc.label = theme["label"]
		doc.enabled = 1
		doc.sort_order = theme["sort_order"]
		doc.corner_radius = theme.get("radius", 12)
		doc.supports_light = 1
		doc.supports_dark = 1
		for field, value in theme.get("components", {}).items():
			doc.set(field, value)
		for mode in ("light", "dark"):
			for token, value in theme[mode].items():
				doc.set(f"{mode}_{token}", value)
		doc.insert(ignore_permissions=True)


def _seed_settings() -> None:
	"""Single DocTypes don't get field defaults until first saved — set them
	once, without touching values an admin already chose."""
	settings = frappe.get_single("QTT App Settings")
	defaults = {
		"default_theme": "qtt-midnight",
		"default_theme_mode": "dark",
		"default_language": "en" if frappe.db.exists("Language", "en") else None,
		"announcement_level": "info",
		"default_text_size": "standard",
		"default_density": "standard",
		"analytics_flush_seconds": 30,
		"analytics_retention_days": 180,
	}
	changed = False
	for field, value in defaults.items():
		if value is not None and not settings.get(field):
			settings.set(field, value)
			changed = True
	# A Single's Check reads 0 whether it was switched off or never saved, so
	# "never saved" is told apart by its tabSingles row being absent.
	saved = set(frappe.db.sql_list("select field from tabSingles where doctype = %s", "QTT App Settings"))
	for check in ("analytics_enabled", "signup_verify_email", "signup_verify_whatsapp", "google_sign_in", "biometric_sign_in"):
		if check not in saved:
			settings.set(check, 1)
			changed = True
	for field, value in (("whatsapp_otp_template", "reference_number"), ("whatsapp_otp_language", "en")):
		if not settings.get(field):
			settings.set(field, value)
			changed = True
	if changed:
		settings.save(ignore_permissions=True)


def _seed_translations() -> None:
	if not os.path.isdir(_I18N_DIR):
		return
	for filename in sorted(os.listdir(_I18N_DIR)):
		if not filename.endswith(".json"):
			continue
		language = filename[:-5]
		if language == "en" or not frappe.db.exists("Language", language):
			continue
		with open(os.path.join(_I18N_DIR, filename), encoding="utf-8") as fh:
			strings = json.load(fh)
		existing = set(
			frappe.get_all(
				"Translation",
				filters={"language": language, "context": TRANSLATION_CONTEXT},
				pluck="source_text",
			)
		)
		for source, translated in strings.items():
			if source in existing or not translated:
				continue
			frappe.get_doc(
				{
					"doctype": "Translation",
					"language": language,
					"source_text": source,
					"translated_text": translated,
					"context": TRANSLATION_CONTEXT,
				}
			).insert(ignore_permissions=True)
