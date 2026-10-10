import frappe
from frappe import _
from frappe.model.document import Document

from qtt_platform.app_config_logic import APP_PLATFORMS, parse_version


class QTTAppSettings(Document):
	def validate(self):
		for field in ("min_app_version", "latest_app_version"):
			if self.get(field) and not parse_version(self.get(field)):
				frappe.throw(_("{0} must look like 1.2.3.").format(self.meta.get_label(field)))
		if self.maintenance_mode and not (self.maintenance_message or "").strip():
			frappe.throw(_("Add a Maintenance Message — users will see it instead of the app."))
		seen = set()
		for flag in self.feature_flags or []:
			key = (flag.flag_key or "").strip()
			if key in seen:
				frappe.throw(_("Duplicate feature flag: {0}").format(key))
			seen.add(key)
			unknown = {p.strip().lower() for p in (flag.platforms or "").split(",") if p.strip()} - set(APP_PLATFORMS)
			if unknown:
				frappe.throw(_("Unknown platform(s) in flag {0}: {1}").format(key, ", ".join(sorted(unknown))))
			if flag.min_app_version and not parse_version(flag.min_app_version):
				frappe.throw(_("Flag {0}: Min App Version must look like 1.2.3.").format(key))
