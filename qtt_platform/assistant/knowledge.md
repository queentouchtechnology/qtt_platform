# QTT OS — what the assistant knows

QTT OS is Queen Touch Technology's one app for running a small business: one
login, every product inside it, on Android, iOS, the web and computers. A
business (called a workspace) subscribes to the products it needs; each
person in it gets access to some products, with a role in each.

## The app itself (every user)
- **Apps (home)**: greeting, what needs you today (the "For you" cards), your
  apps, and one search box for everything.
- **Search**: finds customers, people, items and app screens. Understands
  typos, any word order, phone numbers, and everyday words ("salary" opens
  Office Pulse, "bill" opens Orbitra). Remembers recent searches.
- **Customers**: one customer list shared by all apps. Individual or business
  (GSTIN, billing address), tags and notes; call, WhatsApp or email them;
  archive instead of delete.
- **Business** (owner / admin): Profile (logo, address, GSTIN, phone, bank,
  UPI — printed on invoices, payslips, PDFs); Team (invite by email, choose
  each person's apps and role, remove); Plans (each app's plan and trial end).
- **Account**: switch between several accounts, appearance (light / dark,
  theme, text size, density), language (English, Tamil, Hindi, Arabic and
  more), tips on/off, help and support (WhatsApp or email QTT), fingerprint /
  Face ID sign-in, sign out.
- **Signing in**: email and password, Continue with Google, or fingerprint /
  Face ID on a phone that signed in before. Two-step verification is set by
  the business admin. New businesses verify their email and WhatsApp number
  with a one-time code when signing up.
- **Joining a business**: the owner invites you from Business › Team; you
  receive an email with an invitation code; on the sign-in screen tap
  "I have an invitation code" (or "Join with code" if you already have a QTT
  login).
- **Several businesses**: switch with the business name at the top of Home.

## Office Pulse — attendance, leave, expenses, payroll (HR)
Roles: **Employee** (own attendance, leave, expenses, payslips), **HR**
(everything except payroll), **HR Admin** (everything including payroll).
Anyone with people reporting to them is a **manager**: they see Team today and
approve their team's requests.
- **Check in / out** from the Office Pulse home. If offices are set, you must
  be within the office radius; if the business allows check-in away from the
  office, you add a reason and it is marked remote.
- **Work From Home / On Duty**: My attendance › "Request work from home / on
  duty" — choose dates, details; a manager or HR approves. It does not use
  leave.
- **Leave**: balances per leave type; Apply for leave (dates, half day,
  reason; holidays are not counted); withdraw open or future requests. HR
  gives yearly leave in Setup › leave types › Give leave.
- **Expenses**: New expense claim — one or more expenses (what for, amount,
  date, details) and receipt photos (up to 5 MB each); withdraw while pending.
- **Payslips**: appear after HR finalises payroll; download the PDF.
- **Approvals** (managers, HR): leave, WFH / on duty and expense requests;
  approve or reject with a note.
- **People** (HR): add employees, give app access (email invitation linked to
  the employee), mark attendance, set salary, mark as left.
- **Setup** (HR): ask for location at check-in; allow check-in away from the
  office; offices (stand at the office and save its location; radius);
  leave types (yearly limit, unpaid, carry over) and giving leave; holiday
  calendars (weekly off, holidays); shifts (start, end, late after minutes,
  automatic attendance from check-ins); departments and job titles.
- **Payroll** (HR Admin): 1) Salary templates with pay items (earnings and
  deductions; formulas like base * 0.4), 2) give a template to people with
  their monthly salary, 3) Run payroll for a month, check gross / deductions
  / net, then Finalise and publish payslips (employees then see them).

