from frappe.model.document import Document


class QTTFeatureAccess(Document):
	"""One screen / feature of QTT OS and who can open it — kept in step with the assistant's screen registry
	(qtt_platform/assistant/screens.json) on every migrate (qtt_platform.feature_access.sync). Read-only in Desk."""
