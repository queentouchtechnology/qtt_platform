# QTT Admin — for Queen Touch Technology staff only

QTT Admin is the staff side of QTT OS (only people with the QTT Platform Owner role see it). Open it from the account
switcher › QTT Admin. Its home shows the key numbers (workspaces, active, trials, monthly revenue, collected this
month, servers OK) and one **Needs attention** list, most urgent first; tapping an item opens the screen that fixes it.

## Needs attention (what can appear)
Servers in warning / critical / offline; client websites that are down; domains near or past expiry; servers whose
last Contabo snapshot is missing or old; failed payments; trials ending; set-up errors (Onbox, Office Pulse); client
requests nobody answered; marketing items waiting for approval; DeepSeek balance low or n8n failures; and QTT's
WhatsApp number — quality dropped, a template rejected / paused / disabled by Meta, a template approved (shown for a
day), or Meta changed a template's category. The WhatsApp items come from an hourly check (minute 40).

## Manage (the tiles)
- **Workspaces** — every business on QTT OS: open one to see its products, plans and people.
- **Plans** — each product's plans: price, trial, limits, subscribers; create or edit. Changes apply to new
  subscriptions at once.
- **Servers** — QTT's servers with their reports (CPU, memory, disk, services, Hermes), domains and snapshots.
- **Receptionists** — every client's WhatsApp AI receptionist with its set-up checklist (Onbox connected, WhatsApp
  number connected, owner's answers, live) and counts; **Put it live** connects it.
- **Services and pricing** — each managed service's name, wording, base prices and whether it's offered; each plan's
  name, monthly price, setup fee, automations allowed (AI & WhatsApp: 0 = every automation), products / pages /
  articles / newsletters limits. New orders use the new price; businesses already on a plan keep theirs.
- **Automation library** — the automations businesses choose from (name, what it does, when it runs, group, default
  time, order, shown or hidden) and how many businesses use each.
- **WhatsApp templates** — every message template on QTT's WhatsApp number (+91 95009 10005): status (approved, in
  review, rejected with Meta's reason, paused), category, language, quality, last 30 days sent / delivered / read /
  clicked. **New template**: name (small letters, numbers, _), Utility or Marketing, language, optional header (text,
  picture, PDF or video — upload a sample), message with {{1}}, {{2}}… and a sample for each, optional footer, buttons
  (quick reply, link, call, copy code — copy code is Marketing only), with a live preview. Meta's format rules are
  checked before sending (a variable can't be at the very start or end, two variables need words between them, every
  variable needs a sample, not too many variables for the length). Edit: approved, rejected or paused templates only
  (Meta: an approved one once a day, 10 times a month). Delete asks first; a deleted name can't be reused for 30 days.
  The six templates QTT OS itself sends can't be deleted: qtt_report, qtt_alert, qtt_payment_reminder,
  qtt_business_update (Utility), qtt_enquiry_received (Utility — the instant reply to a website enquiry) and
  qtt_lead_followup (Marketing — the day 1 / 3 / 7 follow-ups).
- **WhatsApp number** — QTT's number: quality (High / Medium / Low), display name and whether Meta approved it, how
  many new chats it may start a day (grows with good messages), connected, last 30 days' messages, this month's cost by
  category (empty until Meta bills), business profile. From here:
  - **Business profile › Edit**: about (shown under the name, up to 139), description, address, email, up to 2
    websites, business category, and the profile photo (square JPG or PNG, 192 × 192 or more, up to 5 MB).
  - **QR codes and links**: a QR picture and wa.me link that open a chat with a ready-made first message (up to 140
    characters); change the message any time — printed codes keep working; delete asks first.
  - **Broadcasts**: an approved Marketing template (no picture header) to everyone who agreed to get offers. **People
    who agreed**: paste "Name, number" lines (from Excel too), say how they agreed, tick that they agreed (Meta
    requires it); anyone who replied STOP is never added back. Values can use {name} for each person's first name.
    **Send** shows how many go today (the number's daily limit, or Managed Services Settings › Broadcast cap), the
    estimated cost and how many wait; **Send the rest** on a later day — nobody gets it twice; **Stop** halts sending.
    A reply of STOP takes someone off (when the receptionist is on for that number).
  - **Forms in the chat** (WhatsApp Flows): Lead, Booking or Order forms that open inside WhatsApp — title, intro,
    up to 20 questions (short / long answer, phone, email, number, date, pick one), button, thank-you. **Publish**
    (Meta checks it; Meta publishes forms only for a verified business — finish Meta business verification first),
    **Send to a customer** (someone who wrote in the last 24 hours), **Answers** (mark each done). Answers come
    straight to QTT OS; a business also sees them in its activity.
  - **Blocked numbers**: block or unblock; Meta only blocks someone who wrote in the last 24 hours.
  - **Cost by client**: each business's template messages from QTT's number this month (or another month) × Meta's
    rates (Desk › Managed Services Settings › WhatsApp costs — check Meta's rate card for India and update them),
    next to what it pays for AI & WhatsApp Automation, and the margin; smallest margin first. "QTT" = messages QTT
    sent for itself.
- **Marketing** — QTT's own marketing: content waiting for approval (approve / reject), articles, LinkedIn posts and
  their numbers.
- **Revenue** — monthly revenue, collected, past-due payments and trials ending.
- **App control** — what every QTT OS app shows and allows: maintenance, announcement, versions, defaults, languages,
  feature flags, analytics. A save reaches running apps at once.
- **Clients** (Managed Services) — everyone QTT runs managed services for: their services, websites / servers
  (health), requests (answer them), activity; assign a service.
- **Usage** — AI spend (DeepSeek, OpenAI), Hermes and n8n runs, from the automation server.

## Businesses' own WhatsApp (Managed Services › Your WhatsApp)
A business with AI & WhatsApp Automation whose own number is connected in its Onbox (WhatsApp Cloud API) gets the same
tools for its number (owner only): number health, profile and photo, QR codes, templates, broadcasts, forms, blocked
numbers. Its own messages are billed to its own Meta account, not QTT's. If the number isn't connected it says so.
