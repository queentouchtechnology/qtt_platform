"""
Bench-independent tests for the reporting layer (production-readiness
audit, P4) — `qtt_platform/api/reports.py`. Self-contained fake-frappe
install (same technique as qmp_lms_bridge's test_plans.py/test_usage.py)
since this module is new and nothing else in this test suite imports it
first — no risk of the cross-file fake-frappe binding caveat documented
in test_billing_subscriptions.py applying here.

Run manually from the qtt_platform repo root:

    python -m unittest qtt_platform.tests.test_reports -v
"""

import sys
import types
import unittest
from unittest import mock


class _FrappeDict(dict):
	"""Stands in for real Frappe's `frappe._dict` — a dict that ALSO
	supports attribute access, matching what `frappe.db.sql(...,
	as_dict=True)` actually returns and what every report function's own
	`row.status`-style access expects."""

	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError:
			return None


def _install_fake_frappe():
	class _ValidationError(Exception):
		pass

	class _PermissionError(Exception):
		pass

	fake_frappe = types.ModuleType("frappe")
	fake_frappe.ValidationError = _ValidationError
	fake_frappe.PermissionError = _PermissionError
	fake_frappe.throw = mock.Mock(side_effect=lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg)))
	fake_frappe._ = lambda s: s
	fake_frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	fake_frappe.db = types.SimpleNamespace(sql=mock.Mock(return_value=[]), count=mock.Mock(return_value=0))
	fake_frappe.session = types.SimpleNamespace(user="owner@example.com")
	fake_frappe.cache = mock.Mock(
		return_value=types.SimpleNamespace(get_value=mock.Mock(return_value=None), set_value=mock.Mock())
	)
	sys.modules["frappe"] = fake_frappe
	return fake_frappe


class GetReportTest(unittest.TestCase):
	def setUp(self):
		for mod in list(sys.modules):
			if mod.startswith("qtt_platform"):
				del sys.modules[mod]
		self.fake_frappe = _install_fake_frappe()
		import qtt_platform.api.reports as api_reports

		self.api_reports = api_reports

	def test_no_active_tenant_rejected(self):
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value=None):
			result = self.api_reports.get_report("revenue")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "TENANT_ACCESS_DENIED")

	def test_non_governance_role_rejected(self):
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(
				self.api_reports, "require_tenant_role", side_effect=self.fake_frappe.PermissionError("nope")
			):
				result = self.api_reports.get_report("revenue")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "ROLE_PERMISSION_DENIED")

	def test_unknown_report_key_rejected(self):
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				result = self.api_reports.get_report("not_a_real_report")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"]["code"], "REPORT_NOT_FOUND")

	def test_empty_state_returns_zeroed_summary_not_an_error(self):
		self.fake_frappe.db.sql = mock.Mock(return_value=[])
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				result = self.api_reports.get_report("revenue")
		self.assertTrue(result["success"], result)
		self.assertEqual(result["data"]["rows"], [])
		self.assertEqual(result["data"]["summary"]["payment_count"], 0)

	def test_revenue_report_scopes_by_tenant_via_invoice_join(self):
		self.fake_frappe.db.sql = mock.Mock(return_value=[])
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				self.api_reports.get_report("revenue")
		sql_text, params = self.fake_frappe.db.sql.call_args[0]
		self.assertIn("QTT Payment", sql_text)
		self.assertIn("QTT Invoice", sql_text)
		self.assertEqual(params[0], "tenant-1")

	def test_revenue_report_sums_succeeded_and_refunded_separately(self):
		self.fake_frappe.db.sql = mock.Mock(
			return_value=[
				_FrappeDict(name="p1", invoice="inv-1", amount=100, currency="INR", status="succeeded",
				            paid_at="2026-08-01", refund_of=None),
				_FrappeDict(name="p2", invoice="inv-2", amount=20, currency="INR", status="refunded",
				            paid_at="2026-08-02", refund_of="p1"),
			]
		)
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				result = self.api_reports.get_report("revenue")
		summary = result["data"]["summary"]
		self.assertEqual(summary["total_revenue"], 100)
		self.assertEqual(summary["total_refunded"], 20)
		self.assertEqual(summary["net_revenue"], 80)
		self.assertEqual(summary["payment_count"], 2)

	def test_date_filter_omits_clause_when_no_dates_given(self):
		self.fake_frappe.db.sql = mock.Mock(return_value=[])
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				self.api_reports.get_report("ai_usage")
		sql_text, params = self.fake_frappe.db.sql.call_args[0]
		self.assertNotIn("BETWEEN", sql_text)
		self.assertEqual(params, ["tenant-1"])

	def test_date_filter_applies_both_bounds_when_given(self):
		self.fake_frappe.db.sql = mock.Mock(return_value=[])
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				self.api_reports.get_report("ai_usage", date_from="2026-08-01", date_to="2026-08-31")
		sql_text, params = self.fake_frappe.db.sql.call_args[0]
		self.assertIn("BETWEEN", sql_text)
		self.assertEqual(params, ["tenant-1", "2026-08-01", "2026-08-31"])

	def test_team_growth_report_is_scoped_to_own_tenant_only(self):
		# Regression guard for the cross-tenant-leak bug caught while
		# implementing this report — must never aggregate across tenants.
		self.fake_frappe.db.sql = mock.Mock(return_value=[])
		self.fake_frappe.db.count = mock.Mock(return_value=5)
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				result = self.api_reports.get_report("team_growth")
		sql_text, params = self.fake_frappe.db.sql.call_args[0]
		self.assertIn("QTT Tenant Membership", sql_text)
		self.assertEqual(params[0], "tenant-1")
		self.fake_frappe.db.count.assert_called_once_with(
			"QTT Tenant Membership", {"tenant": "tenant-1", "status": "active"}
		)
		self.assertEqual(result["data"]["summary"]["total_active_members"], 5)

	def test_all_six_reports_are_registered_and_callable(self):
		self.fake_frappe.db.sql = mock.Mock(return_value=[])
		with mock.patch.object(self.api_reports, "resolve_active_tenant", return_value="tenant-1"):
			with mock.patch.object(self.api_reports, "require_tenant_role"):
				for key in (
					"revenue",
					"subscription_lifecycle",
					"ai_usage",
					"audit_log",
					"team_activity",
					"team_growth",
				):
					result = self.api_reports.get_report(key)
					self.assertTrue(result["success"], f"{key}: {result}")
					self.assertIn("summary", result["data"])
					self.assertIn("rows", result["data"])


if __name__ == "__main__":
	unittest.main()
