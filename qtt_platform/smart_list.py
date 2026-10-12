"""
Intelligent search for list endpoints (customers, people, items, workspaces…)
— the server half of every search box in the app. Rules: qtt_platform.search_logic.

	rows, has_more = smart_get_all("QTT Customer", filters=..., fields=...,
									search_fields=["customer_name", "email", ...],
									title_field="customer_name", q=q, ...)

No query: a normal page in the endpoint's order. With a query: SQL narrows on
the most selective word, every word is then checked (any order, phone digits),
results are ranked best-first; if nothing matches, it retries allowing one
typo. Permission filters stay the caller's — this only adds matching.
"""

import frappe

from qtt_platform import search_logic as logic

#: How many candidate rows SQL may return per requested row, before refining.
WINDOW = 5


def smart_get_all(doctype: str, *, filters, fields: list[str], search_fields: list[str], title_field: str, q: str | None,
				  order_by: str = "modified desc", start: int = 0, page_length: int = 50,
				  digits_field: str | None = None) -> tuple[list, bool]:
	start, page_length = max(int(start or 0), 0), max(int(page_length or 50), 1)
	q = (q or "").strip()
	if not q:
		rows = frappe.get_all(doctype, filters=filters, fields=fields, order_by=order_by, start=start, page_length=page_length)
		return rows, len(rows) == page_length

	want = sorted(set(fields) | set(search_fields) | {"name"} | ({digits_field} if digits_field else set()))
	window = (start + page_length) * WINDOW
	d = logic.digits(q)

	def fetch(term: str, limit: int, extra: list | None = None) -> list:
		or_filters = [[doctype, f, "like", f"%{term}%"] for f in search_fields] + (extra or [])
		if digits_field and d:
			or_filters.append([doctype, digits_field, "like", f"%{d}%"])
		return frappe.get_all(doctype, filters=filters, or_filters=or_filters, fields=want, order_by=order_by, limit=limit)

	def values(r) -> list:
		return [r.get(f) for f in search_fields] + ([r.get(digits_field)] if digits_field else [])

	ranked = logic.refine(fetch(logic.sql_term(q), window), q, values, lambda r: r.get(title_field))
	if not ranked and logic.fuzzy_fragments(q):
		# Typo retry: candidates sharing any piece of the word, or starting with
		# its first letter; then every word is checked allowing one mistake.
		seen, candidates = set(), []
		first = [[doctype, title_field, "like", f"{logic.sql_term(q)[0]}%"]]
		for i, frag in enumerate(logic.fuzzy_fragments(q)):
			for r in fetch(frag, window * 2, first if i == 0 else None):
				if r.name not in seen:
					seen.add(r.name)
					candidates.append(r)
		ranked = logic.refine(candidates, q, values, lambda r: r.get(title_field), typos=True)
	page = ranked[start:start + page_length]
	return page, len(ranked) > start + page_length
