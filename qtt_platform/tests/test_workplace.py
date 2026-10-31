"""
Team calls and the Office Pulse Workplace (PROJ-0015) — the rules, no bench.

    python -m unittest qtt_platform.tests.test_workplace -v
"""

import base64
import hashlib
import json
import unittest

from qtt_platform import workplace_rules as rules


class TestCallTokens(unittest.TestCase):
	def test_screen_sharing_only_with_pulse(self):
		self.assertEqual(rules.call_sources(False), ["microphone", "camera"])
		self.assertIn("screen_share", rules.call_sources(True))

	def test_token_is_livekits(self):
		t = rules.call_token(key="APIk", secret="s3cret", room="qtt-T1-general", user="a@x.com", name="Anna", screen_share=False, now=1000)
		claims = rules.jwt_verify(t, "s3cret", now=1100)
		self.assertEqual(claims["iss"], "APIk")
		self.assertEqual(claims["sub"], "a@x.com")
		self.assertEqual(claims["video"]["room"], "qtt-T1-general")
		self.assertTrue(claims["video"]["roomJoin"])
		self.assertNotIn("screen_share", claims["video"]["canPublishSources"])
		self.assertEqual(claims["exp"], 1000 + rules.TOKEN_TTL)

	def test_bad_or_old_tokens(self):
		t = rules.call_token(key="k", secret="s", room="r", user="u", name="n", screen_share=True, now=1000)
		self.assertIsNone(rules.jwt_verify(t, "other"))
		self.assertIsNone(rules.jwt_verify(t, "s", now=1000 + rules.TOKEN_TTL + 5))
		self.assertIsNone(rules.jwt_verify("nonsense", "s"))

	def test_webhook_signature(self):
		body = b'{"event":"room_finished"}'
		digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
		auth = rules.jwt_hs256({"iss": "k", "sha256": digest, "exp": 9999999999}, "s")
		self.assertTrue(rules.webhook_ok(body, auth, "s"))
		self.assertFalse(rules.webhook_ok(b'{"event":"other"}', auth, "s"))
		self.assertFalse(rules.webhook_ok(body, auth, "wrong"))

	def test_summary(self):
		self.assertEqual(rules.call_minutes(100, 100 + 30), 1)
		self.assertEqual(rules.call_minutes(100, 100 + 12 * 60), 12)
		self.assertEqual(rules.call_summary(False, 12, ["Anna", "Ravi"]), "📞 Call · 12 min · Anna, Ravi")
		self.assertEqual(rules.call_summary(True, 3, ["A", "B", "C", "D", "E", "F"]), "📹 Video call · 3 min · A, B, C, D +2")
		self.assertEqual(rules.call_summary(False, 0, []), "📞 Call · missed")


