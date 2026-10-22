"""
Launch flow rules (PROJ-0017) — "What do you want to launch today?" and Help Me Choose. Pure: no Frappe;
tests/test_launch_rules.py.

  GOALS        what an owner can say they want (step 1), each with the products and Suite services that serve it
  recommend    goals → the products to show (step 2), recommended first, each with the reason in plain words
  suite_pick   goals → which QTT Business Suite services start ticked in Customize (step 3)
  steps        a launched product's progress (setup → design and content → connect → live) from what really happened

Products are the QTT OS apps (QTT_OFFICE_PULSE, QTT_ORBITRA, QTT_STUDIO) and QTT Business Suite (QTT_SERVICES), whose
parts are the services (WEBSITE_DEV, ECOMMERCE_STORE, AI_WHATSAPP, MARKETING_ASSISTANT). Nothing here promises a
feature that isn't built: every goal points only at what the products already do.
"""

SUITE = "QTT_SERVICES"
APPS = ("QTT_OFFICE_PULSE", "QTT_ORBITRA", "QTT_STUDIO")
PRODUCTS = APPS + (SUITE,)
SERVICES = ("WEBSITE_DEV", "ECOMMERCE_STORE", "AI_WHATSAPP", "MARKETING_ASSISTANT")

# key: (title, line under it, icon, {product: reason}, suite services it ticks)
GOALS = {
	"customers": ("Get more customers", "I want more enquiries and sales", "icon_chart",
				  {SUITE: "A website, your Google profile and posts every week bring people to you",
				   "QTT_STUDIO": "Posts, flyers and offers in your brand, made in minutes"},
				  ("WEBSITE_DEV", "MARKETING_ASSISTANT")),
	"sell_online": ("Sell online", "I want to take orders and payments online", "icon_cart",
					{SUITE: "An online store with UPI and card payments, set up and looked after by QTT",
					 "QTT_ORBITRA": "Your stock, bills and GST in one place as orders come in"},
					("ECOMMERCE_STORE",)),
	"whatsapp": ("Answer customers on WhatsApp", "I want replies even when I'm busy", "icon_mail",
				 {SUITE: "Your own WhatsApp number with an AI receptionist and one shared inbox"},
				 ("AI_WHATSAPP",)),
	"automate": ("Automate my work", "I want to save time on daily tasks", "icon_sync",
				 {SUITE: "Reminders, follow-ups and daily reports on WhatsApp, done for you",
				  "QTT_ORBITRA": "Bills, stock and payments that keep themselves up to date"},
				 ("AI_WHATSAPP",)),
	"team": ("Manage my team", "Attendance, leave, payroll and files", "icon_team",
			 {"QTT_OFFICE_PULSE": "Check-in on the phone, leave, payroll, tasks and shared files for your team"},
			 ()),
	"run_business": ("Run billing and stock", "Sales, purchases, stock and accounts", "icon_chart",
					 {"QTT_ORBITRA": "POS, GST bills, stock, purchases and accounts on your phone"},
					 ()),
	"content": ("Create marketing content", "Posts, logos, flyers and documents", "icon_star",
				{"QTT_STUDIO": "Posts, logos, flyers, menus, letterheads and Shorts in your brand",
				 SUITE: "The Marketing assistant writes and posts for you every week"},
				("MARKETING_ASSISTANT",)),
	"everything": ("Build a complete business system", "I want it all working together", "icon_rocket",
				   {"QTT_OFFICE_PULSE": "Your team", "QTT_ORBITRA": "Your sales and stock", "QTT_STUDIO": "Your designs",
					SUITE: "Your website, WhatsApp and marketing"},
				   ("WEBSITE_DEV", "AI_WHATSAPP", "MARKETING_ASSISTANT")),
}


def goals() -> list[dict]:
	return [{"key": k, "title": t, "line": line, "icon": icon} for k, (t, line, icon, _p, _s) in GOALS.items()]


def recommend(chosen: list[str] | None, have: dict | None = None) -> list[dict]:
	"""Every product, the ones the goals point to first ("recommended", with their reasons, most-asked first); the rest
	after them. have: {product: status} — a product the business already has says so instead of being offered again."""
	chosen = [g for g in (chosen or []) if g in GOALS]
	have = have or {}
	score: dict[str, int] = {}
	reasons: dict[str, list[str]] = {}
	for g in chosen:
		for p, why in GOALS[g][3].items():
			score[p] = score.get(p, 0) + 1
			if why not in reasons.setdefault(p, []):
				reasons[p].append(why)
	order = sorted(PRODUCTS, key=lambda p: (-score.get(p, 0), PRODUCTS.index(p)))
	return [{"product": p, "recommended": score.get(p, 0) > 0, "reasons": reasons.get(p, []), "have": have.get(p)} for p in order]


def suite_pick(chosen: list[str] | None) -> list[str]:
	"""The Suite services that start ticked for these goals, in the Suite's own order."""
	want = {s for g in (chosen or []) if g in GOALS for s in GOALS[g][4]}
	if "ECOMMERCE_STORE" in want:
		want.discard("WEBSITE_DEV")  # the store is the website
	return [s for s in SERVICES if s in want]


STEP_KEYS = ("setup", "design", "connect", "live")
STEP_TEXT = {
	"setup": ("Setup started", "We're setting up your solution"),
	"design": ("Design and content", "Your words, photos and colours go in"),
	"connect": ("Connect", "Your website address, WhatsApp number or tools are connected"),
	"live": ("Go live", "It's ready for your customers"),
}


def steps(kind: str, status: str | None, stage: str | None = None) -> list[dict]:
	"""Progress of one launched product. kind 'app': a trial or plan starts at once — setup and live are done.
	kind 'service': from the service's status (requested / awaiting_payment / setup / active) and its website's stage
	(building / preview / going_live / live)."""
	if kind == "app":
		done = 4 if status in ("trial", "active") else (1 if status else 0)
	elif status == "active" and not stage:
		done = 4  # a service without a website (WhatsApp, Marketing assistant) is live once it's active
	else:
		done = {"preview": 2, "going_live": 3, "live": 4}.get(stage or "", 1 if status in ("requested", "setup", "active") else 0)
	return [{"key": k, "title": STEP_TEXT[k][0], "line": STEP_TEXT[k][1], "done": i < done} for i, k in enumerate(STEP_KEYS)]
