"""
Roles and access — what each role in each app can do, and what the owner changed. Pure (no frappe):
tested without a bench (tests/test_role_access.py). qtt_platform.role_access stores and serves it.

Every app describes its roles with the `qtt_role_access` hook — a function returning a spec:

	{"product": "QTT_ORBITRA",
	 "areas": [{"key": "pos", "label": "POS — counter sales", "plan": "…when the plan includes it (optional)"}],
	 "roles": [{"key": "Cashier", "label": "Cashier", "about": "…", "assignable": True}],
	 "grants": {"Cashier": ["pos", "sales", …]},     # the defaults
	 "editable": ["Manager", "Cashier"],             # roles the owner may change ([] = fixed)
	 "fixed_areas": ["settings"],                     # areas the owner can't give or take away
	 "requires": {"inventory_edit": ["inventory"]}}   # an area that needs another one

The owner's changes are kept per business: {(product, role): [areas]}.
"""

from __future__ import annotations


class AccessError(ValueError):
	"""Message is shown to the owner."""


def effective(spec: dict, role: str, override: list[str] | None) -> list[str]:
	"""A role's areas in this business: the owner's choice for an editable role, else the default.
	Fixed areas always keep their default; order follows the spec."""
	default = set(spec["grants"].get(role, []))
	if override is None or role not in spec.get("editable", []):
		chosen = default
	else:
		fixed = set(spec.get("fixed_areas", []))
		chosen = (set(override) - fixed) | (default & fixed)
	return [a["key"] for a in spec["areas"] if a["key"] in chosen]


def matrix(spec: dict, overrides: dict[str, list[str]]) -> dict:
	"""The table an owner sees: every area × role, with what's on, what changed, what can't change."""
	rows = []
	for area in spec["areas"]:
		cells = []
		for r in spec["roles"]:
			key = r["key"]
			on = area["key"] in effective(spec, key, overrides.get(key))
			default = area["key"] in spec["grants"].get(key, [])
			can_change = key in spec.get("editable", []) and area["key"] not in spec.get("fixed_areas", [])
			cells.append({"role": key, "on": on, "default": default, "changed": on != default, "can_change": can_change})
		rows.append({**area, "cells": cells})
	return {"product": spec["product"], "roles": spec["roles"], "rows": rows,
			"editable": bool(spec.get("editable")), "changed": any(c["changed"] for r in rows for c in r["cells"])}


def change(spec: dict, current: list[str], role: str, area: str, allowed: bool) -> list[str]:
	"""A role's areas after the owner switches one area on or off (what to store)."""
	keys = [a["key"] for a in spec["areas"]]
	if role not in spec.get("editable", []):
		raise AccessError("This role's access is fixed.")
	if area not in keys:
		raise AccessError("Unknown area.")
	if area in spec.get("fixed_areas", []):
		raise AccessError("This can't be changed for any role.")
	areas = set(current)
	requires = spec.get("requires", {})
	if allowed:
		areas |= {area, *requires.get(area, [])}
	else:
		areas -= {area}
		areas -= {a for a, needs in requires.items() if area in needs}  # what needs it goes too
	if not areas:
		raise AccessError("A role needs at least one thing it can do.")
	return [k for k in keys if k in areas]


def describe(spec: dict, overrides: dict[str, list[str]], only_role: str | None = None) -> str:
	"""One line per role for the assistant: what it can do in this business (owner's changes included)."""
	labels = {a["key"]: a["label"] for a in spec["areas"]}
	lines = []
	for r in spec["roles"]:
		if only_role and r["key"] != only_role:
			continue
		areas = effective(spec, r["key"], overrides.get(r["key"]))
		changed = overrides.get(r["key"]) is not None and r["key"] in spec.get("editable", [])
		lines.append(f"{r['label']}{' (changed by the owner)' if changed else ''}: "
					 + (", ".join(labels[a] for a in areas) or "nothing"))
	return "; ".join(lines)
