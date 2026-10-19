"""
Landing pages on the web (QTT Studio › Landing pages, PROJ-0012 S7): /p/<address> serves a published page — or a draft,
with its private preview key (?preview=…, never shown to search engines). Everything else is left to Frappe.
hooks.page_renderer.
"""

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer


class LandingPageRenderer(BaseRenderer):
	def can_render(self) -> bool:
		return self.path.startswith("p/") and self.path.count("/") == 1

	def render(self):
		from qtt_platform.api import studio_pages

		slug = self.path.split("/", 1)[1]
		preview = (frappe.form_dict.get("preview") or "").strip()
		html = studio_pages.public_html(slug, preview)
		if html is None:
			return self.build_response("<!doctype html><title>Not found</title><p style='font-family:sans-serif'>This page isn't here.</p>", 404)
		headers = {"Cache-Control": "no-store" if preview else "public, max-age=300"}
		return self.build_response(html, 200, headers)
