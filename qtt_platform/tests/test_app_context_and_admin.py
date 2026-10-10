"""
Bench-independent tests for qtt_platform.realtime, api.app_context and
api.platform_admin, against a minimal fake `frappe` — same technique as
test_saas_signup.py. Each test re-imports the modules under test against
its own fake and restores sys.modules afterwards, so it neither sees nor
disturbs other test files' fakes.

    python -m unittest qtt_platform.tests.test_app_context_and_admin -v
"""

import importlib
import sys
import types
import unittest
from unittest import mock


class _PermissionError(Exception):
	pass


class _ValidationError(Exception):
	pass


class _DoesNotExistError(Exception):
	pass


def _fake_frappe(user="anna@acme.com", roles=()):
	fake = types.ModuleType("frappe")
	fake.PermissionError = _PermissionError
	fake.ValidationError = _ValidationError
	fake.DoesNotExistError = _DoesNotExistError

	def _throw(msg, exc=None, **kwargs):
		raise (exc or _ValidationError)(msg)

	fake.throw = _throw
	fake._ = lambda s: s
	fake.whitelist = lambda *a, **k: (lambda fn: fn)
	fake.session = types.SimpleNamespace(user=user)
	fake.local = types.SimpleNamespace(request_ip=None)
	fake.get_roles = mock.Mock(return_value=list(roles))
	fake.publish_realtime = mock.Mock()
	fake.get_all = mock.Mock(return_value=[])
	fake.get_doc = mock.Mock()
	fake.cache = mock.Mock()
	fake.db = types.SimpleNamespace(get_value=mock.Mock(return_value=None), sql=mock.Mock(return_value=[]), count=mock.Mock(return_value=0))
	utils = types.ModuleType("frappe.utils")
	utils.add_days = lambda d, n: d
	utils.now_datetime = lambda: "2026-10-10 00:00:00"
	utils.today = lambda: "2026-10-10"
	utils.get_url = lambda path="": "https://app.example.com" + (path or "")
	fake.utils = utils
	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = utils
	return fake


def _fresh(module_name):
	for name in list(sys.modules):
		if name.startswith("qtt_platform.") and name != "qtt_platform.tests" and not name.startswith("qtt_platform.tests"):
			sys.modules.pop(name, None)
	return importlib.import_module(module_name)


class _Row(dict):
	__getattr__ = dict.get


class _IsolatedTest(unittest.TestCase):
	"""Snapshot sys.modules before each test and restore it after, so the
	fake frappe and freshly imported qtt_platform modules used here never
	replace the ones other test files bound at import time."""

	def setUp(self):
		self._modules = dict(sys.modules)

	def tearDown(self):
		for name in list(sys.modules):
			if name not in self._modules:
				del sys.modules[name]
		sys.modules.update(self._modules)


class RealtimeTest(_IsolatedTest):
	def test_notify_dedupes_and_skips_system_users(self):
		fake = _fake_frappe()
		realtime = _fresh("qtt_platform.realtime")
		realtime.notify_users(["b@x.com", "a@x.com", "a@x.com", "Guest", "Administrator", None], tenant="T1", reason="r")
		users = [c.kwargs["user"] for c in fake.publish_realtime.call_args_list]
		self.assertEqual(users, ["a@x.com", "b@x.com"])
		call = fake.publish_realtime.call_args_list[0]
		self.assertEqual(call.args, ("qtt:context_changed", {"tenant": "T1", "reason": "r"}))
		self.assertTrue(call.kwargs["after_commit"])

	def test_tenant_change_notifies_all_active_members(self):
		fake = _fake_frappe()
		fake.get_all = mock.Mock(return_value=["a@x.com", "b@x.com"])
		realtime = _fresh("qtt_platform.realtime")
		realtime.on_tenant_change(types.SimpleNamespace(name="T1"))
		self.assertEqual(fake.publish_realtime.call_count, 2)
		self.assertEqual(fake.get_all.call_args.kwargs["filters"], {"tenant": "T1", "status": "active"})

	def test_product_access_change_resolves_membership_user(self):
		fake = _fake_frappe()
		fake.db.get_value = mock.Mock(return_value="anna@acme.com")
		realtime = _fresh("qtt_platform.realtime")
		realtime.on_product_access_change(types.SimpleNamespace(membership="M1", tenant="T1"))
		self.assertEqual(fake.publish_realtime.call_args.kwargs["user"], "anna@acme.com")


