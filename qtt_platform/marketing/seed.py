"""
Starting data for the marketing dashboard: QTT's October 2026 plan and
daily schedule, moved from marketing-ai-os/00_COMMAND_CENTER/
OCTOBER_2026_SCHEDULE.md into Frappe (founder decision 2026-10-10).

Insert-only: runs on migrate, creates the plan / slots only when none
exist yet, and never touches them afterwards — from then on they're edited
in QTT OS → QTT Admin → Marketing (or Desk).
"""

import frappe

WEEKDAYS = "mon,tue,wed,thu,fri"
MON_SAT = "mon,tue,wed,thu,fri,sat"
MON_THU = "mon,tue,wed,thu"

# n8n workflows already known (marketing-ai-os N8N_CURRENT_STATE.md)
WF_DAILY_REPORT = "bWzqOrEnKjl6wbar"
WF_SOCIAL = "2lYthYvH82MzPXQK"
WF_LEAD_RESEARCH = "m6ZIWQsJykwUA4yT"

SLOTS = [
	# title, kind, owner, start, end, days, extra
	("Daily report (WhatsApp + Slack + email)", "report", "auto", "08:00", None, "mon,tue,wed,thu,fri,sat,sun", {"n8n_workflow_id": WF_DAILY_REPORT}),
	("Social Autopilot plans today's posts", "social", "auto", "08:00", None, "mon,tue,wed,thu,fri,sat,sun", {"n8n_workflow_id": WF_SOCIAL}),
	("Remote-QA job digest → apply 5–8", "task", "Gayathri", "08:30", None, MON_SAT, {}),
	("Call plan in Slack", "calls", "auto", "09:30", None, MON_SAT, {}),
	("Calls: Tamil Nadu (warm leads)", "calls", "founder", "10:00", "11:30", WEEKDAYS, {}),
	("Calls: India only (Saturday)", "calls", "founder", "10:00", "13:00", "sat", {}),
	("Email batch 1 (Gulf · Singapore · India) — tap Send in Slack", "email", "founder", "10:30", None, WEEKDAYS, {}),
	("Lead research (3 searches: 11:00 · 13:00 · 16:00)", "research", "auto", "11:00", None, WEEKDAYS, {"n8n_workflow_id": WF_LEAD_RESEARCH}),
	("Calls: UAE / Oman (+ Saudi/Qatar Mon–Thu)", "calls", "founder", "11:30", "12:30", WEEKDAYS, {}),
	("Calls: Kerala / Karnataka / AP / Telangana", "calls", "founder", "12:30", "13:00", WEEKDAYS, {}),
	("Lunch · WhatsApp follow-ups · update CRM call statuses", "task", "founder", "13:00", "14:30", WEEKDAYS, {}),
	("Visit Thoothukudi businesses", "visit", "founder", "14:00", "17:00", "sat", {}),
	("Calls: UK (check Corporate TPS)", "calls", "founder", "14:30", "15:30", WEEKDAYS, {"valid_to": "2026-10-25"}),
	("Calls: UK (check Corporate TPS)", "calls", "founder", "15:30", "16:30", WEEKDAYS, {"valid_from": "2026-10-26", "notes": "UK clocks went back"}),
	("Calls: North & West India", "calls", "founder", "15:30", "17:00", WEEKDAYS, {"valid_to": "2026-10-25"}),
	("Calls: North & West India", "calls", "founder", "14:30", "15:30", WEEKDAYS, {"valid_from": "2026-10-26"}),
	("Calls: Tamil Nadu round 2 (missed + callbacks)", "calls", "founder", "17:00", "18:00", WEEKDAYS, {}),
	("Email batch 2 (UK · USA) — tap Send in Slack", "email", "founder", "17:30", None, WEEKDAYS, {}),
	("Calls: UAE round 2", "calls", "founder", "18:00", "18:30", MON_THU, {}),
	("Shorts go live (YouTube, Instagram, Facebook)", "social", "auto", "19:00", None, "mon,wed,fri", {}),
	("Calls: USA East (law firms, dentists, real estate)", "calls", "founder", "19:30", "20:30", WEEKDAYS, {"valid_to": "2026-11-01"}),
	("Calls: USA West (optional)", "calls", "founder", "22:30", "23:00", WEEKDAYS, {}),
	("Review the week, plan next week (no calls)", "task", "founder", "10:00", None, "sun", {}),
]

