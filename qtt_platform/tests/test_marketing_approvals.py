"""
Bench-independent tests for marketing approvals (qtt_platform.marketing.approvals).

    python -m unittest qtt_platform.tests.test_marketing_approvals -v
"""

import unittest
from datetime import datetime

from qtt_platform.marketing import approvals as a

NOW = datetime(2026, 10, 10, 12, 0)


class ApprovalTest(unittest.TestCase):
	def test_tokens_and_links(self):
		t = a.new_token()
		self.assertTrue(len(t) >= 30)
		self.assertTrue(a.token_ok(t, t))
		self.assertFalse(a.token_ok(t, t + "x"))
		self.assertFalse(a.token_ok(None, ""))
		links = a.decision_links("https://app.example.com/", "abc", "TOK")
		self.assertEqual(links["approve_url"],
						 "https://app.example.com/api/method/qtt_platform.api.marketing_content.slack_decide?name=abc&token=TOK&decision=approve")
		self.assertTrue(links["reject_url"].endswith("&decision=reject"))

	def test_only_pending_and_unexpired_can_be_decided(self):
		a.check_decidable(status="pending", expires_at=datetime(2026, 10, 11), now=NOW)
		with self.assertRaises(a.ApprovalError):
			a.check_decidable(status="approved", expires_at=None, now=NOW)
		with self.assertRaises(a.ApprovalError):
			a.check_decidable(status="pending", expires_at=datetime(2026, 10, 10, 11), now=NOW)

	def test_resume_payload_matches_slack_send_and_wait_shape(self):
		self.assertEqual(a.resume_payload(True, via="app", note=None, user="s@q.in"),
						 {"data": {"approved": True}, "decided_via": "app", "note": "", "decided_by": "s@q.in"})

	def test_run_and_timeout_statuses(self):
		self.assertEqual(a.status_after_run("approved", "success"), "published")
		self.assertEqual(a.status_after_run("approved", "error"), "failed")
		self.assertEqual(a.status_after_run("approved", "running"), "approved")
		self.assertEqual(a.status_after_run("rejected", "success"), "rejected")
		self.assertEqual(a.expired_status("approve"), "approved")
		self.assertEqual(a.expired_status("reject"), "expired")

	def test_clean_new(self):
		c = a.clean_new({"kind": "LinkedIn", "title": " Post ", "expires_in_hours": "500", "preview_url": "javascript:x",
						 "resume_url": "https://n8n.example.com/webhook-waiting/12", "timeout_action": "approve"})
		self.assertEqual((c["kind"], c["title"], c["expires_in_hours"], c["preview_url"], c["timeout_action"]),
						 ("linkedin", "Post", 336, None, "approve"))
		self.assertEqual(a.clean_new({"kind": "weird", "title": "x"})["kind"], "other")
		with self.assertRaises(a.ApprovalError):
			a.clean_new({"title": "  "})


if __name__ == "__main__":
	unittest.main()
