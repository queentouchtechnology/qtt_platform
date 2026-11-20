"""Which app a usage event belongs to — the areas QTT Admin reports on (People, each app's page, Reports).

Pure. An event's area comes from its screen's name (`pulse.team` → HR & staff, `services.marketing.leads` → Content Hub),
else from its product, else it is QTT OS itself (opening the app, signing in, home, account). One list, so a new screen
name prefix is one line here.
"""

# key, label, product (for events that came without one), screen-name prefixes (longest match wins)
AREAS: list[tuple[str, str, str | None, tuple[str, ...]]] = [
	("hr", "HR & staff", "QTT_OFFICE_PULSE", ("pulse.", "p:QTT_OFFICE_PULSE")),
	("erp", "ERP", "QTT_ORBITRA", ("orbitra.", "p:QTT_ORBITRA")),
	("store", "Store", "QTT_SERVICES", ("services.store", "services.order", "services.catalog", "services.payments", "store.")),
	("website", "Website", "QTT_SERVICES", ("services.sites", "services.website", "services.domain", "services.deployment", "services.asset",
											 "website.")),
	("whatsapp", "WhatsApp & AI", "QTT_SERVICES", ("services.whatsapp", "services.receptionist", "services.automation", "wa.")),
	("content", "Content Hub", "QTT_SERVICES", ("services.marketing.content", "services.marketing.leads", "services.marketing.article",
												"services.marketing.newsletter", "services.marketing.lead", "content.")),
	("social", "Social media", "QTT_SERVICES", ("services.marketing", "social.")),
	("studio", "Studio", "QTT_STUDIO", ("studio.", "p:QTT_STUDIO")),
	("inbox", "Inbox", "QTT_ONBOX", ("onbox.", "inbox.", "p:QTT_ONBOX")),
	("suite", "Business Suite", "QTT_SERVICES", ("services.", "p:QTT_SERVICES")),
	("team", "Team & workplace", None, ("team.", "workplace.", "calendar.")),
	("admin", "QTT Admin", None, ("admin.",)),
	("os", "QTT OS (home, account, sign-in)", None, ()),
]

LABELS = {k: label for k, label, _p, _s in AREAS}
_BY_PRODUCT = {"QTT_OFFICE_PULSE": "hr", "QTT_ORBITRA": "erp", "QTT_STUDIO": "studio", "QTT_ONBOX": "inbox", "QTT_SERVICES": "suite"}
_PREFIXES = sorted(((prefix, key) for key, _l, _p, prefixes in AREAS for prefix in prefixes), key=lambda x: -len(x[0]))
_PRODUCT_OF = {k: p for k, _l, p, _s in AREAS}


def area(screen: str | None, product: str | None = None) -> str:
	"""The area key of one event."""
	s = (screen or "").strip()
	for prefix, key in _PREFIXES:
		if s.startswith(prefix):
			return key
	if product in _BY_PRODUCT:
		return _BY_PRODUCT[product]
	return "os"


def product_for(area_key: str, product: str | None) -> str | None:
	"""The event's product: the one it came with, else its area's."""
	return product or _PRODUCT_OF.get(area_key)


# Server calls → the app they serve (QTT Admin › Apps: each app's speed). Longest prefix wins; the rest is QTT OS.
CALLS: list[tuple[str, str]] = [
	("qtt_office_pulse.", "hr"),
	("hrms.", "hr"),
	("qtt_orbitra.", "erp"),
	("erpnext.", "erp"),
	("qtt_services.api.shop", "store"),
	("qtt_services.api.store", "store"),
	("qtt_services.api.sites", "website"),
	("qtt_services.api.site_", "website"),
	("qtt_services.api.designs", "website"),
	("qtt_services.api.golive", "website"),
	("qtt_services.api.my_whatsapp", "whatsapp"),
	("qtt_services.api.my_receptionist", "whatsapp"),
	("qtt_services.api.my_automations", "whatsapp"),
	("qtt_services.api.automations", "whatsapp"),
	("qtt_services.api.receptionist", "whatsapp"),
	("qtt_services.api.wa_", "whatsapp"),
	("qtt_services.api.messaging", "whatsapp"),
	("qtt_platform.api.leads", "content"),
	("qtt_services.api.newsletters", "content"),
	("qtt_services.api.content_series", "content"),
	("qtt_services.api.marketing.articles", "content"),
	("qtt_services.api.marketing.write_article", "content"),
	("qtt_services.api.marketing.article", "content"),
	("qtt_services.api.marketing", "social"),
	("qtt_services.api.google_business", "social"),
	("qtt_platform.api.studio", "studio"),
	("qtt_platform.api.post_templates", "studio"),
	("qtt_onbox.", "inbox"),
	("qtt_inbox.", "inbox"),
	("qtt_services.", "suite"),
	("qtt_platform.api.team", "team"),
	("qtt_platform.api.workplace", "team"),
	("qtt_platform.api.files", "team"),
	("qtt_platform.api.calendar", "team"),
	("qtt_platform.api.boards", "team"),
	("qtt_platform.api.notes", "team"),
	("qtt_platform.api.mail", "team"),
	("qtt_platform.api.whiteboard", "team"),
	("raven.", "team"),
	("qtt_platform.api.platform_admin", "admin"),
	("qtt_platform.api.saas_admin", "admin"),
	("qtt_platform.api.admin_", "admin"),
	("qtt_platform.api.servers", "admin"),
	("qtt_platform.api.perf", "admin"),
	("qtt_platform.api.errors", "admin"),
	("qtt_platform.api.usage_dashboard", "admin"),
	("qtt_platform.api.studio_admin", "admin"),
	("qtt_platform.api.marketing_content", "admin"),
	("qtt_platform.api.marketing_dashboard", "admin"),
]
_CALLS = sorted(CALLS, key=lambda x: -len(x[0]))

# Each app's free amounts and plan fair use (qtt_platform.free_use keys).
FREE_KEYS = {"hr": ["hr"], "erp": ["erp"], "website": ["website"], "store": ["store"], "whatsapp": ["whatsapp"], "social": ["social"],
			 "content": ["articles", "newsletters"], "studio": ["studio"]}
PLAN_KEYS = {"hr": ["hr"], "website": ["website"], "store": ["stores"], "whatsapp": ["offer_messages"], "social": ["social"],
			 "content": ["articles", "newsletters"]}


def area_of_call(name: str | None) -> str:
	"""The app a server call serves (perf_rules names: `x.y.z` or `resource:Doctype`)."""
	n = name or ""
	if n.startswith("resource:"):
		return "os"
	if n.startswith("qtt_platform.api.studio_admin"):
		return "admin"
	for prefix, key in _CALLS:
		if n.startswith(prefix):
			return key
	return "os"
