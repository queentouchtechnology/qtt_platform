"""Every AI action QTT OS does, by its action code — QTT AI Action docs, and the usage record each AI call writes.

  ACTIONS          the list (code, what it does, app area, product, counts on the plan, where it happens)
  sync()           after migrate: a code missing in Frappe is added; one already there is left as edited in Desk
  record(...)      one QTT AI Usage Record for one AI call — the action code, business, person, provider, model, tokens,
                   cost and time; success or failure. Written in the request itself (a GET's write is kept too) — no
                   background job. Never raises: a record that can't be written never stops the AI answer.
  model_for(code)  the model an action uses (its own, else the QTT Assistant model)

Rules for the plan's AI allowance (api/free_use) count only actions with counts_for_plan on.
"""

import frappe

DOC = "QTT AI Action"
USAGE = "QTT AI Usage Record"
PLATFORM = "QTT_OS"

# code, what it does, app area, product, counts on the plan, where it happens
ACTIONS: list[tuple[str, str, str, str, int, str]] = [
	("assistant.ask", "Ask QTT — an answer in the app", "os", PLATFORM, 1, "qtt_platform.api.assistant.ask"),
	("knowledge.answer", "Know your business — an answer", "os", PLATFORM, 1, "qtt_platform.api.knowledge"),
	("team.ai", "Team chat — AI help (summary, reply, translate)", "team", PLATFORM, 1, "qtt_platform.api.team_extras"),
	("studio.words", "Studio — words for a design", "studio", "QTT_STUDIO", 1, "qtt_platform.api.studio"),
	("studio.image", "Studio — a picture made", "studio", "QTT_STUDIO", 1, "qtt_platform.studio.images"),
	("content.article.write", "Content Hub — an article written", "content", "QTT_SERVICES", 1, "qtt_services.api.marketing._article_for"),
	("content.newsletter.write", "Content Hub — a newsletter written", "content", "QTT_SERVICES", 1, "qtt_services.api.newsletters._draft_for"),
	("social.post.draft", "Social media — a post drafted (autopilot, series)", "social", "QTT_SERVICES", 1, "qtt_services.api.marketing._draft_for"),
	("social.quick.write", "Social media — a quick post written", "social", "QTT_SERVICES", 1, "qtt_services.api.marketing_quick._write"),
	("social.quick.rewrite", "Social media — a post rewritten", "social", "QTT_SERVICES", 1, "qtt_services.api.marketing_quick.rewrite"),
	("social.idea.post", "Social media — a post from an idea", "social", "QTT_SERVICES", 1, "qtt_services.api.marketing_social._post_for_idea"),
	("social.reply.suggest", "Social media — a reply suggested to a comment", "social", "QTT_SERVICES", 1,
	 "qtt_services.api.marketing_social.suggest_reply"),
	("whatsapp.owner.answer", "WhatsApp — an answer to the owner's question about the business", "whatsapp", "QTT_SERVICES", 1,
	 "qtt_services.api.automations.answer_owner"),
	("whatsapp.daily.report", "WhatsApp — the owner's daily report in short", "whatsapp", "QTT_SERVICES", 0,
	 "qtt_services.api.automations._write"),
	("receptionist.reply", "WhatsApp receptionist — a reply to a customer", "whatsapp", "QTT_SERVICES", 0,
	 "qtt_services.api.receptionist._ask"),
	("website.words", "Website — words for a page", "website", "QTT_SERVICES", 1, "qtt_services.api.site_words.write"),
	("hr.import.read", "HR & staff — reading a staff sheet", "hr", "QTT_OFFICE_PULSE", 1, "qtt_office_pulse.api.people_io._ai_map"),
]
CODES = {a[0] for a in ACTIONS}


def sync() -> None:
	"""after_migrate: every code in ACTIONS is a QTT AI Action (missing ones added; edits in Desk kept)."""
	if not frappe.db.table_exists(DOC):
		return
	products = set(frappe.get_all("QTT Product", pluck="name"))
	for code, label, area, product, counts, where in ACTIONS:
		if frappe.db.exists(DOC, code):
			continue
		frappe.get_doc({"doctype": DOC, "code": code, "label": label, "area": area, "product": product if product in products else None,
						"counts_for_plan": counts, "description": where}).insert(ignore_permissions=True, ignore_mandatory=True)
	sync_accounts()


def _action(code: str | None) -> dict:
	if not code:
		return {}
	cache = getattr(frappe.local, "qtt_ai_actions", None)
	if cache is None:
		cache = frappe.local.qtt_ai_actions = {}
	if code not in cache:
		row = frappe.db.get_value(DOC, code, ["product", "model", "counts_for_plan"], as_dict=True) if frappe.db.table_exists(DOC) else None
		if row is None:
			fallback = next((a for a in ACTIONS if a[0] == code), None)
			row = frappe._dict(product=fallback[3] if fallback else PLATFORM, model=None, counts_for_plan=fallback[4] if fallback else 1)
		cache[code] = row
	return cache[code]


def start_job() -> None:
	"""A paid AI job (Studio, Team chat) starts: its AI calls add their tokens here instead of writing records."""
	frappe.local.qtt_ai_acc = {"input": 0, "output": 0, "model": None, "provider": None}


def end_job() -> dict:
	"""The job's tokens, model and provider (and no more adding up)."""
	acc = getattr(frappe.local, "qtt_ai_acc", None) or {"input": 0, "output": 0, "model": None, "provider": None}
	frappe.local.qtt_ai_acc = None
	return acc


