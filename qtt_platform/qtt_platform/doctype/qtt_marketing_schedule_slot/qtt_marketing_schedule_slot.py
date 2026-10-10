import frappe
from frappe import _
from frappe.model.document import Document

from qtt_platform.marketing.n8n_schedule import ScheduleError, clean_days
from qtt_platform.marketing.report import hhmm


class QTTMarketingScheduleSlot(Document):
	def validate(self):
		try:
			self.days = ",".join(clean_days(self.days or ""))
		except ScheduleError as exc:
			frappe.throw(_(str(exc)))
		start, end = hhmm(self.start_time), hhmm(self.end_time)
		if start and end and end <= start:  # zero-padded HH:MM compares correctly as text
			frappe.throw(_("The end time ({0}) must be after the start time ({1}).").format(end, start))
		if self.valid_from and self.valid_to and str(self.valid_to) < str(self.valid_from):
			frappe.throw(_("The until date is before the from date."))
		self.n8n_workflow_id = (self.n8n_workflow_id or "").strip() or None