## Office Pulse — import and export employees (HR)
- **Import** (People › Import, or the "Bring your team in" card): download the
  template or use your own Excel / CSV (up to 1,000 rows, 5 MB). Columns are
  recognised by name — Name, DOJ, Phone, Designation, Reporting manager… —
  even misspelt; unclear ones are suggested by QTT Assistant; you can change
  any. Someone new needs name, gender and date of birth (day/month/year); no
  joining date = today. Rows are matched to people already here by Employee
  ID, email or mobile and updated (names change only when matched by ID).
  The preview shows New / Update / Problems with reasons and suggestions (new
  departments and job titles are created, people without mobiles, plan room).
  Rows with problems are skipped. Optionally invite new people with an email.
  Over 150 rows continue in the background with a notification. QTT can
  import a list for you (Send it to QTT on the import screen).
- **Export** (People › Export): Excel or CSV of working people (or including
  people who left); the same columns import reads, with Employee ID, so you
  can edit and import back.
- **Action cards on People**: import the team (small teams), "N people can get
  the app" → Invite all, "N people have no mobile number" / "no department" →
  download just them, fill in, import back.

## Office Pulse — biometric devices (ADMS)
- Fingerprint / face devices with ADMS ("Cloud server", "Push") — ZKTeco, eSSL
  and similar — send punches to Office Pulse by themselves. On the device:
  Menu › Comm › Cloud Server Setting → server adms.queentouchtech.in, port 80,
  Domain name on, HTTPS off, Proxy off; check its date, time and time zone.
- Setup › Biometric devices (HR): Add device by its serial number (Menu ›
  System info, or the label). A device no business has added is not accepted;
  its punches stay on it until it's added. Online = in touch in the last 5
  minutes. Optional: a site (punches count as at that site), In / out from the
  device or by the shift rules, a clock correction.
- Each person's user ID on the device is their Device PIN (People › the
  person, an import column "Device PIN" / "Biometric ID" / "Enroll ID", or
  Link people on the devices screen — names on the device are suggested). A
  PIN is unique within the business. Punches for a PIN nobody has yet wait
  and are saved as soon as it's linked. "Get missed punches" asks the device
  to send the last days again (duplicates are skipped).
- Device punches follow the same rules as app check-ins: late check-in
  approval, early exit / overtime, and they count for attendance and payroll.
- Home cards for HR: punches waiting for people; a device not in touch for a
  day. If a device only takes an IP address or can't find the setting, QTT
  sets it up (Help and support).
- Which devices work: eSSL / ZKTeco with Cloud server (ADMS) — yes; other
  brands with ADMS / Push (built on ZKTeco) — yes; face, fingerprint, card or
  PIN — all come in the same way; several devices per business — yes (one
  Device PIN per person on all of them). Device that only takes an IP address,
  or that only works with PC software (eTimeTrackLite, ZKTime) — QTT sets it
  up / switches it to Cloud server. USB / pen-drive only, or one device shared
  by two businesses — not supported.
- Troubleshooting: Offline → power, network, server adms.queentouchtech.in
  port 80 HTTPS off (Online within a minute). Someone's punches missing →
  their user ID on the device must be their Device PIN; waiting punches are
  under "PINs not linked to anyone" — link and they're saved. Wrong times →
  device date / time / time zone (India GMT +5:30), or a clock correction
  here. Everyone shows Check-in → In / out "By the shift rules". "Added to
  another business" → send QTT the serial number. Device used before Office
  Pulse → add it; it sends what it still holds; Get missed punches = last 7
  days, duplicates skipped. Someone left → mark as left and delete them on the
  device so the PIN can be reused.
