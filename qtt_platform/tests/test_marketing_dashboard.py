"""
Bench-independent tests for the marketing dashboard: n8n run-time editing
(marketing/n8n_schedule.py) and the day report / plan rules
(marketing/report.py). No frappe import.

    python -m unittest qtt_platform.tests.test_marketing_dashboard -v
"""

import re
import unittest
from datetime import date, datetime, timedelta

from qtt_platform.marketing import n8n_schedule as sched
from qtt_platform.marketing import report as rpt


def wf(*rules, node_type=sched.SCHEDULE_TYPE, extra_nodes=()):
	return {
		"name": "Daily report",
		"nodes": [
			{"id": "1", "name": "Every day", "type": node_type, "typeVersion": 1.2, "position": [0, 0],
			 "parameters": {"rule": {"interval": list(rules)}}, "pinData": {"x": 1}},
			{"id": "2", "name": "Slack", "type": "n8n-nodes-base.slack", "parameters": {"text": "hi"}},
			*extra_nodes,
		],
		"connections": {"Every day": {"main": [[{"node": "Slack"}]]}},
		"settings": {"timezone": "Asia/Kolkata", "executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner"},
	}


class ScheduleTest(unittest.TestCase):
	def test_cron_for(self):
		self.assertEqual(sched.cron_for("08:00", ["mon", "tue", "wed", "thu", "fri"]), "0 8 * * 1-5")
		self.assertEqual(sched.cron_for("7:30", "sat,sun,mon"), "30 7 * * 0-1,6")
		self.assertEqual(sched.cron_for("23:05", list(sched.DAYS)), "5 23 * * *")
		with self.assertRaises(sched.ScheduleError):
			sched.cron_for("25:00", ["mon"])
		with self.assertRaises(sched.ScheduleError):
			sched.cron_for("08:00", [])
		with self.assertRaises(sched.ScheduleError):
			sched.cron_for("08:00", ["funday"])

	def test_summarize_shapes(self):
		self.assertEqual(sched.summarize(wf({"field": "cronExpression", "expression": "0 8 * * 1-6"}))["days"],
						 ["mon", "tue", "wed", "thu", "fri", "sat"])
		daily = sched.summarize(wf({"field": "days", "triggerAtHour": 8, "triggerAtMinute": 30}))
		self.assertEqual((daily["editable"], daily["time"], len(daily["days"])), (True, "08:30", 7))
		weekly = sched.summarize(wf({"field": "weeks", "triggerAtDay": [1, 3, 5], "triggerAtHour": 19}))
		self.assertEqual((weekly["time"], weekly["days"]), ("19:00", ["mon", "wed", "fri"]))
		# read-only shapes
		for workflow in (
			wf({"field": "hours", "hoursInterval": 2}),
			wf({"field": "cronExpression", "expression": "*/15 * * * *"}),
			wf({"field": "days"}, {"field": "days", "triggerAtHour": 13}),
			wf({"field": "days"}, node_type=sched.LEGACY_CRON_TYPE),
			wf({"field": "days"}, extra_nodes=[{"name": "Second", "type": sched.SCHEDULE_TYPE, "parameters": {}}]),
			{"name": "Webhook only", "nodes": [{"name": "Hook", "type": "n8n-nodes-base.webhook"}]},
		):
			with self.subTest(workflow=workflow["nodes"][0].get("parameters")):
				self.assertFalse(sched.summarize(workflow)["editable"])

	def test_with_schedule_changes_only_the_trigger(self):
		original = wf({"field": "days", "triggerAtHour": 8})
		body, old, new = sched.with_schedule(original, "07:30", ["mon", "tue", "wed", "thu", "fri", "sat"])
		self.assertEqual(old, {"interval": [{"field": "days", "triggerAtHour": 8}]})
		self.assertEqual(new, {"interval": [{"field": "cronExpression", "expression": "30 7 * * 1-6"}]})
		trigger, slack = body["nodes"]
		self.assertEqual(trigger["parameters"]["rule"], new)
		self.assertNotIn("pinData", trigger)  # not accepted by the API on PUT
		self.assertEqual(slack["parameters"], {"text": "hi"})
		self.assertEqual(body["settings"], {"timezone": "Asia/Kolkata", "executionOrder": "v1"})
		self.assertEqual(body["connections"], original["connections"])
		# the input is not mutated
		self.assertEqual(original["nodes"][0]["parameters"]["rule"]["interval"][0]["field"], "days")
		with self.assertRaises(sched.ScheduleError):
			sched.with_schedule(wf({"field": "hours", "hoursInterval": 2}), "08:00", ["mon"])


