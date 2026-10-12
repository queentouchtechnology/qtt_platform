"""
Intelligent search rules (pure — no frappe). Used by global search
(qtt_platform.api.search) and every list endpoint with a search box, and
mirrored in the app (qtt_app/lib/core/search/smart_query.dart):

- Every word must match somewhere (“bala chennai” finds Bala Stores in Chennai),
  in any order, ignoring case and extra spaces.
- Phone numbers match by digits (“98400 12345”, “+91-98400-12345” are the same).
- One typo is forgiven in words of 4+ letters (“kumr” finds Kumar).
- Results are ranked: exact name, then name starts with the query, then a word
  in the name starts with it, then anything else that matched.

How a list endpoint uses it (see `narrow` / `refine`): let SQL narrow on the
most selective word, then `refine` checks every word and ranks. If that finds
nothing, retry SQL with `fuzzy_term` and `refine(..., typos=True)`.
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


def sql_term(q: str | None) -> str:
	"""The word SQL should LIKE-match first: the longest (most selective)."""
	words = terms(q)
	return max(words, key=len) if words else ""


def fuzzy_term(q: str | None) -> str:
	"""A looser SQL pattern for a typo retry: the first 3 letters of sql_term."""
	t = sql_term(q)
	return t[:3] if len(t) >= 4 else ""


def fuzzy_fragments(q: str | None) -> list[str]:
	"""Pieces of the most selective word to LIKE-match on a typo retry — the
	typo can be anywhere, so its start, middle and end (and first letter as a
	name prefix, see smart_list)."""
	t = sql_term(q)
	if len(t) < 4:
		return []
	mid = len(t) // 2
	return list(dict.fromkeys([t[:3], t[mid - 1:mid + 2], t[-3:]]))


def _one_typo(a: str, b: str) -> bool:
	"""One wrong, missing, extra or swapped letter (jhon → john)."""
	if len(a) < 4 or abs(len(a) - len(b)) > 1:
		return False
	d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
	for i in range(len(a) + 1):
		d[i][0] = i
	for j in range(len(b) + 1):
		d[0][j] = j
	for i in range(1, len(a) + 1):
		for j in range(1, len(b) + 1):
			cost = a[i - 1] != b[j - 1]
			d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
			if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
				d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
	return d[-1][-1] <= 1


def matches(text_fields: list[str | None], q: str, typos: bool = False) -> bool:
	"""True when every word of q appears in one of the fields (phones by digits;
	with typos=True a word may also be one letter off a word in the fields)."""
	hay = " ".join(str(f).lower() for f in text_fields if f)
	hay_digits = re.sub(r"\D", "", hay)
	hay_words = [w for w in re.split(r"[^\w@.+]+", hay) if w]
	for w in terms(q):
		w_digits = re.sub(r"\D", "", w)
		if w in hay or (len(w_digits) >= 4 and w_digits in hay_digits):
			continue
		if typos and any(_one_typo(w, x) for x in hay_words):
			continue
		return False
	return True


def score(title: str, q: str) -> int:
	t, words = (title or "").lower().strip(), terms(q)
	s = " ".join(words)
	if not s:
		return 0
	if t == s:
		base = 100
	elif t.startswith(s):
		base = 80
	elif any(word.startswith(s) for word in t.split()):
		base = 60
	elif s in t:
		base = 40
	else:
		base = 20
	# Several words: names that start with one of them, or contain them as words, come first.
	title_words = t.split()
	bonus = sum((3 if t.startswith(w) else 0) + (2 if any(x.startswith(w) for x in title_words) else 0) for w in words) if len(words) > 1 else 0
	return base + bonus


def rank(results: list[dict], q: str, limit: int = 30) -> list[dict]:
	return sorted(results, key=lambda r: (-score(r.get("title", ""), q), r.get("title", "").lower()))[:limit]


def refine(rows: list, q: str, fields, title, typos: bool = False) -> list:
	"""Keep rows where every word matches (fields(row) -> list), best first (title(row) -> str)."""
	kept = [r for r in rows if matches(fields(r), q, typos=typos)]
	return sorted(kept, key=lambda r: (-score(title(r) or "", q), (title(r) or "").lower()))


def needs_refine(q: str | None) -> bool:
	"""More than one word: SQL alone (one LIKE) can't apply every word."""
	return len(terms(q)) > 1


def _title_words(titles: list[str]) -> list[str]:
	return [w for t in titles for w in re.split(r"[^\w]+", (t or "").lower()) if len(w) >= 2]


def completions(titles: list[str], q: str, limit: int = 4) -> list[str]:
	"""Smart suggestions: finish the word being typed from words in real
	results ("hrms dep" → "hrms deployment"), most common first."""
	words = terms(q)
	if not words:
		return []
	last, head = words[-1], words[:-1]
	counts: dict[str, int] = {}
	for title in titles:
		ws = _title_words([title])
		# Words from records that also have the earlier words count more.
		weight = 3 if head and all(any(x.startswith(h) for x in ws) for h in head) else 1
		for w in ws:
			if w.startswith(last) and w != last:
				counts[w] = counts.get(w, 0) + weight
	best = sorted(counts, key=lambda w: (-counts[w], len(w), w))[:limit]
	return [" ".join(head + [w]) for w in best]


def did_you_mean(titles: list[str], q: str) -> str | None:
	"""When a word only matched with a typo, the query spelled the way the
	records spell it ("rnjith" → "ranjith"); None if nothing to correct."""
	words = terms(q)
	vocab = set(_title_words(titles))
	if not words or not vocab:
		return None
	fixed, changed = [], False
	for w in words:
		if w in vocab or any(v.startswith(w) for v in vocab) or re.sub(r"\D", "", w):
			fixed.append(w)
			continue
		near = sorted((v for v in vocab if _one_typo(w, v)), key=lambda v: (abs(len(v) - len(w)), v))
		if near:
			fixed.append(near[0])
			changed = True
		else:
			fixed.append(w)
	return " ".join(fixed) if changed else None
