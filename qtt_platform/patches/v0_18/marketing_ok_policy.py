"""QTT Marketing Settings, 12 Nov 2026: "If nobody decides in time" (Send it / Skip it) became "Your OK before it goes
live" with a third choice, Go live without my OK. Saved values keep their meaning under the new names."""

import frappe

from qtt_platform.marketing import approvals

FIELDS = ("email_batch_on_timeout", "linkedin_on_timeout", "social_on_timeout", "article_on_timeout")


def execute():
	for field in FIELDS:
		old = frappe.db.get_single_value("QTT Marketing Settings", field)
		if old in approvals.OLD_VALUES:
			frappe.db.set_single_value("QTT Marketing Settings", field, approvals.OLD_VALUES[old])
