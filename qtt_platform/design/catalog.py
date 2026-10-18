"""
The template library (PROJ-0011 C) — pure data: every template is a layout (archetypes.py) + a variant (look, pattern,
frame, fonts…), tagged by post type and business group, with a showcase palette for its thumbnail and sample words for
its trade. A business always sees and posts it in its own brand (logo, colours, fonts); the showcase palette is only
the library picture. Synced into QTT Post Template on migrate (library.sync), where QTT Admin can switch any off.

Sample words are examples for the thumbnail only — a real post's words, prices and dates come from the business.
"""

import hashlib
import json

from qtt_platform.design import business_types

POST_TYPES = {
	"offer": "Offer or sale", "product": "Product", "service": "Service", "event": "Event", "greeting": "Festival and wishes",
	"tribute": "Tribute", "listing": "Listing (property, vehicle)", "problem": "Problem and solution", "tip": "Tip or quote",
	"announcement": "Announcement", "course": "Course or admission", "launch": "Launch or new", "hiring": "We're hiring",
	"contact": "Contact us",
}
FORMATS = ("square", "portrait", "story")

PALETTES = {  # showcase colours for the library pictures (never a business's own)
	"blue": {"primary": "#2563eb", "accent": "#0ea5e9", "dark": "#0b1220"},
	"indigo": {"primary": "#4f46e5", "accent": "#f59e0b", "dark": "#111132"},
	"teal": {"primary": "#0d9488", "accent": "#f59e0b", "dark": "#0b1f1e"},
	"green": {"primary": "#15803d", "accent": "#facc15", "dark": "#0f1f14"},
	"lime": {"primary": "#84cc16", "secondary": "#16a34a", "accent": "#16a34a", "dark": "#1a2410"},
	"red": {"primary": "#b91c1c", "accent": "#f59e0b", "dark": "#1a0808"},
	"maroon": {"primary": "#7f1d1d", "accent": "#eab308", "dark": "#14080a"},
	"purple": {"primary": "#7c3aed", "accent": "#facc15", "dark": "#1d1230"},
	"pink": {"primary": "#db2777", "accent": "#facc15", "secondary": "#16a34a", "dark": "#1e2a5a"},
	"navy": {"primary": "#1e3a8a", "accent": "#facc15", "dark": "#0f172a"},
	"amber": {"primary": "#f59e0b", "accent": "#f59e0b", "dark": "#1f2937"},
	"orange": {"primary": "#ea580c", "accent": "#facc15", "dark": "#1c1009"},
	"black_gold": {"primary": "#a16207", "accent": "#eab308", "dark": "#0a0a0a"},
	"slate": {"primary": "#334155", "accent": "#94a3b8", "dark": "#0f172a"},
}
FONT_SETS = {"modern": ("Montserrat", "Inter"), "friendly": ("Poppins", "Inter"), "rounded": ("Baloo 2", "Nunito"),
			 "elegant": ("Playfair Display", "Lato"), "bold": ("Archivo Black", "Archivo"), "classic": ("DM Serif Display", "DM Sans")}

