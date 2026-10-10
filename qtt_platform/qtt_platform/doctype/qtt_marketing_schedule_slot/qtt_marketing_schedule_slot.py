import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time

from qtt_platform.marketing.n8n_schedule import ScheduleError, clean_days


class QTTMarketingScheduleSlot(Document):
	def validate(self):
		try:
			self.days = ",".join(clean_days(self.days or ""))
		except ScheduleError as exc:
			frappe.throw(_(str(exc)))
		if self.end_time and self.start_time and get_time(self.end_time) <= get_time(self.start_time):
			frappe.throw(_("The end time must be after the start time."))
		if self.valid_from and self.valid_to and str(self.valid_to) < str(self.valid_from):
			frappe.throw(_("The until date is before the from date."))
		self.n8n_workflow_id = (self.n8n_workflow_id or "").strip() or None
