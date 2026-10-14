"""
Bench-independent tests for marketing approvals (qtt_platform.marketing.approvals).

    python -m unittest qtt_platform.tests.test_marketing_approvals -v
"""

import unittest
from datetime import datetime

from qtt_platform.marketing import approvals as a

NOW = datetime(2026, 10, 10, 12, 0)


class PolicyTest(unittest.TestCase):
	def test_what_silence_means(self):
		self.assertEqual(a.timeout_action("email_batch", {}), "approve")  # defaults: emails, LinkedIn, social go out
		self.assertEqual(a.timeout_action("linkedin", None), "approve")
		self.assertEqual(a.timeout_action("article", {}), "reject")  # articles need a yes
		self.assertEqual(a.timeout_action("other", {}), "reject")
		self.assertEqual(a.timeout_action("email_batch", {"email_batch_on_timeout": "Skip it"}), "reject")

	def test_reminder_once_before_the_deadline(self):
		from datetime import timedelta as td
		kw = dict(status="pending", created=NOW - td(hours=7), expires_at=NOW + td(minutes=50), reminded_at=None, minutes=60)
		self.assertTrue(a.reminder_due(now=NOW, **kw))
		self.assertFalse(a.reminder_due(now=NOW, **{**kw, "reminded_at": NOW}))
		self.assertFalse(a.reminder_due(now=NOW, **{**kw, "expires_at": NOW + td(hours=3)}))  # not yet
		self.assertFalse(a.reminder_due(now=NOW, **{**kw, "created": NOW - td(minutes=40)}))  # 90-minute window: no reminder
		self.assertFalse(a.reminder_due(now=NOW, **{**kw, "status": "approved"}))
		self.assertTrue(a.timed_out(status="pending", now=NOW, expires_at=NOW))
		self.assertFalse(a.timed_out(status="pending", now=NOW, expires_at=NOW + td(seconds=1)))

	def test_workflow_follows_the_policy(self):
		wf = {"name": "LinkedIn", "settings": {"executionOrder": "v1", "callerPolicy": "x"}, "connections": {"a": 1},
			  "nodes": [{"name": "Wait for decision", "parameters": {"resumeAmount": 12}, "extra": 1},
						{"name": "Decision", "parameters": {"jsCode": "const approved = b && b.data ? !!b.data.approved : false;"}}]}
		body = a.with_policy(wf, True, 12, ("name", "parameters"))
		self.assertEqual(body["nodes"][0]["parameters"]["resumeAmount"], 13)
		self.assertIn("b.data.approved : true", body["nodes"][1]["parameters"]["jsCode"])
		self.assertEqual(body["settings"], {"executionOrder": "v1"})
		self.assertNotIn("extra", body["nodes"][0])
		done = {**wf, "nodes": body["nodes"]}
		self.assertIsNone(a.with_policy(done, True, 12, ("name", "parameters")))  # already aligned


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