# What each layout is for: post types, business groups ("any" = every business), the looks it has.
LAYOUTS = {
	"hero_split": {"label": "Benefits with a device", "post_types": ["service", "launch", "announcement", "course"], "groups": ["technology", "services", "industry"]},
	"center_hero": {"label": "Big title, photo in the middle", "post_types": ["product", "offer"], "groups": ["food", "shops", "beauty"]},
	"listing": {"label": "Listing with specs and price", "post_types": ["listing", "product"], "groups": ["places", "shops"]},
	"event": {"label": "Event poster", "post_types": ["event", "course"], "groups": ["other", "places", "industry", "services"]},
	"tribute": {"label": "Tribute", "post_types": ["tribute"], "groups": ["any"]},
	"quote_tip": {"label": "Tip or quote", "post_types": ["tip", "announcement", "hiring", "greeting"], "groups": ["any"]},
	"problem_solution": {"label": "Problem and solution", "post_types": ["problem", "service"], "groups": ["technology", "services", "industry"]},
	"circles_labels": {"label": "What we teach / offer", "post_types": ["course", "service"], "groups": ["industry", "beauty", "services"]},
	"question_rows": {"label": "Questions to your customer", "post_types": ["problem", "course"], "groups": ["industry", "beauty", "services"]},
	"greeting": {"label": "Festival wishes", "post_types": ["greeting"], "groups": ["any"]},
	"curve_photo": {"label": "Expert with a photo", "post_types": ["service", "contact", "hiring"], "groups": ["services", "technology", "beauty"]},
	"wave_agency": {"label": "Agency with topics", "post_types": ["service", "course"], "groups": ["technology", "services", "industry"]},
	"sale": {"label": "Big sale", "post_types": ["offer"], "groups": ["shops", "beauty", "food"]},
	"numbered_services": {"label": "What we do, numbered", "post_types": ["service", "contact"], "groups": ["technology", "services", "beauty"]},
	"gallery": {"label": "Gallery and services", "post_types": ["service", "product"], "groups": ["services", "beauty", "places"]},
	"product_promo": {"label": "Product promo", "post_types": ["product", "offer"], "groups": ["food", "shops"]},
}

