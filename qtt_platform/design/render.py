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


def _send(path: str, page_html: str, form: dict, files: dict[str, bytes] | None, magic: bytes) -> bytes:
	s = frappe.get_cached_doc("QTT App Settings")
	url, password = (s.get("render_url") or "").rstrip("/"), s.get_password("render_password", raise_exception=False)
	if not url or not password:
		frappe.throw(_("Pictures can't be made yet — QTT is setting this up."))
	multipart = [("files", ("index.html", page_html.encode("utf-8"), "text/html"))]
	for name, data in (files or {}).items():
		multipart.append(("files", (name, data, "application/octet-stream")))
	if "window.qttReady" in page_html:  # wait until the fonts are in (and a post's text has been fitted)
		form["waitForExpression"] = "window.qttReady === true"
	try:
		r = requests.post(f"{url}{path}", auth=(s.get("render_user") or "qtt", password), data=form, files=multipart, timeout=TIMEOUT)
	except requests.RequestException:
		frappe.log_error(title="Design renderer: not reachable")
		frappe.throw(_("Couldn't make the picture just now — please try again in a minute."))
	if r.status_code != 200 or not r.content.startswith(magic):
		frappe.log_error(title="Design renderer: failed", message=f"{r.status_code} {r.text[:500]}")
		frappe.throw(_("Couldn't make the picture just now — please try again in a minute."))
	return r.content


def png(page_html: str, width: int, height: int, files: dict[str, bytes] | None = None, *, transparent: bool = False) -> bytes:
	"""Screenshot the page at exactly width × height (`transparent`: no white behind it — a logo). Raises a friendly
	error when the renderer can't be reached."""
	form = {"width": str(int(width)), "height": str(int(height)), "clip": "true", "format": "png",
			"skipNetworkIdleEvent": "false", "waitDelay": "0.6s", "optimizeForSpeed": "true"}
	if transparent:
		form["omitBackground"] = "true"
	return _send("/forms/chromium/screenshot/html", page_html, form, files, b"\x89PNG")


def pdf(page_html: str, width_in: float, height_in: float, files: dict[str, bytes] | None = None) -> bytes:
	"""The page as a one-page PDF of width × height inches, no margins (a logo for a print shop)."""
	form = {"paperWidth": f"{width_in:.3f}", "paperHeight": f"{height_in:.3f}", "marginTop": "0", "marginBottom": "0",
			"marginLeft": "0", "marginRight": "0", "printBackground": "true", "skipNetworkIdleEvent": "false", "waitDelay": "0.6s"}
	return _send("/forms/chromium/convert/html", page_html, form, files, b"%PDF")
