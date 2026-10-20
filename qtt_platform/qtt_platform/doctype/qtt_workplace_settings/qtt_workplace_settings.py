import secrets

import frappe
from frappe import _
from frappe.model.document import Document


class QTTWorkplaceSettings(Document):
	def validate(self):
		from qtt_platform import workplace_rules as rules

		before = self.get_doc_before_save()
		fp_before = before.files_key_fingerprint if before else None
		if fp_before and self.files_key_fingerprint != fp_before:
			frappe.throw(_("The files key can't be changed — files stored with it would no longer open."))
		if self.encrypt_files and not self.files_key_fingerprint:
			master = secrets.token_hex(32)  # made once; kept encrypted with the site's encryption key
			self.files_master_key = master
			self.files_key_fingerprint = rules.key_fingerprint(master)

	def on_update(self):
		before = self.get_doc_before_save()
		was = bool(before and before.encrypt_files)
		if bool(self.encrypt_files) != was:
			from qtt_platform import files_crypto

			self.db_set("encryption_status", _("Starting — stored files are being switched over"), update_modified=False)
			files_crypto.start(bool(self.encrypt_files))
