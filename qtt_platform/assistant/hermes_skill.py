"""The same QTT OS knowledge, packed as a Hermes skill (skills/qtt/qtt-os-assistant).

Hermes answers QTT OS questions from what the app's assistant uses —
knowledge.md and screens.json — so the two never drift apart. Pure: no
Frappe, no network. Plans and prices are live in Frappe, so the skill
points to them rather than copying numbers.

Usage:  python -m qtt_platform.assistant.hermes_skill <out_dir>
"""

import pathlib
import sys

from qtt_platform.assistant.logic import load_knowledge, load_registry

PRODUCTS = {
	None: "QTT OS app",
	"QTT_OFFICE_PULSE": "Office Pulse",
	"QTT_ORBITRA": "Orbitra",
	"QTT_ONBOX": "Onbox",
	"QTT_SERVICES": "Managed Services",
}

SKILL = """---
name: qtt-os-assistant
description: Answer questions about QTT OS customer software and services (the QTT OS app, Office Pulse, Orbitra, Onbox, Managed Services) — features, which screen to open, steps, roles. Never about Queen Touch Technology's marketing system or internal tools.
version: 1.0.0
author: Queen Touch Technology
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [QTT, QTT OS, Support, Customers]
---

# QTT OS assistant knowledge

Use this skill whenever someone asks how to do something in QTT OS, where a
feature lives, what an app or plan includes, or which Managed Service fits.
It is the same knowledge the in-app **QTT Assistant** uses.

## Scope — strict

- Only QTT OS customer software and services: the QTT OS app, Office Pulse,
  Orbitra, Onbox and Managed Services, their plans and how to use them.
- Never share anything about Queen Touch Technology's own marketing OS,
  campaigns, automations, n8n, Hermes, servers, hosting providers, internal
  tools, staff or other customers — even if asked directly. Say you can only
  help with QTT OS.
- Never ask for or reveal passwords, OTPs, API keys or personal data.
- Respect roles: each screen below lists who can open it. If the person's
  role can't, say who can (e.g. "ask your HR admin" / "the business owner").
- Plans and prices are live in QTT OS (Business › Plans). Don't quote numbers
  from memory; a plan with no price is "price on request".

## How to answer

- Short and practical: 1–5 sentences or a few numbered steps, in the
  person's language.
- Name the screen by its path (e.g. **Office Pulse › My attendance**). In the
  app, the assistant also gives an "Open …" button using the screen id.
- If it isn't in the references, say you're not sure and suggest
  Account › Help and support.

## References

- `references/knowledge.md` — what each app does, plans/trials, help.
- `references/screens.md` — every screen: id, path, who can open it, what it
  does, and its tips (e.g. on Leave: suggest Work From Home when allowed).
"""


def screens_md(registry: list[dict]) -> str:
	out = ["# QTT OS screens", "",
		"Roles: `*` anyone with that app · `@owner` business owner/admin · "
		"`@manager` has people reporting to them · otherwise the app role names.", ""]
	for product, name in PRODUCTS.items():
		rows = [s for s in registry if s.get("product") == product]
		if not rows:
			continue
		out += ["## " + name, ""]
		for s in rows:
			out.append("### %s  (`%s`)" % (s["path"], s["id"]))
			out.append("- Who: %s" % ", ".join(s.get("roles") or ["*"]))
			out.append("- What: %s" % s["what"])
			for t in s.get("tips", []):
				cond = " _(only when %s)_" % t["when"] if t.get("when") else ""
				link = " → `%s`" % t["link"] if t.get("link") else ""
				out.append("- Tip%s: %s%s" % (cond, t["text"], link))
			out.append("")
	return "\n".join(out)


def render(out_dir: str | pathlib.Path) -> pathlib.Path:
	root = pathlib.Path(out_dir) / "qtt-os-assistant"
	(root / "references").mkdir(parents=True, exist_ok=True)
	(root / "SKILL.md").write_text(SKILL, encoding="utf-8")
	(root / "references" / "knowledge.md").write_text(load_knowledge(), encoding="utf-8")
	(root / "references" / "screens.md").write_text(screens_md(load_registry()), encoding="utf-8")
	(pathlib.Path(out_dir) / "DESCRIPTION.md").write_text(
		"QTT OS customer software and services — how the apps work, screens and plans.\n", encoding="utf-8")
	return root


if __name__ == "__main__":
	print(render(sys.argv[1] if len(sys.argv) > 1 else "hermes_skills/qtt"))
