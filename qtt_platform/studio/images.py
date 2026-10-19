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


LOGO_TASK = "studio_logo"
LOGO_COST = 0.08  # USD a vector picture, for QTT's usage records


def ready(task: str = TASK) -> tuple[str, str, str, str] | None:
	"""(provider, model, base url, key) when the AI for `task` is set up, else None."""
	from qtt_platform.ai.core.routing import resolve_routing

	try:
		provider, model = resolve_routing(task)
	except Exception:
		return None
	p = frappe.get_doc("QTT AI Provider", provider)
	key = p.get_password("api_key", raise_exception=False)
	if not key:
		return None
	default = "https://external.api.recraft.ai/v1" if provider == "recraft" else "https://api.openai.com/v1"
	return provider, model, (p.base_url or default).rstrip("/"), key


def need_ready(task: str = TASK) -> tuple[str, str, str, str]:
	r = ready(task)
	if not r:
		frappe.throw(_("AI logos aren't switched on yet — QTT is setting this up.") if task == LOGO_TASK
					 else _("AI backgrounds aren't switched on yet — QTT is setting this up."))
	return r


VISION_TASK = "studio_vision"


def vision_json(messages: list[dict], setup: tuple[str, str, str, str]) -> str | None:
	"""A vision model's JSON answer about a picture (the messages carry it as a data: image), or None when it failed."""
	_provider, model, base, key = setup
	try:
		r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=90,
						  json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 900, "response_format": {"type": "json_object"}})
	except requests.RequestException:
		frappe.log_error(title="QTT Studio: vision not reachable")
		return None
	if r.status_code != 200:
		frappe.log_error(title="QTT Studio: vision failed", message=f"{r.status_code} {r.text[:500]}")
		return None
	try:
		return r.json()["choices"][0]["message"]["content"]
	except (KeyError, IndexError, ValueError):
		return None


def logo_marks(prompt: str, colours: list[str], setup: tuple[str, str, str, str], count: int = 2) -> list[str]:
	"""AI logo symbols (SVG text) in the brand's colours — the symbol only; the name is set beside it in a real font.
	[] when it failed (logged, never shown to the client)."""
	_provider, model, base, key = setup

	def rgb(h):
		h = h.lstrip("#")
		return [int(h[i:i + 2], 16) for i in (0, 2, 4)]

	body = {"prompt": prompt, "style": "vector_illustration", "model": model, "size": "1024x1024", "n": max(1, min(count, 4)),
			"response_format": "url", "controls": {"colors": [{"rgb": rgb(c)} for c in colours[:3]], "background_color": {"rgb": [255, 255, 255]}}}
	try:
		r = requests.post(f"{base}/images/generations", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=TIMEOUT)
	except requests.RequestException:
		frappe.log_error(title="QTT Studio: AI logo not reachable")
		return []
	if r.status_code != 200:
		frappe.log_error(title="QTT Studio: AI logo failed", message=f"{r.status_code} {r.text[:500]}")
		return []
	out = []
	for item in (r.json().get("data") or [])[:4]:
		try:
			s = requests.get(item.get("url"), timeout=60)
			if s.status_code == 200 and b"<svg" in s.content[:400]:
				out.append(s.content.decode("utf-8", "replace"))
		except requests.RequestException:
			continue
	return out


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
