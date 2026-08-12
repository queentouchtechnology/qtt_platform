import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class QTTProductSubscription(Document):
	def validate(self):
		self._validate_plan_matches_product()
		self._validate_period()

	def _validate_plan_matches_product(self):
		# Cross-reference guard — hardening review section 7: "Product
		# Subscription -> Plan: self.product == plan.product." A tenant
		# must never end up 'subscribed' to an HRMS plan under an LMS
		# product subscription row.
		plan_product = frappe.db.get_value("QTT Plan", self.plan, "product")
		if plan_product is None:
			frappe.throw(_("Referenced plan {0} does not exist.").format(self.plan))
		if plan_product != self.product:
			frappe.throw(
				_("Plan {0} belongs to product {1}, not {2}.").format(self.plan, plan_product, self.product),
				frappe.ValidationError,
			)

	def _validate_period(self):
		if self.current_period_start and self.current_period_end:
			if get_datetime(self.current_period_end) <= get_datetime(self.current_period_start):
				frappe.throw(_("current_period_end must be after current_period_start."), frappe.ValidationError)
