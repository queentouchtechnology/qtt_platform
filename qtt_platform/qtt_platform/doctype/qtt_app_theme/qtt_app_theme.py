import re

import frappe
from frappe import _
from frappe.model.document import Document

from qtt_platform.app_config_logic import THEME_TOKENS

_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class QTTAppTheme(Document):
	def validate(self):
		if not _KEY.match(self.theme_key or ""):
			frappe.throw(_("Theme Key must be lowercase letters, digits and dashes, e.g. qtt-midnight."))
		if not (self.supports_light or self.supports_dark):
			frappe.throw(_("A theme needs a light or a dark variant (or both)."))
		for mode in ("light", "dark"):
			if not self.get(f"supports_{mode}"):
				continue
			for token in THEME_TOKENS:
				value = self.get(f"{mode}_{token}")
				if not value or not _HEX.match(value):
					frappe.throw(_("{0} {1} must be a colour like #3858F8.").format(mode.title(), token.replace("_", " ")))
		if not 0 <= (self.corner_radius or 0) <= 32:
			frappe.throw(_("Corner Radius must be between 0 and 32."))

	def on_trash(self):
		if frappe.db.get_single_value("QTT App Settings", "default_theme") == self.name:
			frappe.throw(_("This is the default theme. Choose another default in QTT App Settings first."))
