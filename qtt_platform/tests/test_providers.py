"""
Bench-independent tests for QTT Admin → Servers / Domains provider data
(qtt_platform.ops.providers).

    python -m unittest qtt_platform.tests.test_providers -v
"""

import unittest
from datetime import date, datetime

from qtt_platform import saas_admin_logic as logic
from qtt_platform.ops import providers as p

NOW = datetime(2026, 10, 11, 12, 0)
TODAY = date(2026, 10, 11)


class _Resp:
	def __init__(self, data, status=200):
		self._data, self.status_code = data, status

	def json(self):
		return self._data


class FakeHttp:
	"""Answers by URL; records every call so tests can check nothing but reads happen."""

	def __init__(self, routes):
		self.routes, self.calls = routes, []

	def _answer(self, method, url):
		self.calls.append((method, url))
		for part, resp in self.routes.items():
			if part in url:
				return resp
		return _Resp({"message": "not found"}, 404)

	def get(self, url, **_):
		return self._answer("GET", url)

	def post(self, url, **_):
		return self._answer("POST", url)


class SnapshotRules(unittest.TestCase):
	def test_newest_snapshot_wins(self):
		s = p.snapshot_state([
			{"created": "2026-09-01T10:00:00Z", "auto_delete": "2026-10-01T10:00:00Z"},
			{"created": "2026-10-11T06:52:42.024Z", "auto_delete": "2026-11-10T08:52:42.023Z"},
		])
		self.assertEqual(s["snapshot_count"], 2)
		self.assertEqual(s["last_snapshot_at"], datetime(2026, 10, 11, 6, 52, 42, 24000))
		self.assertEqual(s["snapshot_auto_delete"].date(), date(2026, 11, 10))

	def test_no_snapshots(self):
		self.assertEqual(p.snapshot_state([]), {"last_snapshot_at": None, "snapshot_auto_delete": None, "snapshot_count": 0})

	def test_notices(self):
		self.assertIn("No Contabo snapshot", p.server_notices(last_snapshot_at=None, snapshot_auto_delete=None, provider_status="running", now=NOW)[0])
		fresh = p.server_notices(last_snapshot_at=datetime(2026, 10, 10), snapshot_auto_delete=datetime(2026, 11, 9), provider_status="running", now=NOW)
		self.assertEqual(fresh, [])
		old = p.server_notices(last_snapshot_at=datetime(2026, 9, 1), snapshot_auto_delete=datetime(2026, 10, 14), provider_status="stopped", now=NOW)
		self.assertTrue(any("stopped" in n for n in old))
		self.assertTrue(any("days old" in n for n in old))
		self.assertTrue(any("2026-10-14" in n for n in old))


class DomainRules(unittest.TestCase):
	def level(self, expires, status="active", watch=True):
		return p.domain_level(status=status, expires_on=expires, today=TODAY, warn_days=30, watch=watch)

	def test_levels(self):
		self.assertEqual(self.level("2027-04-20"), ("ok", 191))
		self.assertEqual(self.level("2026-11-05")[0], "warning")
		self.assertEqual(self.level("2026-10-15")[0], "critical")
		self.assertEqual(self.level("2026-09-13", status="expired")[0], "critical")

	def test_not_watched(self):
		self.assertEqual(self.level("2026-09-13", status="expired", watch=False)[0], "lapsed")
		self.assertEqual(self.level("2026-10-15", watch=False)[0], "ignored")


class ProviderCalls(unittest.TestCase):
	def test_contabo_inventory_reads_only(self):
		http = FakeHttp({
			"openid-connect/token": _Resp({"access_token": "t"}),
			"/snapshots": _Resp({"data": [{"name": "s1", "createdDate": "2026-10-11T06:52:42Z", "autoDeleteDate": "2026-11-10T08:52:42Z"}]}),
			"/compute/instances?": _Resp({"data": [{"instanceId": 202748666, "name": "vmi2748666", "displayName": "Frappe",
													 "ipConfig": {"v4": {"ip": "185.217.127.94"}}, "status": "running",
													 "productName": "VPS 10", "cpuCores": 3, "ramMb": 8192, "diskMb": 76800}]}),
		})
		out = p.contabo_inventory("id", "secret", "user", "pw", http=http)
		self.assertEqual(out[0]["ip"], "185.217.127.94")
		self.assertEqual(out[0]["plan"], "VPS 10 · 3 CPU · 8 GB RAM · 75 GB disk")
		self.assertEqual(len(out[0]["snapshots"]), 1)
		self.assertEqual([m for m, _ in http.calls], ["POST", "GET", "GET"])  # token, then reads only

	def test_contabo_bad_login(self):
		http = FakeHttp({"openid-connect/token": _Resp({"error": "invalid_grant", "error_description": "Invalid user credentials"}, 401)})
		with self.assertRaisesRegex(p.ProviderError, "Invalid user credentials"):
			p.contabo_inventory("id", "secret", "user", "bad", http=http)

	def test_hostinger_domains(self):
		http = FakeHttp({"/portfolio": _Resp([
			{"domain": "queentouchtech.com", "type": "domain", "status": "active", "expires_at": "2027-04-20T13:52:01Z"},
			{"domain": "tabletap.in", "type": "domain", "status": "expired", "expires_at": "2026-09-13T00:00:00Z"},
		])})
		self.assertEqual(p.hostinger_domains("tok", http=http)[1], {"domain": "tabletap.in", "status": "expired", "expires_on": "2026-09-13"})

	def test_hostinger_error(self):
		http = FakeHttp({"/portfolio": _Resp({"message": "Unauthenticated."}, 401)})
		with self.assertRaisesRegex(p.ProviderError, "Unauthenticated"):
			p.hostinger_domains("bad", http=http)


class Attention(unittest.TestCase):
	def test_domain_and_snapshot_items(self):
		items = logic.attention_items(
			domains=[{"domain": "truthofbible.org", "level": "warning", "days_left": 20}],
			snapshots=[{"key": "n8n", "title": "n8n", "days": None}],
			today_str="2026-10-11",
		)
		self.assertEqual([(i["kind"], i["level"]) for i in items], [("domain", "warning"), ("snapshot", "info")])
		self.assertEqual(items[0]["days"], 20)
		self.assertEqual(items[1]["area"], "servers")


if __name__ == "__main__":
	unittest.main()
