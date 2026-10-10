import re

import frappe
from frappe import _
from frappe.model.document import Document

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class QTTMarketingPlan(Document):
	def validate(self):
		self.month = (self.month or "").strip()
		if not _MONTH.match(self.month):
			frappe.throw(_("Month must look like 2026-10."))
		if not self.title:
			self.title = f"Marketing plan {self.month}"
		for week in self.weeks or []:
			if week.start_date and week.end_date and str(week.end_date) < str(week.start_date):
				frappe.throw(_("{0}: the end date is before the start date.").format(week.label))
