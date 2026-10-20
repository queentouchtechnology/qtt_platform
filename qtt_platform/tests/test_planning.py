"""
Office Pulse planning (PROJ-0016 D) — boards, notes, whiteboards, forms and My work. No bench.

    python -m unittest qtt_platform.tests.test_planning -v
"""

import unittest
from datetime import date, datetime, timedelta

from qtt_platform import planning_rules as p


class Boards(unittest.TestCase):
	def test_templates(self):
		b = p.from_template("sales")
		self.assertEqual([x["title"] for x in b["lists"]], ["New lead", "Contacted", "Quote sent", "Won", "Lost"])
		self.assertEqual(next(x["title"] for x in b["lists"] if x["id"] == b["done_list"]), "Won")
		self.assertTrue(all(l["color"].startswith("#") for l in b["labels"]))
		self.assertEqual(p.from_template("nope")["title"], "To do")
		for key in p.TEMPLATES:
			p.from_template(key)  # every template's done list is one of its lists

	def test_lists_checked(self):
		ls = p.clean_lists([{"id": "a", "title": " To do "}, {"id": "a", "title": "Done"}, {"title": "New"}])
		self.assertEqual([x["title"] for x in ls], ["To do", "Done", "New"])
		self.assertEqual(len({x["id"] for x in ls}), 3)
		with self.assertRaises(ValueError):
			p.clean_lists([])
		with self.assertRaises(ValueError):
			p.clean_lists([{"title": ""}])
		with self.assertRaises(ValueError):
			p.clean_lists([{"title": str(i)} for i in range(21)])

	def test_labels(self):
		ls = p.clean_labels([{"name": "Hot", "color": "red"}, {"name": ""}, {"name": "Big", "color": "#123456"}])
		self.assertEqual([x["name"] for x in ls], ["Hot", "Big"])
		self.assertTrue(ls[0]["color"].startswith("#"))
		self.assertEqual(ls[1]["color"], "#123456")

	def test_positions(self):
		self.assertEqual(p.between(None, None), 1024.0)
		self.assertEqual(p.between(None, 1024.0), 512.0)
		self.assertEqual(p.between(1024.0, None), 2048.0)
		self.assertEqual(p.between(1024.0, 2048.0), 1536.0)
		self.assertFalse(p.needs_renumber([1.0, 2.0, 3.0]))
		self.assertTrue(p.needs_renumber([1.0, 1.0000000001]))
		self.assertEqual(p.renumber(3), [1024.0, 2048.0, 3072.0])

	def test_who_sees(self):
		team = {"visibility": "team", "created_by_user": "a"}
		mem = {"visibility": "members", "created_by_user": "a"}
		self.assertTrue(p.board_visible(team, "z", False, []))
		self.assertTrue(p.board_visible(mem, "a", False, []))
		self.assertTrue(p.board_visible(mem, "b", False, ["b"]))
		self.assertFalse(p.board_visible(mem, "z", False, ["b"]))
		self.assertTrue(p.board_visible(mem, "z", True, []))  # owners / admins
		self.assertTrue(p.board_may_manage(mem, "a", False))
		self.assertFalse(p.board_may_manage(team, "b", False))

	def test_checklist(self):
		c = p.clean_checklist([{"text": "Call", "done": 1}, {"text": " "}, {"text": "Quote"}])
		self.assertEqual(p.progress(c), (1, 2))