class TestFiles(unittest.TestCase):
	def test_spaces_in_the_store(self):
		self.assertEqual(rules.space_prefix("t1", "team"), "t1/team/")
		self.assertEqual(rules.space_prefix("t1", "company"), "t1/company/")
		self.assertEqual(rules.space_prefix("t1", "hr"), "t1/hr/")
		mine = rules.space_prefix("t1", "mine", "Anna@X.com")
		self.assertEqual(mine, rules.space_prefix("t1", "mine", "anna@x.com"))
		self.assertTrue(mine.startswith("t1/people/") and "anna" not in mine)  # no e-mail in the store
		self.assertNotEqual(mine, rules.space_prefix("t2", "mine", "anna@x.com"))  # each business its own
		self.assertEqual(rules.space_prefix("t1", "mydocs", hr_folder="People/Anna"), "t1/hr/People/Anna/")
		self.assertEqual(rules.space_prefix("t1", "mydocs"), "")  # HR hasn't made one
		self.assertEqual(rules.space_prefix("t1/../t2", "team"), "t1t2/team/")  # a business id can't climb out
		with self.assertRaises(ValueError):
			rules.space_prefix("t1", "everything")

	def test_paths_stay_inside(self):
		self.assertEqual(rules.clean_path("/a/../b//c/"), "a/b/c")
		self.assertEqual(rules.clean_path("..\\..\\etc"), "etc")
		self.assertNotIn("/", rules.clean_name("a/b"))
		self.assertEqual(rules.object_key("t1/team/", "../../t2/team/x.pdf"), "t1/team/t2/team/x.pdf")

	def test_kinds_and_new_docs(self):
		self.assertEqual(rules.kind_of_file("Budget.XLSX"), "cell")
		self.assertEqual(rules.kind_of_file("photo.jpg"), "image")
		self.assertEqual(rules.kind_of_file("QTT App Map.qttmap"), "appmap")  # the share page draws it
		self.assertEqual(rules.kind_of_file("x", True), "folder")
		self.assertTrue(rules.editable("Plan.docx"))
		self.assertFalse(rules.editable("photo.png"))
		self.assertEqual(rules.new_doc_name("cell", "Stock"), "Stock.xlsx")
		self.assertEqual(rules.new_doc_name("word", ""), "Document.docx")
		with self.assertRaises(ValueError):
			rules.new_doc_name("video", "x")

	def test_listing(self):
		from datetime import datetime, timezone

		items = rules.listing("t1/team/Plans/", ["t1/team/Plans/2026/", "t1/team/Plans/Old/"],
							  [{"Key": "t1/team/Plans/", "Size": 0},  # the folder's own marker
							   {"Key": "t1/team/Plans/Budget.xlsx", "Size": 2048, "LastModified": datetime(2026, 10, 20, 9, tzinfo=timezone.utc)},
							   {"Key": "t1/team/Plans/a.png", "Size": 10}])
		self.assertEqual([i["name"] for i in items], ["2026", "Old", "a.png", "Budget.xlsx"])
		self.assertTrue(items[0]["is_dir"])
		self.assertEqual(items[3]["size"], 2048)
		self.assertEqual(items[3]["type"], "cell")
		self.assertIsNotNone(items[3]["modified"])
		self.assertEqual(rules.human_size(2048), "2.0 KB")

	def test_trash_and_quota(self):
		self.assertEqual(rules.trash_key("t1/team/a.pdf", "2026-10-20"), "trash/2026-10-20/t1/team/a.pdf")
		self.assertEqual(rules.trash_days_to_purge(["2026-09-01", "2026-09-20", "2026-10-19", "junk"], "2026-10-20"), ["2026-09-01"])
		self.assertTrue(rules.fits(9 * 1024 ** 3, 10, 512 * 1024 ** 2))
		self.assertFalse(rules.fits(10 * 1024 ** 3, 10, 1))
		self.assertTrue(rules.fits(10 ** 12, None, 1))  # no quota (Company, HR)
		self.assertEqual(rules.free_bytes(1024 ** 3, 2), 1024 ** 3)
		self.assertIsNone(rules.free_bytes(5, None))

	def test_editor_config(self):
		c = rules.editor_config(name="Plan.docx", key="t1/team/Plan.docx", etag="e1", file_url="https://f", callback_url="https://cb",
								can_edit=True, user_id="u1", user_name="Ann")
		self.assertEqual((c["documentType"], c["document"]["fileType"], c["editorConfig"]["mode"]), ("word", "docx", "edit"))
		self.assertTrue(c["document"]["permissions"]["edit"])
		v = rules.editor_config(name="Plan.docx", key="t1/team/Plan.docx", etag="e1", file_url="f", callback_url="cb", can_edit=False,
								user_id="u2", user_name="Bo")
		self.assertEqual(v["editorConfig"]["mode"], "view")
		self.assertEqual(v["document"]["key"], c["document"]["key"])  # same file, same key: they edit together
		self.assertNotEqual(rules.doc_key("t1/team/Plan.docx", "e2"), c["document"]["key"])  # saved: a new key
		self.assertEqual(rules.editor_config(name="a.pdf", key="k", etag="e", file_url="f", callback_url="c", can_edit=True,
											 user_id="u", user_name="U")["editorConfig"]["mode"], "view")
		token = rules.jwt_hs256(c, "s3cret")
		self.assertEqual(rules.jwt_verify(token, "s3cret")["document"]["url"], "https://f")
		self.assertIsNone(rules.jwt_verify(token, "other"))


class TestRemote(unittest.TestCase):
	def test_config_string_round_trip(self):
		s = rules.rustdesk_config("remote.queentouchtech.in", "KEY123=")
		raw = s[::-1]
		data = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
		self.assertEqual(data["host"], "remote.queentouchtech.in")
		self.assertEqual(data["relay"], "remote.queentouchtech.in")
		self.assertEqual(data["key"], "KEY123=")

	def test_ids_and_links(self):
		self.assertEqual(rules.rustdesk_id("123 456 789"), "123456789")
		self.assertIsNone(rules.rustdesk_id("12ab"))
		self.assertEqual(rules.rustdesk_uri("123456789"), "rustdesk://connection/new/123456789")
		self.assertEqual(rules.rustdesk_uri("123456789", "p@ss w"), "rustdesk://connection/new/123456789?password=p%40ss%20w")

	def test_who_manages_computers(self):
		self.assertTrue(rules.can_manage_devices("Tenant Owner", None))
		self.assertTrue(rules.can_manage_devices("Member", "HR Admin"))
		self.assertFalse(rules.can_manage_devices("Member", "Employee"))


if __name__ == "__main__":
	unittest.main()
