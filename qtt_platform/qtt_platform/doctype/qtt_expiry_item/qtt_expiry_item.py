# Copyright (c) 2026, Queen Touch Technology
# Expiry register — see qtt_platform/ops/expiry_watch.py and api/servers.check_expiries.

from frappe.model.document import Document


class QTTExpiryItem(Document):
	def validate(self):
		# A new date (renewed) starts the reminders over.
		if self.has_value_changed("expires_on"):
			self.last_step = None
