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
  Website Development also has **add-ons** (marked Add-on; owners pick any of them with one size): Business email,
  Google Business profile, Care plan, 3 more pages, Move my existing website — priced and switched on/off here too.
- **Automation library** — the automations businesses choose from (name, what it does, when it runs, group, default
  time, order, shown or hidden) and how many businesses use each.
- **Studio** — QTT Studio's post template library and its use. **Templates**: every design's picture, how many
  times businesses used it, the nightly check (each enabled template drawn in square, portrait and story on the
  renderer; a problem — didn't draw, blank, wrong size — shows with what was wrong, and on QTT Admin's home as
  "Studio templates didn't draw right"), on / off (an off template isn't offered; designs made from it stay), **Check
  now**, "Only the ones with a problem". **Use and cost**: a month at a time — by business: designs by kind, AI
  credits used, what QTT paid the AI providers; by AI job (make, ask, letter, short script, AI background, AI logo,
  reading a poster); failed AI jobs.
- **Marketing assistant** — the clients' Marketing assistant (not QTT's own marketing, which is **Marketing**).
  **Library**: post designs on / with a problem (managed in Studio), ready ideas by kind of business, and festivals —
  tap a festival that moves each year to set this year's date, switch one off to stop its wishes; ones that need a date
  come first (and show on QTT Admin's home as "N festivals need this year's date"). **Queue**: the design renderer and
  the cut-out service (up / down, how fast — "down" also shows on the home), problems this week (series that failed,
  posts / articles / newsletters not sent, with why), series due and posts going out in the next 24 hours, **Run due
  series now** (they run every hour anyway). **Usage**: a month at a time — each business with its package and posts /
  articles / newsletters / series against the limits; those near a limit (80%) come first with a warning sign.
- **Website designs** — what owners choose from before a website is built (Website Development): six designs (theme
  styles: Classic, Modern, Bold, Elegant, Minimal, Warm) and colour palettes. Rename them, change their one line and
  order, show or hide them. Each design shows how many screenshots are up to date (one per business type × computer /
  phone, taken every 15 minutes by the automation server's worker); **Retake** one design or all. The demo site
  (design-demo.preview.queentouchtech.in) draws any design live; **Update demo** puts the latest theme on it (Frappe
  runs the setup script on CloudPanel). The theme itself defines the designs — a new design is a theme change.
  Each website business type has AI-made pictures (two banners and an About picture, OpenAI gpt-image-1, made with
  qtt_services/tools/site_images.py — kit-images/<business>/, no recognisable faces); a new website gets its type's
  pictures in its media library. A website's words are written by AI from the owner's answers and checked by the owner
  before ordering; reviews, numbers and team start empty, and invented years / ratings / "No. 1" claims are dropped.
  The same designs and colours are offered for online stores (PROJ-0010): the store types (fashion, grocery, electronics,
  jewellery, cosmetics, furniture, sweets, general store) get their own screenshots, and the demo site has WooCommerce with
  every store type's sample products (tagged qtt-demo-<type>; Refresh demo site adds them); nothing can be bought there.
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

## Websites waiting for their domain
After the owner approves, the domain is checked every 30 minutes for a week, then twice a day (fresh DNS over HTTPS; who
runs the DNS from the nameservers, who registered it from RDAP). The owner sees their DNS provider's own steps and plain
words for what's wrong, and is reminded on days 1, 3 and 7 (app + WhatsApp). From day 3 the site is in Needs attention
("not connected for N days"); on day 7 a task "Call <business>: connect <domain> to their new website" appears with the
phone, the provider and the problems. Parked / for-sale addresses (e.g. atom.com, Sedo, Afternic) are flagged — the owner
may not own the domain.

## Builds (QTT Admin › Builds)
Website and online store builds, go-lives, deletions and domain purchases. Each product moves from n8n to Frappe with a
switch in Desk › Managed Services Settings › Builds run by Frappe (Websites, Online stores, Buying domains; off = n8n as
before — switching off is the rollback). When Frappe runs them: at most 2 at once (Builds at once), never two runs on the
same website, a connection problem is tried again after 10, 30 and 60 minutes, a run longer than 30 minutes is stopped and
retried the same way, and a step that fails on the server isn't retried by itself. When there are no tries left a task
"Build failed: <website> (<kind>)" appears and Needs attention shows it. Open Builds, tap it to see the steps and the
log (the server's output; passwords never in it), then **Retry** (same site — it carries on from what's already there)
or **Cancel it** (a cancelled go-live isn't started again until Retry). Domains: bought from QTT's Hostinger account with
the payment method set in Settings; QTT's cost each month is limited (Domains bought automatically a month, ₹5,000) —
above it a task "Approve buying <domain>" appears and Builds shows **Approve**. A domain already in QTT's Hostinger
account is never bought twice. A go-live tries the security certificate up to 4 times; if it still
doesn't install, the site is live without https and a task "Secure <domain> (https)" appears (CloudPanel › Sites › the
site › SSL/TLS › New Let's Encrypt Certificate). Deleting a website cancels its cache task.

## Online store add-ons: staff tasks
Managed E-Commerce add-ons (marked Add-on in Services and pricing; owners pick any with one plan): Payment gateway setup,
We add your products, Google Shopping, Business email, Google Business profile, Delivery partner setup, Move my existing
store, Care plan. When the store starts, each one done by hand gets a task with its steps: "Set up online payments for
<business>'s store" (their own merchant account and keys; test order and refund), "Add the first products to <business>'s
store" (up to 50 from their list; remove the samples), "Put <business>'s products on Google Shopping" (Merchant Center on
the owner's Google account, Google Listings & Ads), "Connect a delivery partner for <business>" (the owner's Shiprocket
account, one test shipment), "Move <business>'s old store into the new one" (their old store's address), plus business
email and Google profile as for websites. With Payment gateway setup chosen, the separate "Connect <service> payments"
task isn't made. Care plan: owners ask for changes through Requests.

## Online stores: payments set up from the order
A store build sets cash on delivery, delivery (charge, free above, collect from the shop) and the four policy pages from
the owner's answers (store_setup_rules.py). The chosen payment service is installed and left off: Razorpay the owner
connects in the app (store › Payments and delivery, their own keys); for Cashfree, PhonePe or PayU a task "Connect
<service> payments for <business>" appears — help the owner open their own merchant account, activate the plugin, enter
their keys in WooCommerce › Settings › Payments, place and refund a small test order.

## Website add-ons: staff tasks
When a website service starts (paid, or added by QTT), each add-on done by hand gets a task with its steps: "Set up
business email for <business>" (the mailbox names the owner gave), "Create the Google Business profile for <business>"
(with the owner's own Google account, never QTT's; then paste the link into the service's answers), "Add the extra pages
to <business>'s website" (the site already allows 3 more pages) and "Move <business>'s old website into the new one".
Care plan needs no task — owners ask for changes through Requests. An owner who already has a Google profile pastes its
link when ordering; the website links it for Google automatically.

## Live websites: switch the cache on
When a website QTT built goes live, a task "Switch on the cache for <domain>" appears (and the site shows in Needs
attention): CloudPanel → Sites → the site → Varnish Cache → switch on, keep the excluded pages, Save. A daily check sees
the site answering from the cache and closes the task by itself. The theme clears the cache whenever the owner changes the
site from the app.

## Businesses' own WhatsApp (Managed Services › Your WhatsApp)
A business with AI & WhatsApp Automation whose own number is connected in its Onbox (WhatsApp Cloud API) gets the same
tools for its number (owner only): number health, profile and photo, QR codes, templates, broadcasts, forms, blocked
numbers. Its own messages are billed to its own Meta account, not QTT's. If the number isn't connected it says so.

## Design base and renderer (PROJ-0011 B)

- Post pictures are designs (HTML, CSS and SVG in the business's own palette, fonts and logo), turned into PNGs by
  headless Chromium (Gotenberg) on the automation server, behind Caddy at `/render/` with a password. Settings:
  Desk › QTT App Settings › **Design renderer** (address, user, password — the password is never shown). No AI images;
  OpenAI images only for a paid custom poster.
- The design base (qtt_platform/design): the palette (the owner's colours kept, missing ones derived, readable text by
  contrast), ~40 patterns, ~60 elements (brush strokes, badges, price tags, icon tiles, device frames, QR codes made
  locally, date blocks, cloud bubbles…), photo frames, text effects (gold, 3D), Google fonts incl. Tamil / Hindi /
  Arabic, business types (a Technology group), photo backgrounds from the website / store kits.
- Reference posts the library follows: docs/design/tech-post-references.md, local-post-references.md,
  agency-post-references.md (in qtt-os).
- If "See your brand" or post pictures fail: check the renderer (Desk error log "Design renderer: …"), then the
  gotenberg container on the automation server (`docker ps` in /opt/qtt-auto).

## Festival dates for the content library (PROJ-0011 C2)

- QTT Admin › Marketing assistant › Library (or Desk › **QTT Occasion**): the days businesses get wishes for. Fixed days
  (New Year, Republic Day, Women's Day, Tamil New Year, May Day, Independence Day, Teachers' Day, Children's Day,
  Christmas) roll to next year by themselves (checked daily). Festivals
  that move (Pongal, Ramzan, Bakrid, Onam, Vinayagar Chathurthi, Ayudha Puja, Deepavali, Karthigai Deepam) need **this
  year's date set by staff** — without a date their wishes aren't offered (they show 30 days before). Untick "Offer
  wishes for it" to stop one.
- The ready-written words themselves live in qtt_platform/design/content.py (English + Tamil), filled from each
  business's knowledge; an idea is only offered when every fact it needs is there.

## Team chat (support notes, PROJ-0013 / 0014)
- Every business's Team is a private Raven workspace named `qtt-<tenant>` (Desk › Raven Workspace); QTT's own
  Raven workspace ("Raven") is separate and unchanged. Customers never get the Raven User role (it would open Desk) —
  all their access goes through qtt_platform.api.team / team_extras, which check the business and membership.
- #general holds every active member and follows Business › Team (added / suspended / removed). A person "missing"
  from Team is almost always not active in the business.
- Phone notifications need the person's device registered (QTT Push Device) and no Do not disturb (Desk › QTT Team
  Profile shows status and Do not disturb until). Muted chats only notify for @mentions.
- Reminders on saved messages run every 5 minutes (QTT Team Saved). Tasks are Frappe ToDos linked to the message.
- Catch me up / Fill with AI take 1 credit each from the business's fullest AI wallet; QTT's own business doesn't pay.

## Calls and the Office Pulse Workplace (PROJ-0015)
- Servers: LiveKit (calls, meet.queentouchtech.in), OnlyOffice (office.queentouchtech.in) and RustDesk
  (remote.queentouchtech.in) run in /opt/qtt-workplace on the QTT-AI-OS server (31.220.83.224), behind its Caddy,
  with Garage (S3 file storage for Files). Keys: Desk › QTT Workplace Settings (secrets never shown).
- Calls: free for every business; screen sharing / remote control / Files need the person's Office Pulse access.
  A call's room is the chat id; LiveKit's webhook (team_calls.webhook) tracks who's in and writes the summary line.
- Files (since 2026-10-20, no Nextcloud): one private bucket qtt-files in Garage (/opt/qtt-workplace/garage, 4 MB of
  memory), reached only by Frappe through Caddy office.queentouchtech.in:9443 (Frappe's IP only — Docker ports skip
  ufw, so the check is in Caddy). Keys per business: <tenant>/team/, /company/, /hr/, /people/<person id>/; an
  employee's HR folder is a QTT HR Folder record. Frappe checks every permission and the quotas (Workplace Settings).
  Deleted or replaced files: trash/<day>/<key> for 30 days (file_store.purge_trash, daily) — to restore, copy the
  object back. Code: file_store.py, api/workplace.py.
- Documents: OnlyOffice talked to directly (api/workplace_docs.py) — open_doc makes an editor page link (a few hours,
  one person); OnlyOffice fetches the file through a signed Frappe link and saves through a signed call. Its JWT
  header is AuthorizationJwt (Frappe takes "Authorization" as a login and refuses it).
- OnlyOffice Community: its logo shows and 20 editors at once across all businesses; a paid licence lifts both.
- Remote control: the standard RustDesk app pointed at our server (Copy server settings in the app). Company
  computers: QTT Remote Device (permanent passwords encrypted).
- Uploads: the site's max_file_size is 110 MB (site_config.json, set 2026-10-21) so Files' own 100 MB check decides;
  Team chat keeps its 25 MB check in code. Frappe's default (25 MB) would refuse Files uploads over 25 MB.
- Nextcloud (cloud.queentouchtech.in, n8n server) is QTT's own team cloud only — QTT OS no longer uses it (its QTT OS
  folders and users were removed 2026-10-20; backup /root/qtt-os-nextcloud-backup-20261020.tgz on that server).
- Verified 2026-10-21: 32 API authorization checks, permission / quota checks, OnlyOffice JWT both ways,
  LiveKit load (6 publishers × 24 viewers: 144/144 streams, 0.03 % loss, ~1.5 of 4 cores), 10 conversions at once,
  crash recovery (restart: unless-stopped; docker on boot).

- Remote control hardening (2026-10-21; full write-up: qtt-os/docs/remote-access-security.md): company computers set up
  with the QTT agent (api/workplace_agent.py, scripts in qtt_platform/workplace_agent/) get a QTT-made password nobody
  sees, rotated automatically on revocation (team_events.on_membership / on_pulse_access); removal locks them. Audit:
  Desk › QTT Remote Access Log. RustDesk web-client ports 21118/21119 are closed (not used).
- Rotating the RustDesk server key (only if it leaks): stop hbbs/hbbr, move /opt/qtt-workplace/rustdesk/id_ed25519*
  aside, start them (new key), update Desk › QTT Workplace Settings › RustDesk public key; agents pick the new server
  settings on their next check-in; computers added by hand and helpers' RustDesk apps need the new settings again.
