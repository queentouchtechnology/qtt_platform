"""
QTT Studio — AI pictures (PROJ-0012 S1): an empty scene for an AI background, made by the model routed to the
"studio_image" task (QTT AI Model; the key is typed in Desk › QTT AI Provider). Only ever an empty scene — the
business's own product is put on it afterwards, never drawn by the AI. Clients never see which provider made it.
"""

import base64

import frappe
import requests
from frappe import _

TASK = "studio_image"
TIMEOUT = 180
# rough cost a picture (USD, medium quality) — for QTT's usage records, not shown to clients
COST = {"1024x1024": 0.042, "1024x1536": 0.063, "1536x1024": 0.063}


def ready() -> tuple[str, str, str, str] | None:
	"""(provider, model, base url, key) when AI pictures are set up, else None."""
	from qtt_platform.ai.core.routing import resolve_routing

	try:
		provider, model = resolve_routing(TASK)
	except Exception:
		return None
	p = frappe.get_doc("QTT AI Provider", provider)
	key = p.get_password("api_key", raise_exception=False)
	if not key:
		return None
	return provider, model, (p.base_url or "https://api.openai.com/v1").rstrip("/"), key


def need_ready() -> tuple[str, str, str, str]:
	r = ready()
	if not r:
		frappe.throw(_("AI backgrounds aren't switched on yet — QTT is setting this up."))
	return r


def scene(prompt: str, size: str, setup: tuple[str, str, str, str]) -> bytes | None:
	"""One picture (PNG/JPEG bytes) for the prompt, or None when it failed (logged, never shown to the client)."""
	_provider, model, base, key = setup
	try:
		r = requests.post(f"{base}/images/generations", headers={"Authorization": f"Bearer {key}"},
						  json={"model": model, "prompt": prompt, "size": size, "quality": "medium", "n": 1}, timeout=TIMEOUT)
	except requests.RequestException:
		frappe.log_error(title="QTT Studio: AI picture not reachable")
		return None
	if r.status_code != 200:
		frappe.log_error(title="QTT Studio: AI picture failed", message=f"{r.status_code} {r.text[:500]}")
		return None
	try:
		item = r.json()["data"][0]
		if item.get("b64_json"):
			return base64.b64decode(item["b64_json"])
		if item.get("url"):
			return requests.get(item["url"], timeout=60).content
	except (KeyError, IndexError, ValueError, requests.RequestException):
		frappe.log_error(title="QTT Studio: AI picture unreadable")
	return None