- Attendance waits for an offline device (Attendance rules › "Wait for
  offline biometric devices before marking absent", 48 h by default), so its
  punches aren't missed. A punch or an approved correction that arrives for a
  day already marked automatically re-marks that day; leave, HR's own marks
  and days already in a submitted payslip are not changed (the payroll run
  flags them). The same punch is never saved twice, and pressing again within
  2 minutes counts as one punch.
- Payroll › a run › "Before you finalise": punches not in attendance yet,
  biometric punches waiting for a person, undecided requests, approved
  overtime not in a run, devices not in touch since the period ended, and
  punches that arrived after the slips were submitted.
- Where to find it: Setup › Biometric devices (device list, server address
  with copy buttons, add device, PINs not linked, a device's settings, Get
  missed punches, latest punches); People › the person › Edit › Device PIN;
  the import's Device PIN column; Approvals for late / early punches.

## Office Pulse — shifts and workforce features (HR sets up)
Every business sets its own rules. Each screen below has a "How to set up"
card with steps and suggestions for the business type.
- **Business type** (Setup › Business type): Office, Security / field
  service, Hospital / healthcare, Factory / manufacturing, Retail /
  restaurant, Other. Tap **Use** to switch on what that business usually
  needs and suggested rules; change anything later. Features (capabilities):
  Flexible cycles, Sites, Requests, Split shifts, Overtime pay, Coverage
  (with handover and on-call), Offline attendance. Presets: Office — none;
  Security — flexible cycles, sites, requests, overtime pay, coverage,
  offline; Hospital — flexible cycles, sites, requests, overtime pay,
  coverage; Factory — flexible cycles, requests, overtime pay, coverage;
  Retail — sites, requests, split shifts, overtime pay, coverage.
- **Shifts** (Setup › Shifts): start and end (an end before the start ends
  the next morning — night shifts work), late after minutes, a **break**
  (unpaid minutes after hours worked, or paid; a break they checked out for
  counts as taken), and with Split shifts the time off in the middle (e.g.
  11:00–22:00 off 15:00–18:00 — not counted as work, checking out for it is
  not an early exit). Two different shifts on one day, and flexi hours, are
  not supported.
- **Shift patterns** (Setup › Shift patterns): which shift on which day and
  where (office, from home, anywhere, or a site). Repeats every week, every 2–8
  weeks (rotation), or with Flexible cycles every N days (4 on / 4 off = 8
  days, 2-2-3 = 14, four crews = 28). Who: everyone, a department or chosen
  people (chosen people first, then department, then everyone). Save and
  apply gives shifts 60 days ahead in the background (a notification comes
  when done) and keeps topping up. A one-day change for a person is in People
  › the person › Shifts and survives pattern edits.
- **Attendance rules** (Setup › Attendance rules): late check-ins need
  approval (after N minutes; if not approved: half day, absent or late mark);
  check-out required with reminders and what happens without one; how many
  hours a forgotten check-out still counts (night shifts ~12); early exits and
  overtime need approval (Requests); offline check-ins accepted for N hours;
  morning coverage alert.
- **Requests** (My requests, when the business uses Requests): shift change
  (another shift, place or a day off), shift swap (same day or trading days;
  the colleague accepts first), early exit, overtime. Late check-ins and
  missed check-outs also appear there with who they wait for.
- **Approval flows** (Setup › Approval flows): per kind of request up to 5
  steps — manager, manager's manager, HR, HR Admin or a chosen person — each
  optionally only above an amount, days or minutes; "add HR after N hours"
  when a step waits. No steps: the manager or HR. A rejection ends it.
  Approvals cards show the leave balance left, and with Coverage a warning
  when approving would leave a shift short; filter pills by kind.
- **Overtime and on-call pay** (Payroll › Overtime and on-call pay, HR Admin,
  Overtime pay feature): hourly rate = monthly salary ÷ days ÷ hours (or a
  fixed rate) × multiplier (1.5, 2); counted in blocks (e.g. 15 min); on-call
  allowance per day. Approved overtime and on-call days are added to the next
  payroll run (shown before the slips are made), each paid once; only people
  with a salary set are paid.
- **Coverage** (Manage › Coverage, Coverage feature): rules — at least N
  people on a shift (at a site) on chosen days; gaps for the next 2 weeks;
  HR gets gaps for the next 3 days at 7 am; approvers are warned. **Handover
  notes**: "Leave a handover note" on the check-in card; the next shift (same
  site, else the business) sees it on their card. **On call** (Manage › On
  call): add a person for some days or a rotation (people in order, days
  each, times round); "on call now" shows on Team today and their card.
- **Offline attendance** (Offline feature): with no network, Check in /
  out is saved on the phone (shown "on phone") and sent when back online or
  with "Send now". Wrong phone clocks are corrected; future or too-old
  punches (default 72 h) are refused; a punch is never saved twice.
- On the check-in card: today's shift (both parts of a split shift), the
  break rule, time worked, on-call, handover notes.

## Orbitra — billing, POS, stock, GST (shops and small businesses)
Roles: **Cashier** (POS, sales, customers; sees stock), **Manager** (adds
purchases, inventory editing, reports), **Orbitra Admin** (everything,
including accounts and settings). Purchases, Accounts and Reports also need a
plan that includes them.
- **POS**: tap items (search, code or barcode), choose a customer or walk-in,
  take payment by cash, UPI or card or split two ways; change is calculated;
  any unpaid part stays on the customer; save the bill PDF.
- **Sales**: invoices (unpaid first) and quotes; new invoice or quote;
  receive payment; save / share PDF; take back items (credit note, stock
  returns); turn a quote into an invoice.
- **Inventory**: items and services with selling price, cost, GST rate,
  HSN/SAC, barcode, category, low-stock alert level; add stock, count stock,
  move stock between stores; hide an item from POS and new bills.
- **Purchases**: supplier bills bring stock in and track what you owe; pay a
  supplier; manage suppliers.
- **Customers** (in Orbitra): what each customer owes and bought; new invoice
  or receive payment from there.
- **Accounts**: money in and out; record shop expenses; move money between
  cash and bank; who owes you / whom you owe.
- **Reports**: for a period — sales by day, best sellers and customers, GST
  (collected minus paid on purchases), profit, stock value.
- **Settings** (admin): prices include GST or not, main store, invoice note.
  Business details on invoices come from Business › Profile.

## Onbox — every customer conversation in one inbox
Roles: **Agent** (answers chats assigned to them or their channels),
**Supervisor** and **Manager** (see every channel; managers also manage
settings).
- Channels: WhatsApp Business (Meta Cloud API), website chat (paste a code on
  your website), Facebook, Instagram and email (forwarding or mailbox).
- Conversations: Mine / Unassigned / All; filter by status (open, pending,
  snoozed, resolved) and channel; reply or add a private note; attach files
  (up to 16 MB); assign to a person or team; snooze; labels; priority;
  resolve / reopen; save the contact as a customer.
- WhatsApp rule: free-form replies only within 24 hours of the customer's last
  message; after that you can only add private notes (or send an approved
  template from QTT's automations).
- Channel access (managers): choose which team members answer each channel.

## Managed Services — QTT runs it for you
QTT builds and looks after websites, WhatsApp replies, daily reports,
reminders, automations, servers and more. The business owner orders; others
see status.
- Home: status of each website / system (up or down, checked every few
  minutes), your services, previews to review, activity.
- Ordering: pick a service; websites let you choose a design and colours for
  your kind of business, hosting, and a website address (search a new domain
  or use your own). Free services start at once; paid ones start when paid.
- Preview → Approve and go live: review the preview, ask for changes or
  approve; then connect your domain (3 DNS steps shown in the app; it goes
  live on its own once connected). The preview has an expiry date.
- Requests: ask QTT for a change or help; mark urgent if something is broken.
- Payments: invoices; pay by UPI, card or net banking.
- Stopping a service: from the service, "Stop this service" (keeps running
  until the end of the paid period; "Keep this service" undoes it).
- Paying by term: some services can be paid monthly, yearly or for 3 years
  ("How would you like to pay?" when ordering); longer terms save money and
  show the saving. Each term is paid in advance and renews at its end (for a
  year or more, the invoice comes 15 days early).

## Managed Services — online store (Managed E-Commerce Websites)
QTT creates, hosts, secures and manages a full online store (WooCommerce) for
the business, and the owner runs it from the app — there is no website login
to remember or share.
- Ordering: Managed Services › Explore › Managed E-Commerce Websites. Answer
  a few questions (business name, what you sell, how many products, how
  customers pay, where you deliver, a phone number), choose monthly, yearly
  or 3 years, pay the setup fee and the first term. Prices are in the app.
- Setting up takes a few minutes and shows step by step: creating the store,
  WordPress and WooCommerce, the design for what you sell, sample products
  with photos, connecting it to the app, security (https). Then "ready for
  your review" with a preview link (…preview.queentouchtech.in).
- Designs: ready designs for fashion, grocery, electronics, jewellery, beauty,
  furniture, sweets and bakery, and general stores. The design can be switched
  later; your name, logo, contact details and products stay.
- Sample products are there so the store doesn't look empty — edit them or
  delete them and add your own.
- Going live: approve the preview, then connect your website address (the app
  shows the DNS steps). Once the address points here the store moves onto it
  by itself (usually within 10 minutes), with https, and opens to Google.
- Running it — on the website's page in Managed Services tap "Run your store":
  - Store home: today's orders, orders to pack and send, new enquiries,
    products running low or sold out, plugin updates waiting.
  - Orders: search; tabs To send / Unpaid / Delivered; the order with items,
    address, payment; call or WhatsApp the customer; Mark delivered, Paid —
    ready to send, Cancel order (the customer is emailed; stock goes back);
    Add a note (optionally emailed to the customer, e.g. a tracking number).
  - Products: add or edit with photos from the phone (square, plain
    background looks best; the first photo is the main one), price, offer
    price, stock, categories, Show in the shop (off = hidden while you get it
    ready), Featured; quick stock change from the list. Products with sizes or
    colours: QTT sets their prices and stock for now — ask through Requests.
  - Design: colours, fonts, logo, menus, banners and slides, every page and
    its sections (switch a section off to hide it, drag to reorder, add or
    remove), header, footer, pop-ups, shop options. Changes show on the
    website as soon as you save.
  - Enquiries: messages from the website's forms (enquiry, contact,
    newsletter) — call, WhatsApp or email back.
  - Offers and coupons: discount codes (% off or ₹ off, minimum order, end
    date, how many uses, free delivery).
  - Marketing and tools: Google Analytics, Meta (Facebook) pixel, Google Search
    Console and Tag Manager codes (purchases are tracked automatically); add
    approved plugins (SEO, Facebook & Instagram shopping, Google Shopping,
    Mailchimp, Razorpay, GST invoices) and switch them on or off; plugin
    updates.
  - Store settings: name, tagline, Show on Google.
  Only the business owner can change things; others in the business can look.
- What the store has: search that suggests products as you type, filters
  (price, colour, size, in stock, on sale), colour and size buttons, quick
  view, wishlist, compare, "Only a few left", Buy now, Order on WhatsApp, a
  free-delivery progress bar, a WhatsApp chat button, offers with countdown,
  newsletter pop-up, a bottom bar on phones, catalogue-only mode (customers
  enquire instead of buying).
- New orders, cancelled or failed payments, products running low or sold out,
  and new enquiries appear in Managed Services activity.
- A store on another theme that QTT took over (e.g. Porto): orders, products,
  enquiries, coupons, marketing and plugins work the same; the design page
  changes the logo, colours, fonts, top-of-page announcement, social links and
  share buttons; page layouts, sliders and banners are changed by QTT.
- Problems or bigger changes: Managed Services › Requests.

## Plans and trials
Each app has its own plans (there are no bundles); a new business starts on a
free trial. Live plan names, prices and limits are given to you separately —
use only those. To upgrade or change a plan, the owner contacts Queen Touch
Technology (Business › Plans says this too).

## Help
- In the app: Account › Help and support (WhatsApp or email QTT).
- Questions in search ending with "?" open this assistant.

## What the assistant never discusses
Only QTT OS customer software and services above. Never: Queen Touch
Technology's own marketing system or campaigns, internal tools or
automations, servers, staff, other businesses or their data, pricing not in
the live plan list, or anything outside QTT OS. Never asks for or reveals
passwords, codes or keys.
