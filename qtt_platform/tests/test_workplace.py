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
	def test_names(self):
		self.assertEqual(rules.cloud_user("Anna@X.com"), rules.cloud_user("anna@x.com"))
		self.assertTrue(rules.cloud_user("a@x.com").startswith("qtt-"))
		self.assertEqual(rules.cloud_group("T1"), "qtt-T1")
		self.assertEqual(rules.cloud_group("T1", "hr"), "qtt-T1-hr")
		self.assertEqual(rules.folder_name("Acme / Bakery", "team"), "Acme Bakery · Team files")
		self.assertEqual(rules.folder_name("Acme", "company"), "Acme · Company")

	def test_paths_stay_inside(self):
		self.assertEqual(rules.clean_path("/a/../b//c/"), "a/b/c")
		self.assertEqual(rules.clean_path("..\\..\\etc"), "etc")
		self.assertNotIn("/", rules.clean_name("a/b"))

	def test_kinds_and_new_docs(self):
		self.assertEqual(rules.kind_of_file("Budget.XLSX"), "cell")
		self.assertEqual(rules.kind_of_file("photo.jpg"), "image")
		self.assertEqual(rules.kind_of_file("x", True), "folder")
		self.assertTrue(rules.editable("Plan.docx"))
		self.assertFalse(rules.editable("photo.png"))
		self.assertEqual(rules.new_doc_name("cell", "Stock"), "Stock.xlsx")
		self.assertEqual(rules.new_doc_name("word", ""), "Document.docx")
		with self.assertRaises(ValueError):
			rules.new_doc_name("video", "x")

	def test_propfind(self):
		xml = """<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
<d:response><d:href>/remote.php/dav/files/qtt-1/Acme%20%C2%B7%20Team%20files/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype><oc:size>300</oc:size></d:prop></d:propstat></d:response>
<d:response><d:href>/remote.php/dav/files/qtt-1/Acme%20%C2%B7%20Team%20files/Plans/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype><oc:size>100</oc:size><oc:fileid>7</oc:fileid></d:prop></d:propstat></d:response>
<d:response><d:href>/remote.php/dav/files/qtt-1/Acme%20%C2%B7%20Team%20files/Budget.xlsx</d:href><d:propstat><d:prop><d:resourcetype/><d:getcontentlength>2048</d:getcontentlength><d:getlastmodified>Tue, 20 Oct 2026 09:00:00 GMT</d:getlastmodified></d:prop></d:propstat></d:response>
</d:multistatus>"""
		items = rules.parse_propfind(xml, "/remote.php/dav/files/qtt-1/Acme · Team files")
		self.assertEqual([i["name"] for i in items], ["Plans", "Budget.xlsx"])
		self.assertTrue(items[0]["is_dir"])
		self.assertEqual(items[1]["size"], 2048)
		self.assertEqual(items[1]["type"], "cell")
		self.assertIsNotNone(items[1]["modified"])
		self.assertEqual(rules.human_size(2048), "2.0 KB")


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
