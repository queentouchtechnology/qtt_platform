"""
Sorting for list APIs (pure — no frappe; tested without a bench).

Every list that lets people sort names its choices once, e.g.

    SORTS = {"name": "customer_name asc", "newest": "creation desc"}
    order = list_sort.order_by(sort, SORTS, "name")

Only those exact strings ever reach the query — whatever the app sends, an unknown choice falls back
to the default, so a sort can't be used to inject SQL. The app shows the same keys as "Sort by".
"""

PAGE = 20  # rows per page when the app loads more as you scroll


def order_by(sort: str | None, choices: dict[str, str], default: str) -> str:
	return choices.get((sort or "").strip()) or choices[default]


def page(start, page_length, *, cap: int = 100) -> tuple[int, int]:
	"""(start, page_length) from what the app sent: never negative, at most `cap` a page."""
	try:
		start = max(int(start or 0), 0)
	except (TypeError, ValueError):
		start = 0
	try:
		length = int(page_length or PAGE)
	except (TypeError, ValueError):
		length = PAGE
	return start, min(max(length, 1), cap)
