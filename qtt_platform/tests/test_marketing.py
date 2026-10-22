"""
Bench-independent tests for the n8n client and the QTT Admin → Marketing
summary (qtt_platform.marketing.n8n — no frappe import).

    python -m unittest qtt_platform.tests.test_marketing -v
"""

import unittest
from datetime import datetime, timezone

import sys

# Another test module swaps in a stub `requests` (test_billing_subscriptions); this one needs the real library.
if not hasattr(sys.modules.get("requests"), "RequestException"):
	sys.modules.pop("requests", None)
import requests  # noqa: E402

from qtt_platform.marketing.n8n import N8nClient, N8nError, run_row, summarize

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class FakeResponse:
	def __init__(self, status, body=None):
		self.status_code = status
		self._body = body

	def json(self):
		if self._body is None:
			raise ValueError("no json")
		return self._body


class FakeSession:
	def __init__(self, *responses):
		self.responses = list(responses)
		self.calls = []

	def request(self, method, url, params=None, headers=None, timeout=None, json=None):
		self.calls.append((method, url, params, headers))
		nxt = self.responses.pop(0)
		if isinstance(nxt, Exception):
			raise nxt
		return nxt


def client(*responses):
	session = FakeSession(*responses)
	return N8nClient("https://n8n.example.com/", "KEY", session=session), session


class ClientTest(unittest.TestCase):
	def test_workflows_follow_cursor_and_send_key(self):
		c, s = client(
			FakeResponse(200, {"data": [{"id": "a"}], "nextCursor": "c2"}),
			FakeResponse(200, {"data": [{"id": "b"}], "nextCursor": None}),
		)
		self.assertEqual([w["id"] for w in c.workflows()], ["a", "b"])
		self.assertEqual(s.calls[0][1], "https://n8n.example.com/api/v1/workflows")
		self.assertEqual(s.calls[1][2], {"limit": 250, "cursor": "c2"})
		self.assertEqual(s.calls[0][3]["X-N8N-API-KEY"], "KEY")

	def test_activate_and_deactivate_paths(self):
		c, s = client(FakeResponse(200, {"id": "w1", "active": True}), FakeResponse(200, {"id": "w1", "active": False}))
		c.set_active("w1", True)
		c.set_active("w1", False)
		self.assertEqual([x[:2] for x in s.calls], [
			("POST", "https://n8n.example.com/api/v1/workflows/w1/activate"),
			("POST", "https://n8n.example.com/api/v1/workflows/w1/deactivate"),
		])

	def test_errors_are_friendly_and_never_contain_the_key(self):
		cases = [
			FakeResponse(401, {}),
			FakeResponse(404, {}),
			FakeResponse(500, {}),
			FakeResponse(200, None),
			requests.ConnectionError("boom"),
			requests.Timeout("slow"),
		]
		for case in cases:
			c, _ = client(case)
			with self.subTest(case=case), self.assertRaises(N8nError) as ctx:
				c.executions()
			self.assertNotIn("KEY", str(ctx.exception))

	def test_needs_url_and_key(self):
		with self.assertRaises(N8nError):
			N8nClient("", "KEY")
		with self.assertRaises(N8nError):
			N8nClient("https://n8n.example.com", "")


class SummaryTest(unittest.TestCase):
	WORKFLOWS = [
		{"id": "ok", "name": "Daily report", "active": True, "nodes": [{"type": "n8n-nodes-base.scheduleTrigger"}]},
		{"id": "bad", "name": "Website report", "active": True, "nodes": [{"type": "n8n-nodes-base.webhook"}], "tags": [{"name": "web"}]},
		{"id": "off", "name": "Old campaign", "active": False, "nodes": []},
	]
	EXECUTIONS = [
		{"id": 3, "workflowId": "bad", "status": "error", "startedAt": "2026-10-10T11:58:00.000Z", "stoppedAt": "2026-10-10T11:58:02.500Z"},
		{"id": 2, "workflowId": "bad", "status": "error", "startedAt": "2026-10-10T11:56:00.000Z"},
		{"id": 1, "workflowId": "ok", "status": "success", "startedAt": "2026-10-10T08:00:00.000Z", "stoppedAt": "2026-10-10T08:00:30.000Z"},
		{"id": 0, "workflowId": "ok", "status": "error", "startedAt": "2026-10-08T08:00:00.000Z"},  # older than 24 h
	]

	def test_failing_first_and_counts(self):
		s = summarize(self.WORKFLOWS, self.EXECUTIONS, now=NOW)
		self.assertEqual([w["id"] for w in s["workflows"]], ["bad", "ok", "off"])
		bad, ok, off = s["workflows"]
		self.assertEqual((bad["runs_24h"], bad["failed_24h"]), (2, 2))
		self.assertEqual(bad["last_run"]["id"], "3")
		self.assertEqual(bad["last_run"]["duration_ms"], 2500)
		self.assertEqual(bad["trigger"], "webhook")
		self.assertEqual(bad["tags"], ["web"])
		self.assertEqual((ok["failed_24h"], ok["last_run"]["status"]), (0, "success"))
		self.assertEqual(ok["trigger"], "schedule")
		self.assertIsNone(off["last_run"])
		self.assertEqual(s["totals"], {"workflows": 3, "active": 2, "runs_24h": 3, "failed_24h": 2, "failing_workflows": 1})

	def test_old_n8n_without_status_field(self):
		self.assertEqual(run_row({"id": 1, "finished": True})["status"], "success")
		self.assertEqual(run_row({"id": 1, "finished": False})["status"], "failed")
		self.assertEqual(run_row({"id": 1, "status": "crashed"})["status"], "failed")
		self.assertEqual(run_row({"id": 1, "status": "running"})["status"], "running")


if __name__ == "__main__":
	unittest.main()
