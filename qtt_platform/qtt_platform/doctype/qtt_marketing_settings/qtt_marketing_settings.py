from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document


class QTTMarketingSettings(Document):
	def validate(self):
		self.n8n_url = (self.n8n_url or "").strip().rstrip("/")
		if self.n8n_url:
			parsed = urlparse(self.n8n_url)
			if parsed.scheme != "https" or not parsed.netloc:
				frappe.throw(_("n8n Address must be an https address, e.g. https://n8n.example.com"))
