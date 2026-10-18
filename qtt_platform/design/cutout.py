"""
Remove background (PROJ-0011): a business's own photo → the same photo with a transparent background, by rembg
(open source) on QTT's automation server, beside the renderer and behind its password (QTT App Settings › Design
renderer — the cut-out service is the same address with /cutout instead of /render). No outside service, no AI images:
only photos the business uploaded itself.
"""

import frappe
import requests
from frappe import _

MODELS = {"person": "u2net_human_seg", "general": "isnet-general-use"}
TIMEOUT = 120


def remove_background(data: bytes, kind: str = "general") -> bytes:
	"""PNG bytes with the background removed (a person: the people model; anything else: the general one)."""
	s = frappe.get_cached_doc("QTT App Settings")
	url, password = (s.get("render_url") or "").rstrip("/"), s.get_password("render_password", raise_exception=False)
	if not url or not password:
		frappe.throw(_("Removing backgrounds isn't set up yet — QTT is setting this up."))
	base = url[: -len("/render")] if url.endswith("/render") else url
	try:
		r = requests.post(f"{base}/cutout/api/remove", auth=(s.get("render_user") or "qtt", password),
						  files={"file": ("photo", data, "application/octet-stream")},
						  data={"model": MODELS.get(kind, MODELS["general"])}, timeout=TIMEOUT)
	except requests.RequestException:
		frappe.log_error(title="Remove background: not reachable")
		frappe.throw(_("Couldn't remove the background just now — please try again in a minute."))
	if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
		frappe.log_error(title="Remove background: failed", message=f"{r.status_code} {r.text[:300]}")
		frappe.throw(_("Couldn't remove the background just now — please try again in a minute."))
	return r.content
