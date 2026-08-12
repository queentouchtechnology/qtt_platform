import frappe
from frappe import _
from frappe.model.document import Document


class QTTTenantProductSubscriptionPointer(Document):
	"""No role holds write/create/delete DocPerm here (see the .json
	permissions array) — every write goes through
	qtt_platform.subscription.service.activate_pointer() with
	ignore_permissions=True. validate() is the integrity backstop, not
	the access-control layer."""

	def validate(self):
		self._validate_subscription_matches()

	def _validate_subscription_matches(self):
		sub = frappe.db.get_value(
			"QTT Product Subscription", self.current_subscription, ["tenant", "product"], as_dict=True
		)
		if not sub:
			frappe.throw(_("Referenced subscription {0} does not exist.").format(self.current_subscription))
		if sub.tenant != self.tenant or sub.product != self.product:
			frappe.throw(
				_("Pointer tenant/product must match the referenced subscription's tenant/product."),
				frappe.ValidationError,
			)