class ReportTest(unittest.TestCase):
	DAY = date(2026, 10, 12)  # Monday
	NOW = datetime(2026, 10, 12, 12, 0)
	SLOTS = [
		{"name": "s1", "title": "Daily report", "kind": "report", "start_time": "08:00", "days": "mon,tue,wed,thu,fri,sat,sun", "n8n_workflow_id": "wfR", "enabled": 1},
		{"name": "s2", "title": "Calls UK", "kind": "calls", "start_time": "14:30:00", "end_time": timedelta(hours=15, minutes=30), "days": "mon,tue,wed,thu,fri", "valid_to": "2026-10-25", "enabled": 1},
		{"name": "s3", "title": "Calls UK (winter)", "kind": "calls", "start_time": "15:30", "days": "mon,tue,wed,thu,fri", "valid_from": "2026-10-26", "enabled": 1},
		{"name": "s4", "title": "Calls TN", "kind": "calls", "start_time": "10:00", "end_time": "11:30", "days": "mon", "enabled": 1},
		{"name": "s5", "title": "Lunch", "kind": "task", "start_time": "11:30", "end_time": "13:00", "days": "mon", "enabled": 1},
		{"name": "s6", "title": "Research", "kind": "research", "start_time": "16:00", "days": "mon", "n8n_workflow_id": "wfX", "enabled": 1},
		{"name": "s7", "title": "Off", "kind": "task", "start_time": "09:00", "days": "mon", "enabled": 0},
		{"name": "s8", "title": "Saturday visit", "kind": "visit", "start_time": "14:00", "days": "sat", "enabled": 1},
		{"name": "s9", "title": "Social", "kind": "social", "start_time": "08:00", "days": "mon", "n8n_workflow_id": "wfS", "enabled": 1},
	]

	def build(self):
		return rpt.day_report(
			day=self.DAY, now=self.NOW, slots=self.SLOTS,
			workflows=[{"id": "wfR", "name": "Daily report"}, {"id": "wfS", "name": "Social"}],
			executions=[
				{"workflowId": "wfR", "status": "success", "startedAt": "2026-10-12T08:00:03"},
				{"workflowId": "wfS", "status": "error", "startedAt": "2026-10-12T08:00:10"},
			],
			crm={"leads": {"count": 4, "by": {"UAE": 4}}}, notes=["Holiday"], week=None,
		)

	def test_schedule_filters_and_orders(self):
		titles = [s["title"] for s in self.build()["schedule"]]
		self.assertEqual(titles, ["Daily report", "Social", "Calls TN", "Lunch", "Calls UK", "Research"])

	def test_statuses(self):
		status = {s["title"]: s["status"] for s in self.build()["schedule"]}
		self.assertEqual(status["Daily report"], "done")
		self.assertEqual(status["Social"], "failed")
		self.assertEqual(status["Calls TN"], "past")
		self.assertEqual(status["Lunch"], "now")
		self.assertEqual(status["Calls UK"], "upcoming")
		self.assertEqual(status["Research"], "upcoming")
		# a past day with no run = missed
		later = datetime(2026, 10, 13, 9, 0)
		self.assertEqual(rpt.slot_status(self.SLOTS[5], {}, day=self.DAY, now=later), "missed")

	def test_numbers_and_automations(self):
		r = self.build()
		self.assertEqual(r["numbers"]["leads"]["count"], 4)
		self.assertEqual(r["numbers"]["calls"], {"count": 0})
		self.assertEqual(r["automation_totals"], {"runs": 2, "failed": 1})
		self.assertEqual(r["automations"][0]["name"], "Social")  # failures first
		self.assertTrue(r["is_today"])

	def test_hhmm(self):
		self.assertEqual(rpt.hhmm("8:05:00"), "08:05")
		self.assertEqual(rpt.hhmm(timedelta(hours=19, minutes=30)), "19:30")
		self.assertIsNone(rpt.hhmm(None))


class PlanTest(unittest.TestCase):
	WEEKS = [
		{"label": "Week 2 (email 20/day)", "start_date": "2026-10-05", "end_date": "2026-10-11", "details": "Mon 5: Short 02\n- Wed 7: Short 03"},
		{"label": "Week 3", "start_date": "2026-10-12", "end_date": "2026-10-18", "details": "Mid-month review"},
	]

	def test_current_and_next_week(self):
		self.assertEqual(rpt.current_week(self.WEEKS, date(2026, 10, 7))["items"], ["Mon 5: Short 02", "Wed 7: Short 03"])
		self.assertEqual(rpt.current_week(self.WEEKS, date(2026, 10, 3))["label"], "Week 2 (email 20/day)")
		self.assertIsNone(rpt.current_week(self.WEEKS, date(2026, 10, 30)))

	def test_progress(self):
		rows = rpt.progress(
			[{"metric": "Emails", "target": "300–400", "target_number": 300, "metric_key": "emails_sent"},
			 {"metric": "Meetings", "target": "8–10", "target_number": 8, "metric_key": None}],
			{"emails_sent": 90}, day=date(2026, 10, 10), month_days=31,
		)
		self.assertEqual((rows[0]["actual"], rows[0]["percent"], rows[0]["on_pace"]), (90, 30, False))  # pace = 97
		self.assertIsNone(rows[1]["actual"])

	def test_plan_markdown_matches_the_daily_report_parser(self):
		text = rpt.plan_markdown({"month": "2026-10", "title": "October", "weeks": self.WEEKS,
								  "targets": [{"metric": "Emails", "target": "300"}], "todos": [{"title": "Zoho", "due_date": "2026-10-09"}]})
		self.assertIn("## Week by week", text)
		# The regex the 08:00 n8n report uses to find this week's section:
		js = re.compile(r"^### Week \d+ — \w+ (\d+)(?: \w+)? – \w+ (\d+)", re.M)
		self.assertEqual(js.findall(text), [("5", "11"), ("12", "18")])
		self.assertIn("### Week 2 — Mon 5 Oct – Sun 11 Oct (email 20/day)", text)
		self.assertIn("| Fri 9 Oct | Zoho | open |", text)


if __name__ == "__main__":
	unittest.main()
