import unittest

from qtt_platform import perf_rules as r


class TestPerfRules(unittest.TestCase):
	def test_endpoint(self):
		self.assertEqual(r.endpoint("/api/method/qtt_platform.api.home.overview?x=1"), "qtt_platform.api.home.overview")
		self.assertEqual(r.endpoint("/api/v2/method/frappe.auth.get_logged_user"), "frappe.auth.get_logged_user")
		self.assertEqual(r.endpoint("/api/resource/CRM%20Lead/abc"), "resource:CRM Lead")
		self.assertIsNone(r.endpoint("/app/home"))
		self.assertIsNone(r.endpoint(None))

	def test_source(self):
		self.assertEqual(r.source("qtt_platform.api.home.overview", "a@b.in", "Mozilla/5.0"), "app")
		self.assertEqual(r.source("qtt_platform.api.home.overview", "a@b.in", "Dart/3.5 (dart:io)"), "app")
		self.assertEqual(r.source("qtt_platform.api.home.overview", "Guest", "Mozilla/5.0"), "other")
		self.assertEqual(r.source("qtt_platform.api.servers.ingest", "a@b.in", "Mozilla/5.0"), "other")
		self.assertEqual(r.source("x.y", "a@b.in", "n8n"), "other")
		self.assertEqual(r.source("qtt_platform.api.team_calls.webhook", "a@b.in", "x"), "other")

	def test_buckets(self):
		self.assertEqual(r.bucket(1), 0)
		self.assertEqual(r.bucket(10 ** 9), r.BUCKETS - 1)
		for ms in (6, 50, 333, 1000, 9000):
			b = r.bucket(ms)
			self.assertLessEqual(ms, r.bucket_ms(b) + 1)
			self.assertGreater(ms, r.bucket_ms(b - 1) - 1)

	def test_roll_and_percentiles(self):
		lines = [r.pack("a.b", ms, 200, "app") for ms in range(1, 101)] + [r.pack("a.b", 5000, 500, "app"), "junk"]
		rolled = r.roll(lines)
		row = rolled[("app", "a.b")]
		self.assertEqual(row["calls"], 101)
		self.assertEqual(row["errors"], 1)
		self.assertEqual(rolled[("app", "*")]["calls"], 101)
		s = r.summary(row["hist"])
		self.assertTrue(45 <= s["p50"] <= 62, s)
		self.assertTrue(90 <= s["p95"] <= 115, s)
		self.assertIsNone(r.percentile({}, 50))

	def test_merge_hours(self):
		h1 = r.roll([r.pack("a", 100, 200, "app")] * 10)[("app", "a")]["hist"]
		h2 = r.roll([r.pack("a", 2000, 200, "app")] * 10)[("app", "a")]["hist"]
		import json
		m = r.merge([json.dumps(h1), h2])
		self.assertEqual(sum(m.values()), 20)
		self.assertGreaterEqual(r.percentile(m, 95), 2000)

	def test_change(self):
		self.assertEqual(r.change(1000, 400), 60)
		self.assertEqual(r.change(1000, 1200), -20)
		self.assertIsNone(r.change(None, 5))

	def test_clean_screens(self):
		got = r.clean_screens('[{"screen": "home.overview", "ms": 820}, {"screen": "<x>", "ms": "12", "copy": true}, {"ms": 3}, "x", {"screen": "a", "ms": -1}]')
		self.assertEqual(got, [("home.overview", 820, False), ("x", 12, True)])
		self.assertEqual(r.clean_screens("nope"), [])


if __name__ == "__main__":
	unittest.main()
