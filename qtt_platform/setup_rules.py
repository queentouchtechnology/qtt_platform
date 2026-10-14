"""
Set-up guides (qtt_platform.api.setup): what to do first, what next, what's optional — pure, tested
in tests/test_setup_rules.py. Each app lists its steps with the `qtt_setup_steps` hook:

	{"key": "pulse.team", "title": "Add your team", "why": "…", "stage": "first" | "next" | "optional",
	 "done": bool, "status": "12 people" | None, "screen": "pulse.people", "explain": "pulse.shifts_explained" | None}

Stages keep their order; inside a stage the app's order is the order to do them in.
"""

STAGES = ("first", "next", "optional")


def arrange(steps: list[dict]) -> dict:
	"""Steps grouped by stage, with the one to do now marked "next": the first not-done step of
	"first", else of "next". Progress counts only first + next (optional never nags)."""
	steps = [dict(s) for s in steps if s.get("stage") in STAGES]
	todo = [s for s in steps if s["stage"] != "optional"]
	now = next((s for stage in ("first", "next") for s in todo if s["stage"] == stage and not s.get("done")), None)
	for s in steps:
		s["now"] = s is now
	done = sum(1 for s in todo if s.get("done"))
	return {
		"stages": [{"stage": st, "steps": [s for s in steps if s["stage"] == st]} for st in STAGES if any(s["stage"] == st for s in steps)],
		"done": done, "total": len(todo), "complete": bool(todo) and done == len(todo),
		"next": {k: now[k] for k in ("key", "title", "why", "screen")} if now else None,
	}
