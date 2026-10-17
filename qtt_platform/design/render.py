"""
The design renderer (PROJ-0011 B): a whole HTML page → a PNG, by headless Chromium (Gotenberg) on QTT's automation
server — QTT App Settings › Design renderer (address, user, password). No AI images: designs are HTML, CSS and SVG in
the business's own palette, fonts and logo. Pictures a page uses (logo, photos) travel with it as files beside the
page and are referenced by file name.
"""

import frappe
import requests
from frappe import _

TIMEOUT = 90


def ready() -> bool:
	s = frappe.get_cached_doc("QTT App Settings")
	return bool(s.get("render_url") and s.get_password("render_password", raise_exception=False))


def png(page_html: str, width: int, height: int, files: dict[str, bytes] | None = None) -> bytes:
	"""Screenshot the page at exactly width × height. Raises a friendly error when the renderer can't be reached."""
	s = frappe.get_cached_doc("QTT App Settings")
	url, password = (s.get("render_url") or "").rstrip("/"), s.get_password("render_password", raise_exception=False)
	if not url or not password:
		frappe.throw(_("Pictures can't be made yet — QTT is setting this up."))
	multipart = [("files", ("index.html", page_html.encode("utf-8"), "text/html"))]
	for name, data in (files or {}).items():
		multipart.append(("files", (name, data, "application/octet-stream")))
	form = {"width": str(int(width)), "height": str(int(height)), "clip": "true", "format": "png",
			"skipNetworkIdleEvent": "false", "waitDelay": "0.6s", "optimizeForSpeed": "true"}
	try:
		r = requests.post(f"{url}/forms/chromium/screenshot/html", auth=(s.get("render_user") or "qtt", password),
						  data=form, files=multipart, timeout=TIMEOUT)
	except requests.RequestException:
		frappe.log_error(title="Design renderer: not reachable")
		frappe.throw(_("Couldn't make the picture just now — please try again in a minute."))
	if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
		frappe.log_error(title="Design renderer: failed", message=f"{r.status_code} {r.text[:500]}")
		frappe.throw(_("Couldn't make the picture just now — please try again in a minute."))
	return r.content
