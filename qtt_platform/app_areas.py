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
