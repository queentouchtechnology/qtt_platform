"""
Will the words fit? (PROJ-0012 S2, premium upgrade) — before a design is drawn, each word slot is compared with how much
that layout holds: the characters measured on real renders in the square size, the tightest one (fit_budgets.json, made
by the Studio audit's measure step). Text that is longer is reported to the owner as a plain warning — what to shorten,
by how much — instead of being shrunk out of sight or cut. Pure (no Frappe); tests/test_design.py.
"""

import json
from functools import lru_cache
from pathlib import Path

LABELS = {"headline": "headline", "subline": "line under the headline", "kicker": "small line above the headline", "tagline": "tagline",
		  "quote": "quote", "cta": "button words", "business": "business name", "phone": "phone line", "website": "website",
		  "address": "address", "price": "price", "person": "name", "role": "role", "badge": "badge", "place": "place", "time": "time",
		  "price_label": "price label", "list_title": "list title", "item_title": "longest point", "list_item": "longest list line"}
ROOM = {"square": 1.0, "portrait": 1.15, "story": 1.4, "wide": .9, "landscape": .95}  # taller sizes hold a little more
SLACK = 1.1  # a few letters over is fine: the text still shrinks a step


@lru_cache(maxsize=1)
def budgets() -> dict:
	p = Path(__file__).with_name("fit_budgets.json")
	try:
		return json.loads(p.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return {}


def _plain(v) -> str:
	return str(v or "").replace("*", "").strip()


def check(layout: str, content: dict, fmt: str = "square") -> list[dict]:
	"""[{slot, label, length, max, message}] for each word slot longer than this layout holds at this size."""
	b = budgets().get(layout) or {}
	room = ROOM.get(fmt, 1.0)
	out = []
	for slot, limit in b.items():
		if not limit:
			continue
		c = content or {}
		if slot == "item_title":
			text = max((_plain(it.get("title")) for it in c.get("items") or [] if isinstance(it, dict)), key=len, default="")
		elif slot == "list_item":
			text = max((_plain(t) for t in c.get("list") or []), key=len, default="")
		else:
			text = _plain(c.get(slot))
		if not text:
			continue
		cap = int(limit * room)
		if len(text) > cap * SLACK:
			over = len(text) - cap
			label = LABELS.get(slot, slot)
			out.append({"slot": slot, "label": label, "length": len(text), "max": cap,
						"message": f"The {label} is {over} letters longer than this design holds — shorten it, or pick a roomier design."})
	return out