def model_for(code: str | None, default: str) -> str:
	"""The model this action uses: its own (QTT AI Action › Model), else the QTT Assistant model."""
	return (_action(code).get("model") or "").strip() or default


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
	"""What the provider charges for these tokens (QTT AI Model prices per 1M tokens; 0 when not set)."""
	try:
		row = frappe.db.get_value("QTT AI Model", {"model_id": model}, ["cost_input_per_1m", "cost_output_per_1m"], as_dict=True)
	except Exception:
		row = None
	if not row:
		return 0.0
	return round(((row.cost_input_per_1m or 0) * input_tokens + (row.cost_output_per_1m or 0) * output_tokens) / 1_000_000, 6)


def record(*, action: str | None, tenant: str | None, provider: str, model: str, input_tokens: int, output_tokens: int, status: str,
		   duration_ms: int, credits_used: float = 0.0, provider_cost: float | None = None) -> str | None:
	"""One QTT AI Usage Record for one AI call. Returns its name; None when it couldn't be written (logged)."""
	try:
		from qtt_platform.tenant.context import resolve_active_tenant

		user = frappe.session.user if frappe.session and frappe.session.user not in (None, "Guest") else "Administrator"
		tenant = tenant or resolve_active_tenant(user)
		if not tenant:
			from qtt_platform.api.leads import house_tenant

			tenant = house_tenant()
		a = _action(action)
		doc = frappe.get_doc({
			"doctype": USAGE, "tenant": tenant, "product": a.get("product") or PLATFORM, "user": user,
			"feature": action or "unknown", "action": action if action in CODES or (action and frappe.db.exists(DOC, action)) else None,
			"provider": provider, "model": model, "status": "success" if status == "success" else "error",
			"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens,
			"credits_used": credits_used,
			"provider_cost": (provider_cost if provider_cost is not None else cost_of(model, input_tokens, output_tokens)) if status == "success" else 0,
			"duration_ms": duration_ms,
		}).insert(ignore_permissions=True, ignore_links=True)
		frappe.local.flags.commit = True  # kept even when the call came from a GET (Frappe rolls a GET back otherwise)
		return doc.name
	except Exception:
		frappe.log_error(title=f"AI usage not recorded: {action}")
		return None


# The AI accounts QTT pays (QTT Admin › AI): what each is used for, where its key is set and how to top it up. Filled in
# on deploy only where the QTT AI Provider row has nothing yet — QTT Admin edits them (the provider's pages can change).
ACCOUNTS = {
	"deepseek": {
		"label": "DeepSeek",
		"base_url": "https://api.deepseek.com",
		"used_for": "All text AI: articles, newsletters, social posts, replies to customers on WhatsApp, daily reports, Ask QTT, "
					"Know your business, Studio words, Team chat help, website words, reading staff sheets.",
		"key_where": "Desk › QTT App Settings › QTT Assistant › API key (the model is set there too)",
		"dashboard_url": "https://platform.deepseek.com/usage",
		"topup_url": "https://platform.deepseek.com/top_up",
		"topup_steps": "Sign in at platform.deepseek.com with QTT's account.\nOpen Top up.\nChoose an amount and pay by card or PayPal.\n"
					   "The new balance shows in QTT Admin › AI within 30 minutes (the usage collector checks every half hour).",
	},
	"openai": {
		"label": "OpenAI",
		"used_for": "Studio: AI pictures and backgrounds (gpt-image-1) and reading a picture (gpt-4o-mini).",
		"key_where": "Desk › QTT AI Provider › openai › API key",
		"dashboard_url": "https://platform.openai.com/usage",
		"topup_url": "https://platform.openai.com/settings/organization/billing/overview",
		"topup_steps": "Sign in at platform.openai.com with QTT's account.\nSettings › Billing › Add to credit balance.\n"
					   "Optional: turn on auto recharge so pictures never stop.",
	},
	"recraft": {
		"label": "Recraft",
		"used_for": "Studio: AI logo symbols (recraftv3).",
		"key_where": "Desk › QTT AI Provider › recraft › API key",
		"dashboard_url": "https://www.recraft.ai/",
		"topup_url": "https://www.recraft.ai/",
		"topup_steps": "Sign in at recraft.ai with QTT's account.\nOpen your profile › API.\nBuy API units.",
	},
}
ACCOUNT_FIELDS = ("label", "used_for", "key_where", "dashboard_url", "topup_url", "topup_steps")


def sync_accounts() -> None:
	"""after_migrate (with sync): each account in ACCOUNTS has a QTT AI Provider row with its top-up details. DeepSeek's
	row is only the account (switched off for the AI gateway — its key lives in QTT App Settings); a field already
	filled in is left as edited."""
	if not frappe.db.table_exists("QTT AI Provider") or not frappe.get_meta("QTT AI Provider").has_field("topup_url"):
		return
	for key, info in ACCOUNTS.items():
		if not frappe.db.exists("QTT AI Provider", key):
			if key != "deepseek":
				continue  # only DeepSeek is added; others exist when QTT set them up
			frappe.get_doc({"doctype": "QTT AI Provider", "provider_key": key, "enabled": 0, "base_url": info.get("base_url")}).insert(
				ignore_permissions=True, ignore_mandatory=True)
		doc = frappe.get_doc("QTT AI Provider", key)
		changed = False
		for f in ACCOUNT_FIELDS:
			if not doc.get(f) and info.get(f):
				doc.set(f, info[f])
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
