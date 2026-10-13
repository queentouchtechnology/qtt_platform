"""
Adaptive action cards for the app's home (pure — no frappe; qtt_platform.api.home
gathers and serves them).

A card is the one next thing worth doing, for this person, in this business,
right now — built from live state and their role, never a static tip:

	{"key": "pulse.approvals",            # stable id (dismiss / dedupe)
	 "product": "QTT_OFFICE_PULSE",       # optional: whose card
	 "priority": 80,                      # 0–100, higher first
	 "tone": "warning",                   # info | success | warning | danger
	 "icon": "approval",                  # app icon name
	 "title": "{n} requests waiting for you",   # English source, translated in the app
	 "body": "Leave and expense claims from your team.",
	 "args": {"n": 3},                    # values for {placeholders}
	 "action": {"label": "Review", "kind": "product", "target": "QTT_OFFICE_PULSE"}}

Action kinds: "product" (open that app), "section" (an app tab: workspace,
apps, …), "url" (open a link). Every app adds its own cards through the
`qtt_home_cards` hook: a function (user, tenant) -> list of cards.
"""

TONES = ("info", "success", "warning", "danger")
KINDS = ("product", "section", "url", "screen")  # screen: an app screen id (assistant/screens.json), opened in its app
MAX_CARDS = 6


def clean(card: dict) -> dict | None:
	"""A valid card (defaults filled) or None."""
	if not isinstance(card, dict) or not card.get("key") or not card.get("title"):
		return None
	action = card.get("action") or {}
	if action and (action.get("kind") not in KINDS or not action.get("target")):
		action = {}
	try:
		priority = max(0, min(100, int(card.get("priority", 50))))
	except (TypeError, ValueError):
		priority = 50
	return {
		"key": str(card["key"]),
		"product": card.get("product"),
		"priority": priority,
		"tone": card.get("tone") if card.get("tone") in TONES else "info",
		"icon": card.get("icon") or "info",
		"title": str(card["title"]),
		"body": str(card.get("body") or ""),
		"args": {k: v for k, v in (card.get("args") or {}).items() if isinstance(v, (str, int, float))},
		"action": {"label": str(action.get("label") or "Open"), "kind": action["kind"], "target": str(action["target"])} if action else None,
	}


def rank(cards: list, dismissed: set[str] = frozenset(), limit: int = MAX_CARDS) -> list[dict]:
	"""Valid, not dismissed, one per key (highest priority wins), most important first."""
	best: dict[str, dict] = {}
	for raw in cards:
		c = clean(raw)
		if not c or c["key"] in dismissed:
			continue
		if c["key"] not in best or c["priority"] > best[c["key"]]["priority"]:
			best[c["key"]] = c
	tone_weight = {"danger": 3, "warning": 2, "info": 1, "success": 0}
	return sorted(best.values(), key=lambda c: (-c["priority"], -tone_weight[c["tone"]], c["key"]))[:limit]


def platform_cards(*, can_manage: bool, sub_status: str | None, trial_days_left: int | None,
				   profile_missing: list[str], team_size: int) -> list[dict]:
	"""The business-level cards (owner / admin only)."""
	if not can_manage:
		return []
	cards = []
	if sub_status == "past_due":
		cards.append({"key": "billing.past_due", "priority": 95, "tone": "danger", "icon": "payments",
					  "title": "Payment is due", "body": "Pay now so your team keeps using the apps without a break.",
					  "action": {"label": "Pay now", "kind": "section", "target": "workspace"}})
	if trial_days_left is not None and 0 <= trial_days_left <= 7:
		cards.append({"key": "billing.trial_ending", "priority": 85, "tone": "warning", "icon": "timer",
					  "title": "Your free trial ends in {n} days" if trial_days_left != 1 else "Your free trial ends tomorrow",
					  "body": "Choose a plan to keep everything running.", "args": {"n": trial_days_left},
					  "action": {"label": "Choose a plan", "kind": "section", "target": "workspace"}})
	if profile_missing:
		cards.append({"key": "profile.incomplete", "priority": 60, "tone": "info", "icon": "storefront",
					  "title": "Finish your business profile",
					  "body": "Add your {missing} — they appear on your bills, payslips and website.",
					  "args": {"missing": ", ".join(profile_missing)},
					  "action": {"label": "Finish profile", "kind": "section", "target": "workspace"}})
	if team_size <= 1:
		cards.append({"key": "team.invite", "priority": 40, "tone": "info", "icon": "group_add",
					  "title": "Bring your team in", "body": "Invite the people who work with you — each sees only what they need.",
					  "action": {"label": "Invite", "kind": "section", "target": "workspace"}})
	return cards