PLAN = {
	"month": "2026-10",
	"title": "October 2026 — QTT outreach & growth",
	"summary": "Email ramp from one Zoho mailbox (10 → 20 → 30 a day), ≈25 calls a day across regions, daily social autopilot + Shorts, "
			   "remote-QA work for Gayathri. Every email batch still needs the Slack Send tap.",
	"targets": [
		("Emails sent", "300–400", 300, "emails_sent", "≈560 max capacity"),
		("Email replies", "5% (≈15–20)", 15, "email_replies", None),
		("Calls made", "300+", 300, "calls", "≈25 / day"),
		("New leads", "", 0, "leads", None),
		("Meetings / demos", "8–10", 8, None, None),
		("Quotations sent", "5", 5, None, None),
		("First QA client (via QTT)", "1", 1, None, None),
		("Gayathri applications", "100+ (≈5/day)", 100, "applications", "crowd-testing accounts active"),
		("Social", "daily autopilot + 9 Shorts (02–10)", 0, None, None),
	],
	"weeks": [
		("Week 1 (start)", "2026-10-03", "2026-10-04",
		 "Sat 3: India calls + 2–3 local business visits\n"
		 "Gayathri: sign up on uTest, Testlio, Global App Testing, Turing, Uplers, Arc.dev; add the childcare career break to CV + LinkedIn\n"
		 "Sun 4: review first week (emails, replies, calls)"),
		("Week 2 (email 20/day)", "2026-10-05", "2026-10-11",
		 "Mon 5: Short 02 (clinic) · day-5 follow-ups start for the 1 Oct emails\n"
		 "Wed 7: Short 03 (restaurant) · Fri 9: Short 04 (website)\n"
		 "Gayathri: 5–8 applications/day from the digest + LinkedIn/Naukri; 3 freelance QA proposals\n"
		 "By Fri 9: subscribe Zoho Mail Lite (trial ends mid-October — outreach stops without it)\n"
		 "Rotate exposed keys (Exotel, Google, Brevo, webhook secret)"),
		("Week 3 (email 30/day)", "2026-10-12", "2026-10-18",
		 "Mon 12: Short 05 (Google Maps) · decide on Shorts 11–20 (build ~13–14 Oct so they queue from 26 Oct)\n"
		 "Wed 14: Short 06 (QTT ERP) · Fri 16: Short 07 (e-commerce)\n"
		 "Mid-month review (Sun 18): reply rate per region and niche; move call time to the best-performing region"),
		("Week 4 (festival week in Tamil Nadu)", "2026-10-19", "2026-10-25",
		 "Mon 19 Ayudha Puja · Tue 20 Vijayadashami: skip India calls; Gulf/UK/US continue\n"
		 "Mon 19: Short 08 (school app) · Wed 21: Short 09 (social media) · Fri 23: Short 10 (bakery case study — confirm Ganesh Bakery is OK being named)\n"
		 "Prepare Deepavali (Sun 8 Nov) content — real offer only, nothing invented\n"
		 "Sun 25: UK clocks go back → from Mon 26 UK calls 15:30–16:30, North India 14:30–15:30"),
		("Week 5", "2026-10-26", "2026-10-31",
		 "Shorts 11–20 start (if approved) Mon / Wed / Fri\n"
		 "Day-11 final follow-ups for early October emails\n"
		 "Sun 1 Nov: US clocks go back → USA East 20:30–21:30 from Mon 2 Nov\n"
		 "Sat 31: monthly review — emails, replies, calls, meetings, quotations, QA work; set November targets"),
	],
	"todos": [
		("2026-10-03", "Gayathri platform sign-ups; CV/LinkedIn career-break line", "founder"),
		("2026-10-09", "Subscribe Zoho Mail Lite · rotate exposed keys", "founder"),
		("2026-10-12", "Decide Shorts 11–20 topics (Claude builds)", "founder"),
		("2026-10-16", "QA plan decisions (free launch check, gayathri@ mailbox, Upwork agency)", "founder"),
		("2026-10-23", "Ganesh Bakery OK for Short 10 · Deepavali offer (if any)", "founder"),
		(None, "Exotel KYC result (backup line)", "founder"),
	],
	"day_notes": [
		("2026-10-19", "Ayudha Puja (Tamil Nadu) — no India calls"),
		("2026-10-20", "Vijayadashami (Tamil Nadu) — no India calls"),
		("2026-10-25", "UK clocks go back — UK calls move to 15:30 IST from Monday"),
		("2026-11-01", "US clocks go back — USA calls move to 20:30 IST from Monday"),
	],
}


def seed_marketing_defaults() -> None:
	"""after_migrate: create the October 2026 plan and the daily schedule
	only if there's nothing yet."""
	if not frappe.db.table_exists("QTT Marketing Plan") or not frappe.db.table_exists("QTT Marketing Schedule Slot"):
		return
	if not frappe.db.exists("QTT Marketing Plan", PLAN["month"]):
		doc = frappe.new_doc("QTT Marketing Plan")
		doc.update({"month": PLAN["month"], "title": PLAN["title"], "status": "active", "summary": PLAN["summary"]})
		for metric, target, number, key, notes in PLAN["targets"]:
			doc.append("targets", {"metric": metric, "target": target or "—", "target_number": number or None, "metric_key": key, "notes": notes})
		for label, start, end, details in PLAN["weeks"]:
			doc.append("weeks", {"label": label, "start_date": start, "end_date": end, "details": details})
		for due, title, owner in PLAN["todos"]:
			doc.append("todos", {"due_date": due, "title": title, "owner_name": owner, "status": "open"})
		for day, note in PLAN["day_notes"]:
			doc.append("day_notes", {"date": day, "note": note})
		doc.insert(ignore_permissions=True)
	if not frappe.db.count("QTT Marketing Schedule Slot"):
		for i, (title, kind, owner, start, end, days, extra) in enumerate(SLOTS):
			frappe.get_doc({
				"doctype": "QTT Marketing Schedule Slot",
				"title": title, "kind": kind, "owner_name": owner, "start_time": start, "end_time": end,
				"days": days, "sort_order": i, "enabled": 1, **extra,
			}).insert(ignore_permissions=True)
