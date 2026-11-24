"""
queentouchtech.in's search titles and descriptions, from Desk › QTT SEO Plan (the keyword plan, owner 24 Nov 2026). The
website's build reads them (website/apps8.py live_seo). Public words only: the keywords and the plan stay in Desk.
"""

import frappe
from frappe.rate_limiter import rate_limit


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=3600)
def pages() -> dict:
	"""{pages: [{page, title, description}]} — the website's search titles and descriptions as set in Desk › QTT SEO Plan."""
	doc = frappe.get_cached_doc("QTT SEO Plan")
	return {"pages": [{"page": p.page, "title": p.title or "", "description": p.description or ""} for p in doc.pages]}
