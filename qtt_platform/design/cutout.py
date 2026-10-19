"""
Remove background (PROJ-0011): a business's own photo → the same photo with a transparent background, by rembg
(open source) on QTT's automation server, beside the renderer and behind its password (QTT App Settings › Design
renderer — the cut-out service is the same address with /cutout instead of /render). No outside service, no AI images:
only photos the business uploaded itself.

QTT Studio (PROJ-0012 S1) asks for the finer cut-out (BiRefNet: hair, fur, see-through edges) — its own service at
/cutout-hq, used when QTT App Settings › "Studio: finer cut-outs" is ticked; otherwise, or when it fails, the standard one.
"""

import frappe
import requests
from frappe import _

MODELS = {"person": "u2net_human_seg", "general": "isnet-general-use"}
# the lite model for people too: the full-size BiRefNet (portrait) needs more than the 4.5 GB the service may use
FINE_MODELS = {"person": "birefnet-general-lite", "general": "birefnet-general-lite"}
TIMEOUT = 120
FINE_TIMEOUT = 240


def _post(s, path: str, data: bytes, model: str, timeout: int) -> bytes | None:
	url, password = (s.get("render_url") or "").rstrip("/"), s.get_password("render_password", raise_exception=False)
	base = url[: -len("/render")] if url.endswith("/render") else url
	try:
		r = requests.post(f"{base}/{path}/api/remove", auth=(s.get("render_user") or "qtt", password),
						  files={"file": ("photo", data, "application/octet-stream")}, data={"model": model}, timeout=timeout)
	except requests.RequestException:
		frappe.log_error(title=f"Remove background ({path}): not reachable")
		return None
	if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
		frappe.log_error(title=f"Remove background ({path}): failed", message=f"{r.status_code} {r.text[:300]}")
		return None
	return r.content


def remove_background(data: bytes, kind: str = "general", *, fine: bool = False) -> bytes:
	"""PNG bytes with the background removed (a person: the people model; anything else: the general one). `fine`: Studio's
	finer cut-out when it's switched on, the standard one otherwise."""
	s = frappe.get_cached_doc("QTT App Settings")
	if not (s.get("render_url") or "").strip() or not s.get_password("render_password", raise_exception=False):
		frappe.throw(_("Removing backgrounds isn't set up yet — QTT is setting this up."))
	png = None
	if fine and s.get("fine_cutout"):
		png = _post(s, "cutout-hq", data, FINE_MODELS.get(kind, FINE_MODELS["general"]), FINE_TIMEOUT)
	if png is None:
		png = _post(s, "cutout", data, MODELS.get(kind, MODELS["general"]), TIMEOUT)
	if png is None:
		frappe.throw(_("Couldn't remove the background just now — please try again in a minute."))
	from qtt_platform.design.photos import trim

	return trim(png)
