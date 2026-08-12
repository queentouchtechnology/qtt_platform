"""
Real bench integration tests for SaaS lifecycle Phase F — requires an
actual Frappe site (frappe.tests.utils.FrappeTestCase). NOT executed
this pass (no bench access); see test_billing_subscriptions.py's Phase F
test classes (InviteUserTest, AcceptInvitationTest, RevokeInvitationTest,
UserProvisioningCreateUserTest, ...) for the 21 bench-independent tests
that WERE actually executed while building this phase.

Does not send a real email — frappe.sendmail() is left to run for real
here (it's Frappe's own queued-by-default mechanism, not something this
project reimplements), so running this against a real bench with email
configured will genuinely queue an email. If that's undesirable, monkey-
patch frappe.sendmail before running.

Run on a real bench:

    bench --site <test-site> run-tests --app qtt_platform \
        --module qtt_platform.tests.test_invitation_integration
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from qtt_platform.api import invitation as api_invitation

_PRODUCT = "QMP_LMS"
_INVITEE_EMAIL = "qtt-phase-f-invitee@example.com"


class InvitationIntegrationTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("QTT Product", _PRODUCT):
			frappe.get_doc(
				{
					"doctype": "QTT Product",
					"product_key": _PRODUCT,
					"display_name": "QMP LMS",
					"app_name": "lms",
					"status": "active",
					"roles": [{"role_key": "Manager", "role_name": "Manager"}],
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		self.tenant = frappe.get_doc(
			{
				"doctype": "QTT Tenant",
				"tenant_name": "Phase F Integration Tenant",
				"slug": "phase-f-integration-tenant",
				"owner_user": "Administrator",
				"status": "active",
			}
		)
		self.tenant.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "QTT Tenant Membership",
				"user": "Administrator",
				"tenant": self.tenant.name,
				"tenant_role": "Tenant Owner",
				"status": "active",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		if frappe.db.exists("User", _INVITEE_EMAIL):
			frappe.delete_doc("User", _INVITEE_EMAIL, force=1, ignore_permissions=True)
		frappe.delete_doc("QTT Tenant", self.tenant.name, force=1, ignore_permissions=True)
		super().tearDown()

	def test_full_invite_and_accept_flow_grants_membership_and_product_access(self):
		invite_result = api_invitation.invite_user(
			self.tenant.name, _INVITEE_EMAIL, tenant_role="Member", product=_PRODUCT, product_role="Manager"
		)
		self.assertTrue(invite_result["invitation"])

		token = frappe.db.get_value("QTT Invitation", invite_result["invitation"], "token")

		accept_result = api_invitation.accept_invitation(
			token, full_name="Phase F Invitee", password="StrongPassword123!"
		)
		self.assertTrue(accept_result["success"], accept_result)
		self.assertEqual(accept_result["data"]["product_role"], "Manager")

		membership = frappe.db.get_value(
			"QTT Tenant Membership", {"user": _INVITEE_EMAIL, "tenant": self.tenant.name}, ["tenant_role", "status"], as_dict=True
		)
		self.assertEqual(membership.tenant_role, "Member")
		self.assertEqual(membership.status, "active")

		access = frappe.db.get_value(
			"QTT Product Access", {"tenant": self.tenant.name, "product": _PRODUCT}, ["product_role", "status"], as_dict=True
		)
		self.assertEqual(access.product_role, "Manager")
		self.assertEqual(access.status, "active")

		invitation_status = frappe.db.get_value("QTT Invitation", invite_result["invitation"], "status")
		self.assertEqual(invitation_status, "accepted")

		# Re-accepting the SAME token a second time must be rejected —
		# it's no longer 'pending'.
		second_attempt = api_invitation.accept_invitation(token)
		self.assertFalse(second_attempt["success"])
		self.assertEqual(second_attempt["error"]["code"], "INVALID_INVITATION")

	def test_re_inviting_the_same_email_reuses_the_pending_row(self):
		first = api_invitation.invite_user(self.tenant.name, _INVITEE_EMAIL, tenant_role="Member")
		second = api_invitation.invite_user(self.tenant.name, _INVITEE_EMAIL, tenant_role="Tenant Admin")
		self.assertEqual(first["invitation"], second["invitation"])
		self.assertEqual(frappe.db.get_value("QTT Invitation", first["invitation"], "tenant_role"), "Tenant Admin")

	def test_revoked_invitation_cannot_be_accepted(self):
		invite_result = api_invitation.invite_user(self.tenant.name, _INVITEE_EMAIL, tenant_role="Member")
		api_invitation.revoke_invitation(self.tenant.name, invite_result["invitation"])
		token = frappe.db.get_value("QTT Invitation", invite_result["invitation"], "token")

		result = api_invitation.accept_invitation(token, full_name="X", password="StrongPassword123!")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "INVALID_INVITATION")
