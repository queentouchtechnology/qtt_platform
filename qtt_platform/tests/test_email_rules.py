"""
QTT OS emails — every template file renders in the layout, people's text is escaped. No bench.

    python -m unittest qtt_platform.tests.test_email_rules -v
"""

import os
import unittest

import jinja2

from qtt_platform import email_rules as r

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = [os.path.join(HERE, "email_templates"),
		   os.path.join(HERE, "..", "..", "qtt-os", "qtt_services", "qtt_services", "email_templates"),
		   os.path.join(HERE, "..", "..", "qtt-os", "qtt_orbitra", "qtt_orbitra", "email_templates")]
LAYOUT = open(os.path.join(HERE, "templates", "emails", "qtt_layout.html"), encoding="utf-8").read()

# Enough for every template: names, links, lists, flags.
CONTEXT = {
	"code": "482913", "code_spaced": "4 8 2 9 1 3", "brand": "Acme", "minutes": 10, "inviter": "Ann", "business": "Acme & Sons",
	"link": "https://app.example.com/j/X", "expires": "6 Nov 2026", "head": "Ann invited you", "kind": "invite", "title": "Weekly <b>call</b>",
	"when": "Mon 2 Nov, 10:00", "location": "Office", "meeting_url": "https://meet.example.com/x", "organizer": "Ann", "subject_line": "Approve",
	"label": "Article", "site": "acme.in", "goes": True, "action": "Publish", "approve_url": "https://a", "reject_url": "https://r",
	"preview_url": "https://p", "body": "Hello", "approved": True, "file_title": "Plan.pdf", "delete_on": "9 Nov 2026", "closes": ["Acme"],
	"blocked": ["Acme"], "first_name": "Ann", "user": "ann@example.com", "site_url": "https://app.example.com", "login_url": "https://app.example.com",
	"owner": "Ann <ann@example.com>", "service": "Website Development", "answers": [{"label": "Business name", "value": "Acme"}],
	"checklist": ["Plan the work"], "first_name": "Ann", "modules": "procurement", "join_url": "https://app.example.com/join?code=X", "signer": "Gayathri",
	"signer_role": "Business Operations", "admin_url": "https://app.example.com/app", "level": "critical", "recovery": False, "asset": "acme.in",
	"asset_url": "https://acme.in", "details": "Down for 5 minutes", "for_team": True, "workspace": "Acme", "tenant": "t1", "at": "30 Oct 2026, 18:00",
}


def files():
	for folder in FOLDERS:
		if os.path.isdir(folder):
			for f in sorted(os.listdir(folder)):
				if f.endswith(".html"):
					yield f, open(os.path.join(folder, f), encoding="utf-8").read()


def render(text: str, ctx: dict) -> tuple[str, str]:
	t = r.parse_file(text)
	env = jinja2.Environment(loader=jinja2.DictLoader({"templates/emails/qtt_layout.html": LAYOUT}))
	subject = env.from_string(t["subject"]).render(ctx)
	return subject, env.from_string(t["body"]).render({**r.escape(ctx), "subject": r.escape(subject)})


class Templates(unittest.TestCase):
	def test_every_file_renders_in_the_layout(self):
		seen = 0
		for name, text in files():
			with self.subTest(name):
				subject, html = render(text, CONTEXT)
				self.assertTrue(subject.strip())
				self.assertIn("qtt-os-logo.png", html) if "frappe_header = 1" not in text else self.assertNotIn("qtt-os-logo.png", html)
				self.assertIn("queentouchtech.in", html)
				self.assertNotIn("n8n", html.lower())
				self.assertNotIn("{{", html)
				seen += 1
		self.assertGreaterEqual(seen, 10)

	def test_names_are_unique(self):
		names = [r.parse_file(t)["name"] for _, t in files()]
		self.assertEqual(len(names), len(set(names)))

	def test_peoples_text_is_escaped(self):
		_, html = render(dict(files())["calendar-invitation.html"], CONTEXT)
		self.assertIn("Weekly &lt;b&gt;call&lt;/b&gt;", html)
		self.assertNotIn("Weekly <b>call", html)


class Rules(unittest.TestCase):
	def test_parse_file(self):
		t = r.parse_file("<!-- name: QTT · X -->\n<!-- subject: Hi {{ a }} -->\nbody\n")
		self.assertEqual((t["name"], t["subject"], t["body"]), ("QTT · X", "Hi {{ a }}", "body\n"))
		with self.assertRaises(ValueError):
			r.parse_file("<p>no header</p>")

	def test_escape_keeps_own_html(self):
		out = r.escape({"a": "<i>", "b": ["x&y"], "c": 3, "own": "<b>ok</b>"}, {"own"})
		self.assertEqual(out, {"a": "&lt;i&gt;", "b": ["x&amp;y"], "c": 3, "own": "<b>ok</b>"})


if __name__ == "__main__":
	unittest.main()