class Notes(unittest.TestCase):
	BODY = "# Plan\n- [ ] Call Ravi\n- [x] Book hall\n* [ ] Order cake\nSome text"

	def test_checks(self):
		self.assertEqual(p.note_checks(self.BODY), (1, 3))
		self.assertEqual(p.action_items(self.BODY), ["Call Ravi", "Order cake"])

	def test_toggle(self):
		b = p.toggle_check(self.BODY, 0)
		self.assertIn("- [x] Call Ravi", b)
		b = p.toggle_check(b, 1)
		self.assertIn("- [ ] Book hall", b)
		self.assertTrue(b.endswith("Some text"))
		with self.assertRaises(ValueError):
			p.toggle_check(self.BODY, 9)

	def test_meeting_notes(self):
		title, body = p.meeting_notes("Weekly review", "Mon 21 Oct, 10:00", "Office", ["Ann", "Ravi"])
		self.assertEqual(title, "Meeting notes: Weekly review")
		self.assertIn("**People:** Ann, Ravi", body)
		self.assertIn("## Action items\n- [ ]", body)
		self.assertEqual(p.action_items(body), [])  # the empty checkbox isn't an action yet

	def test_snippet(self):
		long = "Intro. " * 40 + "The GST number is here. " + "More. " * 40
		s = p.snippet(long, ["gst"])
		self.assertIn("GST number", s)
		self.assertTrue(s.startswith("…") and s.endswith("…"))
		self.assertEqual(p.snippet("# Title\n**bold**", ["x"]), "Title bold")


class Whiteboard(unittest.TestCase):
	def test_merge(self):
		saved = [{"id": "a", "version": 2, "versionNonce": 5}, {"id": "b", "version": 1}]
		incoming = [{"id": "a", "version": 1, "versionNonce": 9}, {"id": "b", "version": 3, "isDeleted": True}, {"id": "c", "version": 1}, {"x": 1}]
		out = p.merge_elements(saved, incoming)
		self.assertEqual([e["id"] for e in out], ["a", "b", "c"])
		self.assertEqual(out[0]["version"], 2)  # the older one from someone else doesn't win
		self.assertTrue(out[1]["isDeleted"])
		# the same version from two people: the bigger nonce, so everyone ends the same
		self.assertEqual(p.merge_elements([{"id": "a", "version": 2, "versionNonce": 1}], [{"id": "a", "version": 2, "versionNonce": 7}])[0]["versionNonce"], 7)

	def test_changed_since(self):
		els = [{"id": "a", "version": 2}, {"id": "b", "version": 1}]
		self.assertEqual([e["id"] for e in p.changed_since(els, {"a": 2})], ["b"])


