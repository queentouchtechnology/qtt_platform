"""
Explore QTT OS — the rules (pure: no frappe; tests/test_explore.py).

Every business owner sees all of QTT OS in one place: the apps (Onbox, Orbitra, Office Pulse) and the
managed services, each with its plans. They start an app's free trial (once per app, when its plans have
one) or choose a plan; a paid plan starts when its first invoice is paid.

  feature_lines   a plan's feature rows (max_agents 10, payroll 1) → lines an owner reads
  can_trial       may this business still start this app's free trial?
  app_status      what the business has of an app right now (for the card's pill)
"""

# Plan feature keys (QTT Plan › Features) → how an owner reads them. {n} is the row's value.
# A switch (1 / 0) shows only when it's on; a limit of 0 or less means unlimited.
LIMITS = {
	"max_agents": "{n} team members",
	"max_inboxes": "{n} inboxes",
	"max_users": "{n} users",
	"max_stores": "{n} stores or branches",
	"max_employees": "Up to {n} employees",
	"ai_credits_grant": "{n} AI replies a month",
}
UNLIMITED = {
	"max_agents": "Unlimited team members",
	"max_inboxes": "Unlimited inboxes",
	"max_users": "Unlimited users",
	"max_stores": "Unlimited stores or branches",
	"max_employees": "Unlimited employees",
}
SWITCHES = {
	"channel_whatsapp": "WhatsApp",
	"channel_website": "Website chat",
	"channel_facebook": "Facebook Messenger",
	"channel_instagram": "Instagram",
	"channel_email": "Email",
	"ai_agent": "AI assistant replies for you",
	"purchases": "Purchases",
	"accounts": "Accounts",
	"reports": "Reports",
	"payroll": "Payroll and payslips",
}
CHANNELS = ("channel_whatsapp", "channel_website", "channel_facebook", "channel_instagram", "channel_email")


def _num(value) -> int | None:
	try:
		return int(float(str(value).strip()))
	except (TypeError, ValueError):
		return None


def feature_lines(features: dict) -> list[str]:
	"""{feature_key: value} → readable lines, limits first, then what's switched on. Unknown keys are left out
	(internal settings never reach owners). The channels read as one line: "WhatsApp, Website chat and Email"."""
	out = []
	for key, text in LIMITS.items():
		if key not in features:
			continue
		n = _num(features[key])
		if n is None:
			continue
		if n <= 0:
			if key in UNLIMITED:
				out.append(UNLIMITED[key])
			continue  # 0 AI replies: simply not offered
		out.append(text.format(n=f"{n:,}"))
	on = [SWITCHES[k] for k in CHANNELS if _num(features.get(k)) == 1]
	if on:
		out.append(on[0] if len(on) == 1 else f"{', '.join(on[:-1])} and {on[-1]}")
	out += [text for key, text in SWITCHES.items() if key not in CHANNELS and _num(features.get(key)) == 1]
	return out


def can_trial(trial_days: int, had_before: bool) -> bool:
	"""A free trial is offered once per app: when the plan has trial days and the business never had the app."""
	return bool(trial_days and int(trial_days) > 0) and not had_before


def app_status(sub: dict | None, has_open_invoice: bool) -> str | None:
	"""None (doesn't have it) | 'trial' | 'active' | 'awaiting_payment' (chose a paid plan, first invoice not paid
	yet) | 'paused' (unpaid or switched off) — the current subscription, cancelled ones count as none."""
	if not sub or sub.get("status") == "cancelled":
		return None
	status = sub.get("status")
	if status == "trialing":
		return "trial"
	if status in ("active", "past_due"):
		return "active"
	if status == "suspended":
		return "awaiting_payment" if has_open_invoice and not sub.get("paid_until") else "paused"
	return None