class AppContextTest(_IsolatedTest):
	def test_guest_rejected(self):
		_fake_frappe(user="Guest")
		app_context = _fresh("qtt_platform.api.app_context")
		with self.assertRaises(_PermissionError):
			app_context.get_app_context()

	def test_suspended_active_tenant_is_not_active_workspace(self):
		fake = _fake_frappe(roles=["QTT Platform Owner"])
		fake.cache.return_value.get_value = mock.Mock(return_value="T1")  # resolve_active_tenant
		fake.db.get_value = mock.Mock(return_value={"full_name": "Anna", "user_image": None})

		def get_all(doctype, **kwargs):
			if doctype == "QTT Tenant Membership":
				return [_Row(name="M1", tenant="T1", tenant_role="Tenant Owner")]
			if doctype == "QTT Tenant":
				return [_Row(name="T1", tenant_name="Acme", status="suspended", logo=None)]
			return []

		fake.get_all = mock.Mock(side_effect=get_all)
		app_context = _fresh("qtt_platform.api.app_context")
		ctx = app_context.get_app_context()
		self.assertTrue(ctx["user"]["is_platform_owner"])
		self.assertEqual(ctx["workspaces"][0]["tenant_status"], "suspended")
		self.assertIsNone(ctx["active_workspace"])
		self.assertEqual(ctx["products"], [])
		self.assertFalse(ctx["can_manage_workspace"])
		self.assertEqual(ctx["realtime"]["context_event"], "qtt:context_changed")

	def test_products_skip_disabled_and_carry_role(self):
		fake = _fake_frappe()
		fake.db.get_value = mock.Mock(return_value=None)

		def get_all(doctype, **kwargs):
			if doctype == "QTT Product Access":
				return [_Row(product="QTT_INBOX", product_role="Agent"), _Row(product="OLD", product_role="X")]
			if doctype == "QTT Product":
				return [_Row(name="QTT_INBOX", display_name="Inbox", icon=None, description="d")]
			return []

		fake.get_all = mock.Mock(side_effect=get_all)
		app_context = _fresh("qtt_platform.api.app_context")
		with mock.patch.object(app_context.subscription_service, "get_current_subscription", return_value=None):
			products = app_context._products({"membership": "M1", "tenant": "T1"})
		self.assertEqual([p["product"] for p in products], ["QTT_INBOX"])
		self.assertEqual(products[0]["role"], "Agent")
		self.assertIsNone(products[0]["subscription"])


	def test_workspace_products_only_open_subscriptions(self):
		fake = _fake_frappe()

		def get_all(doctype, **kwargs):
			if doctype == "QTT Tenant Product Subscription Pointer":
				return ["QTT_INBOX", "QTT_OFFICE_PULSE", "OLD"]
			if doctype == "QTT Product":
				return [_Row(name="QTT_INBOX", display_name="Inbox", icon=None, description=None),
						_Row(name="QTT_OFFICE_PULSE", display_name="Office Pulse", icon="badge", description=None),
						_Row(name="OLD", display_name="Old", icon=None, description=None)]
			return []

		fake.get_all = mock.Mock(side_effect=get_all)
		fake.db.get_value = mock.Mock(return_value="BUSINESS")
		app_context = _fresh("qtt_platform.api.app_context")
		subs = {"QTT_INBOX": "trialing", "QTT_OFFICE_PULSE": "trialing", "OLD": "cancelled"}
		with mock.patch.object(app_context.subscription_service, "get_current_subscription",
							   side_effect=lambda t, p: _Row(status=subs[p], plan="P", trial_end=None, current_period_end=None)):
			products = app_context._workspace_products("T1")
		# A product nobody has access to yet is still listed, so the owner can hand out access.
		self.assertEqual([p["product"] for p in products], ["QTT_INBOX", "QTT_OFFICE_PULSE"])
		self.assertEqual(products[1]["role"], "")


class PlatformAdminTest(_IsolatedTest):
	def test_every_endpoint_requires_platform_owner(self):
		_fake_frappe(roles=["System Manager"])
		admin = _fresh("qtt_platform.api.platform_admin")
		for call in (admin.overview, admin.list_tenants, lambda: admin.get_tenant("T1"), lambda: admin.set_tenant_status("T1", "suspended")):
			with self.subTest(call=call):
				with self.assertRaises(_PermissionError):
					call()

	def test_set_status_rejects_lifecycle_statuses(self):
		_fake_frappe(roles=["QTT Platform Owner"])
		admin = _fresh("qtt_platform.api.platform_admin")
		with self.assertRaises(_ValidationError):
			admin.set_tenant_status("T1", "cancelled")

	def test_set_status_saves_and_audits(self):
		fake = _fake_frappe(roles=["QTT Platform Owner"])
		doc = mock.Mock(status="active")
		fake.get_doc = mock.Mock(return_value=doc)
		admin = _fresh("qtt_platform.api.platform_admin")
		with mock.patch.object(admin, "write_audit_event") as audit:
			result = admin.set_tenant_status("T1", "suspended", reason="non-payment")
		self.assertEqual(result, {"tenant": "T1", "status": "suspended"})
		self.assertEqual(doc.status, "suspended")
		doc.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(audit.call_args.kwargs["before_state"], {"status": "active"})
		self.assertEqual(audit.call_args.kwargs["metadata"]["reason"], "non-payment")

	def test_page_length_is_capped(self):
		fake = _fake_frappe(roles=["QTT Platform Owner"])
		admin = _fresh("qtt_platform.api.platform_admin")
		result = admin.list_tenants(page_length=10_000)
		self.assertEqual(result["page_length"], 100)
		self.assertEqual(fake.get_all.call_args.kwargs["page_length"], 100)


if __name__ == "__main__":
	unittest.main()
