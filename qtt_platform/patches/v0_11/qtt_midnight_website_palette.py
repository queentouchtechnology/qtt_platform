"""
QTT Midnight now matches queentouchtech.com (app_defaults.DEFAULT_THEMES). Seeding
never overwrites an existing theme, so this moves the live row over — only the
colours still at the previous built-in values; anything edited in Desk stays.
"""

import frappe

from qtt_platform.app_defaults import DEFAULT_THEMES

PREVIOUS = {
	"light": dict(primary="#3858F8", secondary="#5B6CF0", background="#F6F7FB", surface="#FFFFFF", surface_variant="#EEF1F9",
				  text="#0E1220", text_muted="#5B6375", border="#DCE0EC"),
	"dark": dict(primary="#3858F8", secondary="#8B9CFF", background="#080810", surface="#11131C", surface_variant="#1A1D2B",
				 text="#F8F8F8", text_muted="#8890A2", border="#262A3A"),
}


def execute():
	if not frappe.db.exists("QTT App Theme", "qtt-midnight"):
		return
	new = next(t for t in DEFAULT_THEMES if t["theme_key"] == "qtt-midnight")
	doc = frappe.get_doc("QTT App Theme", "qtt-midnight")
	changed = False
	for mode, tokens in PREVIOUS.items():
		for token, old in tokens.items():
			field = f"{mode}_{token}"
			if (doc.get(field) or "").upper() == old.upper():
				doc.set(field, new[mode][token])
				changed = True
	if changed:
		doc.save(ignore_permissions=True)
