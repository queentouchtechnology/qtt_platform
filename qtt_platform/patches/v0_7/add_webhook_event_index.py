import frappe


def execute():
	"""QTT Webhook Event.gateway_event_id's uniqueness is already declared
	via "unique": 1 in the doctype JSON — bench migrate creates that index
	automatically for a single-field unique, same as QTT Payment
	Transaction.gateway_reference (see v0_6's own comment). This patch
	only adds the supporting index for reconciliation's own lookup shape
	(qtt_platform.billing.service.reconcile_subscriptions(): "every open
	QTT Product Subscription with a razorpay_subscription_id") and for
	correlating QTT Webhook Event rows back to a subscription for
	debugging."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_webhook_event")
	frappe.reload_doc("qtt_platform", "doctype", "qtt_product_subscription")

	frappe.db.add_index("QTT Webhook Event", ["gateway_subscription_id"])
	frappe.db.add_index("QTT Product Subscription", ["razorpay_subscription_id"])
