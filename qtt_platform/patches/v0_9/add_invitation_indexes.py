import frappe


def execute():
	"""QTT Invitation.token's uniqueness is already declared via
	"unique": 1 in the doctype JSON — bench migrate creates that index
	automatically, same as every other single-field unique in this app
	(see v0_6/v0_7's identical reasoning). This patch only adds the
	supporting index for invite_user()'s own lookup shape: 'is there
	already a pending invitation for this (tenant, email)'."""
	frappe.reload_doc("qtt_platform", "doctype", "qtt_invitation")
	frappe.db.add_index("QTT Invitation", ["tenant", "email", "status"])