class Forms(unittest.TestCase):
	QS = [
		{"id": "nm", "type": "short", "label": "Your name", "required": True},
		{"id": "em", "type": "email", "label": "Email"},
		{"id": "ph", "type": "phone", "label": "Phone"},
		{"id": "sz", "type": "choice", "label": "Size", "options": ["S", "M", "L"]},
		{"id": "tp", "type": "checkboxes", "label": "Toppings", "options": ["Nuts", "Fruit", "Choco"]},
		{"id": "rt", "type": "rating", "label": "How was it?"},
		{"id": "qty", "type": "number", "label": "How many?"},
		{"id": "dt", "type": "date", "label": "When?"},
		{"id": "yn", "type": "yesno", "label": "Again?"},
	]

	def setUp(self):
		self.qs = p.clean_questions(self.QS)

	def test_questions_checked(self):
		self.assertEqual(len(self.qs), 9)
		with self.assertRaises(ValueError):
			p.clean_questions([{"type": "choice", "label": "Pick", "options": ["only one"]}])
		with self.assertRaises(ValueError):
			p.clean_questions([{"type": "magic", "label": "x"}])
		with self.assertRaises(ValueError):
			p.clean_questions([{"type": "short", "label": " "}])
		with self.assertRaises(ValueError):
			p.clean_questions([])
		self.assertEqual(p.clean_questions([{"type": "dropdown", "label": "x", "options": ["a", "a", "b"]}])[0]["options"], ["a", "b"])

	def test_answers(self):
		clean, errors = p.check_answers(self.qs, {"nm": " Ann ", "em": "Ann@X.com", "ph": "98400 12345", "sz": "M", "tp": ["Choco", "Nuts"],
												 "rt": "4", "qty": "2", "dt": "2026-10-25", "yn": "Yes", "junk": "x"})
		self.assertEqual(errors, {})
		self.assertEqual(clean["nm"], "Ann")
		self.assertEqual(clean["em"], "ann@x.com")
		self.assertEqual(clean["ph"], "9840012345")
		self.assertEqual(clean["tp"], ["Nuts", "Choco"])  # in the form's order
		self.assertEqual((clean["rt"], clean["qty"], clean["yn"]), (4, 2, "yes"))
		self.assertNotIn("junk", clean)

	def test_answer_errors(self):
		_, errors = p.check_answers(self.qs, {"em": "nope", "ph": "12", "sz": "XL", "tp": ["Gold"], "rt": 9, "qty": "lots", "dt": "soon", "yn": "maybe"})
		self.assertEqual(set(errors), {"nm", "em", "ph", "sz", "tp", "rt", "qty", "dt", "yn"})
		self.assertEqual(errors["nm"], "Please answer this.")
		self.assertEqual(errors["qty"], "That answer doesn't fit this question.")

	def test_summary(self):
		rs = [{"sz": "M", "tp": ["Nuts"], "rt": 4, "qty": 2, "yn": "yes", "nm": "A"}, {"sz": "M", "tp": ["Nuts", "Choco"], "rt": 2, "qty": 6, "yn": "no", "nm": "B"}]
		s = {x["id"]: x for x in p.summary(self.qs, rs)}
		self.assertEqual(s["sz"]["counts"], [{"option": "S", "count": 0}, {"option": "M", "count": 2}, {"option": "L", "count": 0}])
		self.assertEqual(s["tp"]["counts"][0], {"option": "Nuts", "count": 2})
		self.assertEqual(s["rt"]["average"], 3.0)
		self.assertEqual((s["qty"]["min"], s["qty"]["max"], s["qty"]["average"]), (2, 6, 4.0))
		self.assertEqual(s["yn"]["counts"], [{"option": "Yes", "count": 1}, {"option": "No", "count": 1}])
		self.assertEqual(s["nm"]["latest"], ["B", "A"])
		self.assertEqual(s["em"]["answered"], 0)

	def test_csv(self):
		out = p.to_csv(self.qs, [{"_at": "2026-10-20 10:00", "nm": "=HYPERLINK(1)", "tp": ["Nuts", "Fruit"], "qty": -2}])
		lines = out.splitlines()
		self.assertTrue(lines[0].startswith("Submitted,Name,Email,Your name,Email,Phone"))
		self.assertIn("'=HYPERLINK(1)", lines[1])
		self.assertIn("Nuts; Fruit", lines[1])
		self.assertIn(",-2,", lines[1])  # a negative number stays a number

	def test_contact(self):
		self.assertEqual(p.contact_from(self.qs, {"nm": "Ann", "em": "a@x.com"}), {"name": "Ann", "email": "a@x.com", "phone": ""})
		self.assertEqual(p.contact_from(self.qs, {"ph": "98400"})["name"], "98400")
		self.assertIsNone(p.contact_from(self.qs, {"nm": "Ann"}))

	def test_open(self):
		now = datetime(2026, 10, 20, 12)
		self.assertIsNone(p.form_open({"accepting": 1}, 0, now))
		self.assertEqual(p.form_open({"accepting": 0}, 0, now), "closed")
		self.assertEqual(p.form_open({"accepting": 1, "closes_at": now}, 0, now), "ended")
		self.assertEqual(p.form_open({"accepting": 1, "max_responses": 3}, 3, now), "full")


class MyWork(unittest.TestCase):
	def test_buckets(self):
		mon = date(2026, 10, 19)  # a Monday
		self.assertEqual(p.bucket(None, mon), "someday")
		self.assertEqual(p.bucket(mon - timedelta(days=1), mon), "overdue")
		self.assertEqual(p.bucket(mon, mon), "today")
		self.assertEqual(p.bucket(mon + timedelta(days=1), mon), "tomorrow")
		self.assertEqual(p.bucket(mon + timedelta(days=6), mon), "week")  # Sunday
		self.assertEqual(p.bucket(mon + timedelta(days=7), mon), "later")
		sat = date(2026, 10, 24)
		self.assertEqual(p.bucket(sat + timedelta(days=2), sat), "later")


if __name__ == "__main__":
	unittest.main()