# The templates: (layout, name, variant, palette, fonts, look). Each becomes one library entry.
_T = [
	# technology / services — QTT's own style
	("hero_split", "Blue sweep", {"pattern": "sweep", "hero": "device", "band": "pillars"}, "blue", "modern", "light"),
	("hero_split", "Night glow", {"pattern": "glow_rings", "hero": "device", "band": "pillars"}, "blue", "modern", "dark"),
	("hero_split", "Circuit", {"pattern": "circuit", "hero": "device", "band": "contact"}, "indigo", "modern", "dark"),
	("hero_split", "Photo card", {"pattern": "dot_corners", "hero": "photo", "frame": "rounded", "band": "contact"}, "teal", "friendly", "light"),
	("hero_split", "Arch photo", {"pattern": "corner_arcs", "hero": "photo", "frame": "arch", "band": "pillars"}, "purple", "friendly", "light"),
	("hero_split", "Brand block", {"pattern": "grid", "hero": "photo", "frame": "rounded", "band": "contact"}, "navy", "bold", "brand"),
	("problem_solution", "Hidden cost", {"warn": "#dc2626"}, "blue", "modern", "dark"),
	("problem_solution", "Pain points", {"warn": "#ea580c"}, "teal", "friendly", "dark"),
	("problem_solution", "Fix it", {"warn": "#dc2626"}, "indigo", "bold", "dark"),
	("wave_agency", "Navy wave", {}, "navy", "modern", "light"),
	("wave_agency", "Purple wave", {}, "purple", "friendly", "light"),
	("wave_agency", "Teal wave", {}, "teal", "modern", "light"),
	("numbered_services", "Purple pop", {}, "purple", "friendly", "brand"),
	("numbered_services", "Orange pop", {}, "orange", "friendly", "brand"),
	("numbered_services", "Blue pop", {}, "blue", "bold", "brand"),
	("curve_photo", "Lime curve", {}, "lime", "friendly", "light"),
	("curve_photo", "Blue curve", {}, "blue", "modern", "light"),
	("curve_photo", "Pink curve", {}, "pink", "friendly", "light"),
	("curve_photo", "Amber curve", {}, "amber", "elegant", "light"),
	# food / shops / beauty
	("center_hero", "Fresh green", {"pattern": "spotlight", "frame": "circle", "script": "Kaushan Script"}, "green", "friendly", "brand"),
	("center_hero", "Warm orange", {"pattern": "spotlight", "frame": "circle", "script": "Pacifico"}, "orange", "rounded", "brand"),
	("center_hero", "Berry", {"pattern": "bubbles", "frame": "blob", "script": "Dancing Script", "rays": False}, "pink", "rounded", "brand"),
	("center_hero", "Night menu", {"pattern": "chalkboard", "frame": "rounded", "script": "Kaushan Script", "rays": False}, "amber", "friendly", "dark"),
	("center_hero", "Soft cream", {"pattern": "corner_blobs", "frame": "arch", "script": "Satisfy", "rays": False}, "red", "elegant", "light"),
	("center_hero", "Royal", {"pattern": "sunburst", "frame": "circle", "script": "Great Vibes"}, "purple", "elegant", "brand"),
	("product_promo", "Chalkboard", {}, "amber", "friendly", "dark"),
	("product_promo", "Chilli", {}, "red", "bold", "dark"),
	("product_promo", "Lime", {}, "lime", "friendly", "dark"),
	("product_promo", "Golden", {}, "black_gold", "elegant", "dark"),
	("sale", "Sunny shards", {}, "amber", "modern", "light"),
	("sale", "Berry shards", {}, "pink", "modern", "light"),
	("sale", "Bold red", {}, "red", "bold", "light"),
	("sale", "Teal", {}, "teal", "modern", "light"),
	("listing", "Navy and yellow", {"swipe": "#dc2626"}, "navy", "modern", "light"),
	("listing", "Green homes", {"swipe": "#ea580c"}, "green", "friendly", "light"),
	("listing", "Maroon", {"swipe": "#1e3a8a"}, "maroon", "modern", "light"),
	("listing", "Teal", {"swipe": "#dc2626"}, "teal", "friendly", "light"),
	("gallery", "Amber diamonds", {"frame": "diamond"}, "amber", "modern", "dark"),
	("gallery", "Pink diamonds", {"frame": "diamond"}, "pink", "elegant", "dark"),
	("gallery", "Tilted cards", {"frame": "tilted"}, "teal", "modern", "dark"),
	("gallery", "Gold frames", {"frame": "rounded"}, "black_gold", "elegant", "dark"),
	# education / coaching / clinics
	("circles_labels", "Bright classes", {}, "pink", "rounded", "light"),
	("circles_labels", "Calm blue", {"colours": ["#2563eb", "#0ea5e9", "#16a34a", "#7c3aed"]}, "blue", "rounded", "light"),
	("circles_labels", "Sunny", {"colours": ["#ea580c", "#facc15", "#16a34a", "#0ea5e9"]}, "orange", "friendly", "light"),
	("question_rows", "Is your child", {}, "pink", "rounded", "light"),
	("question_rows", "Health check", {"colours": ["#0d9488", "#0ea5e9", "#16a34a", "#7c3aed"]}, "teal", "friendly", "light"),
	("question_rows", "Do you struggle", {"colours": ["#2563eb", "#f59e0b", "#16a34a", "#db2777"]}, "blue", "rounded", "light"),
	# events, worship, wishes, tributes, tips
	("event", "Stage gold", {"title_style": "gold", "title_face": "Bebas Neue"}, "maroon", "modern", "dark"),
	("event", "Royal blue", {"title_style": "gold", "title_face": "Cinzel"}, "navy", "elegant", "dark"),
	("event", "Bright seminar", {"title_style": "gradient", "title_face": "Anton", "pattern": "stage_glow"}, "purple", "bold", "dark"),
	("event", "Night teal", {"title_style": "gold", "title_face": "Bebas Neue"}, "teal", "modern", "dark"),
	("greeting", "Festive red", {"deco": "stars"}, "red", "friendly", "brand"),
	("greeting", "Rangoli", {"deco": "kolam", "title_face": "Lilita One"}, "orange", "rounded", "brand"),
	("greeting", "Royal purple", {"deco": "mandala", "title_style": "gold"}, "purple", "elegant", "brand"),
	("greeting", "Green blessing", {"deco": "leaves", "title_style": "gold", "title_face": "Cinzel"}, "green", "elegant", "brand"),
	("greeting", "Midnight", {"deco": "stars", "pattern": "rays"}, "navy", "friendly", "brand"),
	("tribute", "Black and white", {}, "slate", "elegant", "dark"),
	("tribute", "Gentle", {}, "black_gold", "classic", "dark"),
	("quote_tip", "Soft circles", {"pattern": "corner_circles"}, "purple", "friendly", "light"),
	("quote_tip", "Grid note", {"pattern": "grid"}, "blue", "modern", "light"),
	("quote_tip", "Bold block", {"pattern": "dots"}, "teal", "bold", "brand"),
	("quote_tip", "Night thought", {"pattern": "rings"}, "indigo", "elegant", "dark"),
	("quote_tip", "Warm waves", {"pattern": "waves"}, "orange", "rounded", "light"),
	("quote_tip", "Frame", {"pattern": "frame_lines", "quote_mark": False}, "black_gold", "classic", "dark"),
]

