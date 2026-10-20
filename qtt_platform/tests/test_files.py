"""
Office Pulse Files — sharing and file control rules (PROJ-0016 A), no bench.

    python -m unittest qtt_platform.tests.test_files -v
"""

import unittest
from datetime import datetime, timedelta

from qtt_platform import files_rules as r

NOW = datetime(2026, 10, 20, 12, 0)


class Rights(unittest.TestCase):
	def test_spaces(self):
		self.assertEqual(r.space_rights("team", hr=False, admin=False), r.FULL)
		self.assertEqual(r.space_rights("company", hr=False, admin=False), {"read"})
		self.assertEqual(r.space_rights("company", hr=True, admin=False), r.FULL)
		self.assertEqual(r.space_rights("hr", hr=False, admin=False), frozenset())
		self.assertEqual(r.space_rights("mydocs", hr=True, admin=True), {"read"})

	def test_folder_rules_deepest_and_most_personal_win(self):
		rules = [{"path": "Payroll", "who_type": "everyone", "rights": ""},
				 {"path": "Payroll", "who_type": "role", "who": "HR Admin", "rights": "read,write,create,delete"},
				 {"path": "Payroll/2026", "who_type": "user", "who": "ann@x.com", "rights": "read"}]
		base = r.FULL
		self.assertEqual(r.folder_rights(base, rules, "Payroll/a.pdf", user="bo@x.com", roles={"HR"}), frozenset())  # nobody else
		self.assertEqual(r.folder_rights(base, rules, "Payroll/a.pdf", user="bo@x.com", roles={"HR Admin"}), {"read", "write", "create", "delete"})
		self.assertEqual(r.folder_rights(base, rules, "Payroll/2026/m.pdf", user="ann@x.com", roles={"HR Admin"}), {"read"})  # deeper wins
		self.assertEqual(r.folder_rights(base, rules, "Payrolls/x.pdf", user="bo@x.com", roles=set()), base)  # not a prefix match
		self.assertEqual(r.folder_rights(base, rules, "../Payroll/a.pdf", user="bo@x.com", roles=set()), frozenset())  # can't climb past

	def test_lock(self):
		self.assertEqual(r.without_lock(r.FULL, "ann", NOW + timedelta(hours=1), "bo", NOW), {"read", "create", "share"})
		self.assertEqual(r.without_lock(r.FULL, "ann", NOW + timedelta(hours=1), "ann", NOW), r.FULL)  # the one who locked it
		self.assertEqual(r.without_lock(r.FULL, "ann", NOW - timedelta(hours=1), "bo", NOW), r.FULL)  # lock ran out


class Links(unittest.TestCase):
	def test_keys_and_passwords(self):
		k = r.new_key()
		self.assertGreaterEqual(len(k), 32)
		self.assertNotEqual(k, r.new_key())
		self.assertEqual(r.key_hash(k), r.key_hash(k))
		h = r.hash_password("s3cret!")
		self.assertTrue(r.check_password("s3cret!", h))
		self.assertFalse(r.check_password("s3cret", h))
		self.assertNotIn("s3cret", h)
		self.assertFalse(r.check_password("x", ""))

	def test_expiry(self):
		self.assertEqual(r.expires_at("1h", NOW), NOW + timedelta(hours=1))
		self.assertEqual(r.expires_at("7d", NOW), NOW + timedelta(days=7))
		self.assertEqual(r.expires_at("date", NOW, "2026-11-01"), datetime(2026, 11, 1, 23, 59, 59))
		self.assertIsNone(r.expires_at("", NOW))
		with self.assertRaises(ValueError):
			r.expires_at("date", NOW, "2026-10-01")

	def test_state(self):
		link = {"status": "Active", "mode": "download", "max_views": 3, "views": 1, "max_downloads": 1, "downloads": 0}
		self.assertEqual(r.link_state(link, NOW), "ok")
		self.assertEqual(r.link_state({**link, "status": "Revoked"}, NOW), "revoked")
		self.assertEqual(r.link_state({**link, "expires_at": NOW - timedelta(seconds=1)}, NOW), "expired")
		self.assertEqual(r.link_state({**link, "views": 3}, NOW), "used_up")
		self.assertEqual(r.link_state({**link, "downloads": 1}, NOW, "download"), "used_up")
		self.assertEqual(r.link_state({**link, "mode": "preview"}, NOW, "download"), "no")  # preview only
		self.assertEqual(r.link_state({**link, "mode": "upload"}, NOW, "view"), "no")  # File Drop shows nothing
		self.assertEqual(r.link_state({**link, "mode": "upload"}, NOW, "upload"), "ok")

	def test_emails(self):
		link = {"allowed_emails": "Ann@X.com, bo@y.in;junk"}
		self.assertEqual(r.emails(link["allowed_emails"]), ["ann@x.com", "bo@y.in"])
		self.assertTrue(r.needs_email(link))
		self.assertTrue(r.email_allowed(link, " ANN@x.com"))
		self.assertFalse(r.email_allowed(link, "eve@x.com"))
		self.assertTrue(r.email_allowed({"require_approval": 1}, "anyone@z.com"))
		self.assertFalse(r.needs_email({}))
		self.assertRegex(r.new_code(), r"^\d{6}$")


if __name__ == "__main__":
	unittest.main()
