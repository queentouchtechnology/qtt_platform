"""
Intelligent search rules (pure — no frappe; qtt_platform.api.search runs it).

- Every word must match somewhere (“bala chennai” finds Bala Stores in Chennai),
  in any order, ignoring case and extra spaces.
- Phone numbers match by digits (“98400 12345”, “+91-98400-12345” are the same).
- Results are ranked: exact name, then name starts with the query, then a word
  in the name starts with it, then anything else that matched.
"""

import re

MIN_QUERY = 2
PER_SOURCE = 8


def terms(q: str | None) -> list[str]:
	words = [w for w in re.split(r"\s+", (q or "").strip().lower()) if w]
	return words[:6]


def digits(q: str | None) -> str:
	d = re.sub(r"\D", "", q or "")
	return d if len(d) >= 4 else ""


def matches(text_fields: list[str | None], q: str) -> bool:
	"""True when every word of q appears in one of the fields (phones by digits)."""
	hay = " ".join(f.lower() for f in text_fields if f)
	hay_digits = re.sub(r"\D", "", hay)
	for w in terms(q):
		w_digits = re.sub(r"\D", "", w)
		if w in hay or (len(w_digits) >= 4 and w_digits in hay_digits):
			continue
		return False
	return True


def score(title: str, q: str) -> int:
	t, s = (title or "").lower().strip(), " ".join(terms(q))
	if not s:
		return 0
	if t == s:
		return 100
	if t.startswith(s):
		return 80
	if any(word.startswith(s) for word in t.split()):
		return 60
	if s in t:
		return 40
	return 20


def rank(results: list[dict], q: str, limit: int = 30) -> list[dict]:
	return sorted(results, key=lambda r: (-score(r.get("title", ""), q), r.get("title", "").lower()))[:limit]