# ---- sample words for the library pictures (by layout and business group) ------------------------------------------
_TECH = {"business": "Queen Touch Technology", "kicker": "Website backup", "headline": "Never lose your *website* again",
		 "subline": "Automatic daily backups. One-tap restore. Peace of mind.",
		 "items": [{"icon": "icon_sync", "title": "Daily automatic backups", "text": "Every night, nothing to remember"},
				   {"icon": "icon_shield", "title": "Safe off-site copies", "text": "Kept away from your server"},
				   {"icon": "icon_cloud", "title": "Restore in minutes", "text": "Back online fast"},
				   {"icon": "icon_team", "title": "Real support", "text": "A person when you need one"}],
		 "pillars": [["icon_rocket", "Innovate"], ["icon_gear", "Automate"], ["icon_chart", "Analyze"], ["icon_shield", "Protect"]],
		 "tagline": "Technology today.\n*Success tomorrow.*", "phone": "95669 66764", "website": "queentouchtech.com"}
SAMPLES = {
	"hero_split": {"any": _TECH, "services": {**_TECH, "business": "Arun & Co. Chartered Accountants", "kicker": "GST filing",
											   "headline": "File your *GST* on time, every time",
											   "subline": "Monthly returns, reminders and clear reports.",
											   "items": [{"icon": "icon_calendar", "title": "Never miss a due date", "text": "We remind you early"},
														 {"icon": "icon_check", "title": "Accurate returns", "text": "Checked by a CA"},
														 {"icon": "icon_chart", "title": "Simple reports", "text": "Know where you stand"}],
											   "pillars": [["icon_check", "Accurate"], ["icon_clock", "On time"], ["icon_shield", "Safe"], ["icon_team", "Personal"]],
											   "tagline": "Your numbers,\n*our care.*", "website": "arunco.in"},
				   "industry": {**_TECH, "business": "Sri Balaji Industries", "kicker": "Precision machining", "headline": "Parts made *to your drawing*",
								"subline": "CNC turning and milling, small and large batches.",
								"items": [{"icon": "icon_gear", "title": "CNC turning & milling", "text": "Tight tolerances"},
										  {"icon": "icon_check", "title": "Quality checked", "text": "Every batch inspected"},
										  {"icon": "icon_truck", "title": "On-time delivery", "text": "Across Tamil Nadu"}],
								"tagline": "Built right.\n*Delivered on time.*", "website": "sribalajiind.in"}},
	"problem_solution": {"any": {"business": "Queen Touch Technology", "headline": "The hidden *cost* of manual work",
								 "subline": "Manual processes get the job done — at a cost your business can't ignore.",
								 "problems": [{"icon": "icon_chart", "title": "Higher costs"}, {"icon": "icon_clock", "title": "Wasted time"},
											  {"icon": "icon_bolt", "title": "More errors"}, {"icon": "icon_heart", "title": "Missed chances"}],
								 "kicker": "Automate. *Optimize.* Outperform.",
								 "items": [{"icon": "icon_chart", "title": "Reduce costs"}, {"icon": "icon_clock", "title": "Save time"},
										   {"icon": "icon_check", "title": "Fewer errors"}, {"icon": "icon_rocket", "title": "Grow faster"}],
								 "phone": "95669 66764", "website": "queentouchtech.com"}},
	"wave_agency": {"any": {"business": "Kural Digital", "headline": "Creative marketing *agency*", "subline": "We plan, design and post — you get the customers.",
							"list_title": "What we do", "list": ["Social media marketing", "Brand design", "Google profile and SEO", "Websites"],
							"website": "kuraldigital.in", "phone": "98400 12345"},
					"industry": {"business": "Bright Minds Academy", "headline": "Learn *coding* this summer", "subline": "Small batches, real projects, friendly teachers.",
								 "list_title": "Courses", "list": ["Python for beginners", "Web design", "App building", "Spoken English"],
								 "website": "brightminds.in", "phone": "98400 12345"}},
	"numbered_services": {"any": {"business": "Kural Digital", "kicker": "Great ideas to", "headline": "Grow your *business!*",
								  "subline": "Plans that bring customers, not just likes.", "list_title": "What we do",
								  "list": ["Brand solution", "Digital marketing", "Marketing strategy", "Business analysis"], "cta": "CONTACT US",
								  "phone": "98400 12345", "website": "kuraldigital.in"},
						  "beauty": {"business": "Glow Salon", "kicker": "Look your", "headline": "Best *every day*", "subline": "Hair, skin and bridal care by trained stylists.",
									 "list_title": "Our services", "list": ["Haircut & styling", "Facials", "Bridal makeup", "Hair spa"], "cta": "BOOK NOW",
									 "phone": "98400 12345", "website": "glowsalon.in"}},
	"curve_photo": {"any": {"business": "Kural Digital", "headline": "Digital *Marketing Expert*", "quote": "Your ideas, seen by the right people",
							"cta": "GET STARTED", "phone": "98400 12345", "website": "kuraldigital.in"},
					"beauty": {"business": "Dr. Meena's Skin Clinic", "headline": "Healthy skin *starts here*", "quote": "Care from a qualified dermatologist",
							   "cta": "BOOK A VISIT", "phone": "98400 12345", "website": "meenaskin.in"}},
	"center_hero": {"any": {"business": "Fresh Basket", "kicker": "Fresh & Healthy", "headline": "Vegetables", "tagline": "Delivered every morning",
							"badge": "Free delivery", "phone": "98400 12345", "website": "freshbasket.in", "cta": "ORDER NOW"},
					"shops": {"business": "Style Hub", "kicker": "New arrivals", "headline": "Kurtis", "tagline": "Cotton for the summer",
							  "badge": "Just in", "phone": "98400 12345", "website": "stylehub.in", "cta": "SHOP NOW"},
					"beauty": {"business": "Glow Salon", "kicker": "Bridal", "headline": "Makeup", "tagline": "Your day, your look",
							   "badge": "Book early", "phone": "98400 12345", "website": "glowsalon.in", "cta": "BOOK NOW"}},
	"product_promo": {"any": {"business": "Murali Yolo", "kicker": "Fresh and Tasty", "headline": "Pizza", "price_label": "Pizza starts Rs.", "price": "149/-",
							  "phone": "+91 93154 22466", "cta": "Order on Zomato", "address": "C4/115, New Kondli, Near Jay Ambey Society"},
					  "shops": {"business": "Mobile Point", "kicker": "Just arrived", "headline": "Earbuds", "price_label": "From Rs.", "price": "999/-",
								"phone": "98400 12345", "cta": "Call to order", "address": "12 Bazaar Street, Madurai"}},
	"sale": {"any": {"business": "Style Hub", "kicker": "Big", "headline": "Sale", "price_label": "Discount", "badge": "Up to *40%* off",
					 "cta": "Shop now", "website": "stylehub.in"}},
	"listing": {"any": {"business": "Kavya Homes", "place": "Krishnarajapuram", "kicker": "New Home",
						"items": [{"icon": "icon_home", "title": "2 BHK", "text": "2 Bedroom + Hall + Kitchen"},
								  {"icon": "icon_pin", "title": "1.5 Cent", "text": "Land area"},
								  {"icon": "icon_check", "title": "Approved", "text": "Building & land"}],
						"price_label": "மொத்த விலை:", "price": "₹42 லட்சம்", "list": ["Hall", "Bedroom", "Kitchen", "Bathroom"],
						"pillars": [["icon_home", "Modern elevation"], ["icon_drop", "24/7 water"], ["icon_bolt", "EB connection"], ["icon_shield", "Secure location"]],
						"tagline": "Real estate | Buying | Selling | Rental", "phone": "98400 12345"},
				"shops": {"business": "SV Motors", "place": "Tirunelveli", "kicker": "Used car",
						  "items": [{"icon": "icon_check", "title": "2019 Swift VXI", "text": "Petrol · manual"},
									{"icon": "icon_chart", "title": "38,000 km", "text": "Single owner"},
									{"icon": "icon_shield", "title": "Insured", "text": "Till March 2027"}],
						  "price_label": "Price", "price": "₹5.4 lakh", "list": ["Front", "Inside", "Dashboard", "Back"],
						  "pillars": [["icon_check", "Papers clear"], ["icon_gear", "Serviced"], ["icon_shield", "Warranty"]],
						  "tagline": "Buy · Sell · Exchange", "phone": "98400 12345"}},
	"gallery": {"any": {"business": "Lens Studio", "headline": "Photo*graphy*", "subline": "For all occasions", "kicker": "Professional studio",
						"list": ["Event coverage", "Fashion shoot", "Wedding", "Family portrait", "Videography"], "badge": "Book now", "person": "Arun Kumar",
						"role": "Photographer", "phone": "98400 12345", "website": "lensstudio.in", "email": "hello@lensstudio.in"},
				"beauty": {"business": "Glow Salon", "headline": "Bridal *looks*", "subline": "Makeup · hair · saree draping", "kicker": "Bridal studio",
						   "list": ["Bridal makeup", "Engagement look", "Hairstyling", "Saree draping"], "badge": "Book early", "person": "Priya",
						   "role": "Makeup artist", "phone": "98400 12345", "website": "glowsalon.in"}},
	"circles_labels": {"any": {"business": "Thangam Academy", "headline": "Master Your *English*",
							   "items": [{"icon": "icon_book", "title": "Reading"}, {"icon": "icon_check", "title": "Spelling"},
										 {"icon": "icon_music", "title": "Phonics"}, {"icon": "icon_code", "title": "Grammar"}],
							   "subline": "Spoken English for adults too", "cta": "Contact us", "phone": "87541 00704"},
					   "beauty": {"business": "FitZone Gym", "headline": "Get *fit* with us",
								  "items": [{"icon": "icon_heart", "title": "Cardio"}, {"icon": "icon_bolt", "title": "Strength"},
											{"icon": "icon_team", "title": "Group class"}, {"icon": "icon_check", "title": "Diet plan"}],
								  "subline": "Morning and evening batches", "cta": "Join today", "phone": "98400 12345"}},
	"question_rows": {"any": {"business": "Thangam Academy", "headline": "Is your child…",
							  "items": [{"icon": "icon_book", "text": "Unable to", "title": "Read?"}, {"icon": "icon_team", "text": "Unable to", "title": "Understand English?"},
										{"icon": "icon_music", "text": "Not getting", "title": "Good pronunciation?"},
										{"icon": "icon_heart", "text": "Unable to", "title": "Speak back?"}],
							  "subline": "When your child can *read, understand and speak* English…", "kicker": "they can focus on *all other subjects*",
							  "cta": "Call now", "phone": "87541 00704"},
					  "beauty": {"business": "Care Clinic", "headline": "Do you have…",
								 "items": [{"icon": "icon_heart", "text": "Frequent", "title": "Back pain?"}, {"icon": "icon_bolt", "text": "Stiff", "title": "Neck?"},
										   {"icon": "icon_team", "text": "Painful", "title": "Knees?"}, {"icon": "icon_clock", "text": "Poor", "title": "Sleep?"}],
								 "subline": "Physiotherapy can *help you move freely* again", "kicker": "Book an assessment *this week*",
								 "cta": "Call now", "phone": "98400 12345"}},
	"event": {"any": {"business": "Grace Community Church", "headline": "Sunday Service", "role": "Word of God", "person": "Pastor A. Samuel",
					  "time": "7:30 AM", "place": "Grace Community Church", "address": "12 Beach Road, Tuticorin – 628001", "date": "18 Oct",
					  "qr": "https://maps.google.com/?q=Tuticorin"},
			  "industry": {"business": "Bright Minds Academy", "headline": "Free Seminar", "role": "Career guidance by", "person": "Dr. K. Ramesh",
						   "time": "10:00 AM", "place": "Bright Minds Academy", "address": "4 College Road, Trichy", "date": "25 Oct",
						   "qr": "https://brightminds.in/seminar"},
			  "places": {"business": "Royal Mahal", "headline": "Grand Opening", "role": "Inaugurated by", "person": "Our first guests",
						 "time": "6:00 PM", "place": "Royal Mahal Banquet", "address": "21 Anna Nagar, Chennai", "date": "1 Nov",
						 "qr": "https://maps.google.com/?q=Anna+Nagar"}},
	"greeting": {"any": {"business": "Sri Murugan Sweets", "kicker": "Wishing you a", "headline": "Happy Deepavali",
						 "subline": "May the festival of lights bring joy and sweetness to your home.", "phone": "98400 12345"}},
	"tribute": {"any": {"business": "Memories Studio", "person": "R. Devaraj", "role": "Music teacher", "years": "1950 – 2026",
						"quote": "Your music gave life to countless stories. Thank you for the timeless melodies."}},
	"quote_tip": {"any": {"business": "Kural Digital", "kicker": "Tip of the week", "headline": "Reply to every review — *good or bad*. Customers read your answers.",
						  "subline": "It takes two minutes and builds trust.", "phone": "98400 12345", "website": "kuraldigital.in"},
				  "food": {"business": "Annapoorna Mess", "kicker": "Did you know?", "headline": "Our sambar is made *fresh every morning* — never reheated.",
						   "subline": "Come early for the first batch at 7 am.", "phone": "98400 12345"}},
}
# Photos for the library pictures: a kit (kit-images/<kit>) by layout and group.
SAMPLE_KITS = {"technology": "it", "services": "services", "industry": "education", "food": "restaurant", "shops": "fashion",
			   "beauty": "beauty", "places": "realestate", "other": "ngo", "any": "other"}
