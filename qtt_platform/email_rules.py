"""
QTT OS emails — the rules, pure (no Frappe; tests/test_email_rules.py). The sending is emails.py.

  parse_file    an email_templates/*.html file → {name, subject, body}
  escape        a context made safe for a template: every text escaped, except the keys in `html`
"""

import re
from html import escape as _esc

_HEAD = re.compile(r"^\s*<!--\s*(name|subject)\s*:\s*(.*?)\s*-->\s*$")


def parse_file(text: str) -> dict:
	"""First lines `<!-- name: … -->` and `<!-- subject: … -->`, then the body (Jinja, extends the layout)."""
	out, lines = {}, (text or "").splitlines()
	while lines:
		m = _HEAD.match(lines[0])
		if not m:
			break
		out[m.group(1)] = m.group(2)
		lines.pop(0)
	if not out.get("name") or not out.get("subject"):
		raise ValueError("An email template file starts with <!-- name: … --> and <!-- subject: … -->")
	return {"name": out["name"], "subject": out["subject"], "body": "\n".join(lines).strip() + "\n"}


def escape(value, html: tuple | set = ()):
	"""Text from people (names, titles, answers) can't add HTML to an email. Keys in `html` are QTT's own HTML."""
	if isinstance(value, str):
		return _esc(value, quote=True)
	if isinstance(value, dict):
		return {k: (v if k in html else escape(v)) for k, v in value.items()}
	if isinstance(value, (list, tuple)):
		return [escape(v) for v in value]
	return value
