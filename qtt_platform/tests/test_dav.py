"""
Office Pulse Files over WebDAV (PROJ-0016 E2) — folders, sync passwords, desktop clutter. No bench.

    python -m unittest qtt_platform.tests.test_dav -v
"""

import unittest

from qtt_platform import dav_rules as d


class Paths(unittest.TestCase):
	def test_split(self):
		self.assertEqual(d.split("/"), ("", ""))
		self.assertEqual(d.split("/Team files"), ("team", ""))
		self.assertEqual(d.split("/Team files/Plans/a b.xlsx"), ("team", "Plans/a b.xlsx"))
		self.assertEqual(d.split("My files/x/"), ("mine", "x"))
		self.assertEqual(d.split("/Nope/x"), ("?", ""))
		with self.assertRaises(ValueError):
			d.split("/Team files/../My files")

	def test_join_and_tops(self):
		self.assertEqual(d.join("team", "Plans/a.xlsx"), "/Team files/Plans/a.xlsx")
		self.assertEqual(d.join("shared", ""), "/Shared with me")
		self.assertNotIn("HR", d.top_folders(False))
		self.assertIn("HR", d.top_folders(True))
		self.assertEqual(d.top_folders(False)[0], "Team files")

	def test_junk(self):
		for n in ("._report.pdf", ".DS_Store", "Thumbs.db", "desktop.ini", "~$Budget.xlsx", ".~lock.a.odt#"):
			self.assertTrue(d.is_junk(n), n)
		for n in ("report.pdf", ".env.example", "Thumbs up.jpg"):
			self.assertFalse(d.is_junk(n), n)

	def test_unique_names(self):
		self.assertEqual(d.unique_names(["Plan.pdf", "plan.pdf", "Plans", "Plans"]), ["Plan.pdf", "plan (2).pdf", "Plans", "Plans (2)"])


class Passwords(unittest.TestCase):
	def test_new_and_check(self):
		p = d.new_password()
		self.assertRegex(p, r"^[a-z2-9]{4}(-[a-z2-9]{4}){3}$")
		self.assertNotRegex(p, r"[01ilo]")
		h, salt = d.hash_password(p)
		self.assertTrue(d.check_password(p, h, salt))
		self.assertTrue(d.check_password(p.replace("-", "").upper(), h, salt))  # typed without dashes, in capitals
		self.assertTrue(d.check_password(" " + p + " ", h, salt))
		self.assertFalse(d.check_password(p[:-1] + ("a" if p[-1] != "a" else "b"), h, salt))
		self.assertNotEqual(d.hash_password(p)[0], h)  # a new salt each time
		self.assertEqual(d.hint("abcd-efgh-jkmn-pqrs"), "…pqrs")


if __name__ == "__main__":
	unittest.main()