LAYOUT_KITS = {"listing": {"places": "realestate", "shops": "automotive"}, "event": {"other": "events", "any": "events"},
			   "center_hero": {"food": "grocery"}, "product_promo": {"food": "restaurant", "shops": "electronics"}}


def sample_for(layout: str, group: str) -> dict:
	s = SAMPLES.get(layout) or {}
	return dict(s.get(group) or s.get("any") or {})


def sample_kit(layout: str, group: str) -> str:
	return (LAYOUT_KITS.get(layout) or {}).get(group) or SAMPLE_KITS.get(group) or "other"


def _key(layout: str, name: str) -> str:
	return f"{layout.replace('_', '-')}-{name.lower().replace(' ', '-').replace('&', 'and')}"


def templates() -> list[dict]:
	"""Every library template as plain data (the source QTT Post Template is synced from)."""
	out = []
	for i, (layout, name, variant, palette, fonts, look) in enumerate(_T):
		meta = LAYOUTS[layout]
		group = meta["groups"][0] if meta["groups"] != ["any"] else "any"
		out.append({
			"key": _key(layout, name), "title": f"{meta['label']} · {name}", "layout": layout, "variant": variant,
			"post_types": list(meta["post_types"]), "groups": list(meta["groups"]), "look": look, "palette": palette,
			"fonts": fonts, "formats": list(FORMATS), "sort": i, "sample_group": group,
		})
	return out


def catalog_hash() -> str:
	return hashlib.sha1(json.dumps([templates(), SAMPLES], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def matches(t: dict, *, post_type: str | None = None, group: str | None = None, business_type: str | None = None) -> bool:
	"""Does a template suit this filter? A business type is matched through its group."""
	if post_type and post_type not in t["post_types"]:
		return False
	g = group or (business_types.group_of(business_type) if business_type else None)
	if g and "any" not in t["groups"] and g not in t["groups"]:
		return False
	return True
