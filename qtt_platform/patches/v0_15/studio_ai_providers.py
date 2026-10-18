"""QTT Studio (PROJ-0012): the AI providers and models Studio uses, without keys — the owner types each key in Desk
(QTT AI Provider › openai / recraft › API key). Never overwrites a provider or model that's already there."""

import frappe

PROVIDERS = (
	("openai", "https://api.openai.com/v1"),
	("recraft", "https://external.api.recraft.ai/v1"),
)
MODELS = (  # (provider, model id, task) — change the model id in Desk any time
	("openai", "gpt-4o-mini", "studio_vision"),  # reading uploaded posters and photos (S8, S1)
	("openai", "gpt-image-1", "studio_image"),  # AI backgrounds and custom posters (credits)
	("recraft", "recraftv3", "studio_logo"),  # AI vector logos (S5)
)


def execute():
	for key, url in PROVIDERS:
		if not frappe.db.exists("QTT AI Provider", key):
			frappe.get_doc({"doctype": "QTT AI Provider", "provider_key": key, "enabled": 1, "base_url": url}).insert(ignore_permissions=True)
	for provider, model, task in MODELS:
		if not frappe.db.exists("QTT AI Model", {"default_for_task": task}):
			frappe.get_doc({"doctype": "QTT AI Model", "provider": provider, "model_id": model, "default_for_task": task}).insert(ignore_permissions=True)
