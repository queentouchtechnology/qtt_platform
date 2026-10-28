"""
The content library (PROJ-0011 C2) — ready-written words for posts, in English and Tamil, that a design is filled with.
Free for every business (a default, like the template library); Studio's AI writes new words on top of it.

Each idea fills a design's slots (headline — *word* is the highlight —, kicker, subline, cta, badge, items) from the
business's own knowledge: {business}, {product}, {price}, {hours}, {delivery}… An idea is only offered when every fact
it needs is there (needs) — nothing is ever invented: no prices, offers, dates or claims the business didn't give.

Occasions: festivals and days to greet on. Fixed ones carry their date; ones that move every year (Diwali, Eid,
Pongal…) take their date from QTT Occasion in Desk (library.occasions) — never guessed.
"""

import re

LANGUAGES = ("en", "ta")

# ---- the ideas -------------------------------------------------------------------------------------------------------
# key: {post_type, groups, needs, occasion?, en: {slots}, ta: {slots}}
IDEAS = {
	# everyday, any business
	"open-hours": {"post_type": "announcement", "groups": ["any"], "needs": ["hours"],
				   "en": {"kicker": "Visit us", "headline": "We're *open*", "subline": "{hours}", "cta": "See you soon"},
				   "ta": {"kicker": "வாருங்கள்", "headline": "நாங்கள் *திறந்திருக்கிறோம்*", "subline": "{hours}", "cta": "விரைவில் சந்திப்போம்"}},
	"product-highlight": {"post_type": "product", "groups": ["any"], "needs": ["product"],
						  "en": {"kicker": "Try our", "headline": "*{product}*", "subline": "{product_details}", "badge": "{price}", "cta": "Ask us today"},
						  "ta": {"kicker": "சுவைத்துப் பாருங்கள்", "headline": "*{product}*", "subline": "{product_details}", "badge": "{price}", "cta": "இன்றே கேளுங்கள்"}},
	"what-we-offer": {"post_type": "service", "groups": ["any"], "needs": ["products3"],
					  "en": {"kicker": "At {business}", "headline": "What we *offer*", "items": "products", "cta": "Call {phone}"},
					  "ta": {"kicker": "{business}-இல்", "headline": "நாங்கள் *வழங்குவது*", "items": "products", "cta": "அழைக்கவும் {phone}"}},
	"why-us": {"post_type": "service", "groups": ["any"], "needs": ["different"],
			   "en": {"kicker": "Why choose", "headline": "*{business}*?", "subline": "{different}", "cta": "Talk to us"},
			   "ta": {"kicker": "ஏன் தேர்ந்தெடுக்க வேண்டும்", "headline": "*{business}*?", "subline": "{different}", "cta": "எங்களிடம் பேசுங்கள்"}},
	"we-deliver": {"post_type": "announcement", "groups": ["food", "shops"], "needs": ["delivery"],
				   "en": {"kicker": "Good news", "headline": "We *deliver*", "subline": "{delivery}", "cta": "Order now"},
				   "ta": {"kicker": "நல்ல செய்தி", "headline": "நாங்கள் *டெலிவரி* செய்கிறோம்", "subline": "{delivery}", "cta": "இப்போதே ஆர்டர் செய்யுங்கள்"}},
	"pay-your-way": {"post_type": "announcement", "groups": ["any"], "needs": ["payments"],
					 "en": {"kicker": "Easy payments", "headline": "Pay *your way*", "subline": "{payments}"},
					 "ta": {"kicker": "எளிய கட்டணம்", "headline": "உங்கள் *விருப்பப்படி* செலுத்துங்கள்", "subline": "{payments}"}},
	"thank-you": {"post_type": "announcement", "groups": ["any"], "needs": [],
				  "en": {"kicker": "From all of us", "headline": "Thank *you*", "subline": "Every visit means a lot to the {business} team."},
				  "ta": {"kicker": "எங்கள் அனைவரிடமிருந்தும்", "headline": "*நன்றி*", "subline": "உங்கள் ஒவ்வொரு வருகையும் {business} குழுவுக்கு மிகப் பெரியது."}},
	"call-us": {"post_type": "contact", "groups": ["any"], "needs": ["phone"],
				"en": {"kicker": "Questions?", "headline": "Call or *WhatsApp* us", "subline": "{phone}", "cta": "We're happy to help"},
				"ta": {"kicker": "கேள்விகளா?", "headline": "அழையுங்கள் அல்லது *WhatsApp* செய்யுங்கள்", "subline": "{phone}", "cta": "உதவ மகிழ்ச்சி"}},
	"find-us": {"post_type": "contact", "groups": ["any"], "needs": ["address"],
				"en": {"kicker": "Come and see us", "headline": "Find *us* here", "subline": "{address}"},
				"ta": {"kicker": "நேரில் வாருங்கள்", "headline": "எங்கள் *முகவரி*", "subline": "{address}"}},
	"made-for": {"post_type": "service", "groups": ["any"], "needs": ["audience"],
				 "en": {"kicker": "{business}", "headline": "Made for *{audience}*", "subline": "{about}"},
				 "ta": {"kicker": "{business}", "headline": "*{audience}*-க்காக", "subline": "{about}"}},
	"book-now": {"post_type": "service", "groups": ["beauty", "services", "places", "food"], "needs": ["bookings"],
				 "en": {"kicker": "Plan ahead", "headline": "Book your *slot*", "subline": "{bookings}", "cta": "Book now"},
				 "ta": {"kicker": "முன்கூட்டியே திட்டமிடுங்கள்", "headline": "உங்கள் *நேரத்தை* முன்பதிவு செய்யுங்கள்", "subline": "{bookings}", "cta": "இப்போதே முன்பதிவு"}},
	"new-arrival": {"post_type": "launch", "groups": ["shops", "food", "beauty"], "needs": ["product"],
					"en": {"kicker": "Just arrived", "headline": "*{product}*", "subline": "Ask us about it today.", "badge": "New"},
					"ta": {"kicker": "புதிதாக வந்தது", "headline": "*{product}*", "subline": "இன்றே எங்களிடம் கேளுங்கள்.", "badge": "புதியது"}},
	"hiring": {"post_type": "hiring", "groups": ["any"], "needs": ["phone"],
			   "en": {"kicker": "Join our team", "headline": "We're *hiring*", "subline": "Grow with {business}. Call {phone} to know more.", "cta": "Apply today"},
			   "ta": {"kicker": "எங்கள் குழுவில் சேருங்கள்", "headline": "*வேலைவாய்ப்பு*", "subline": "{business} உடன் வளருங்கள். மேலும் அறிய {phone} அழையுங்கள்.", "cta": "இன்றே விண்ணப்பியுங்கள்"}},
	"weekend": {"post_type": "announcement", "groups": ["food", "shops", "beauty", "places"], "needs": ["hours"],
				"en": {"kicker": "Plans for the weekend?", "headline": "See you this *weekend*", "subline": "{hours}"},
				"ta": {"kicker": "வார இறுதித் திட்டமா?", "headline": "இந்த *வார இறுதியில்* சந்திப்போம்", "subline": "{hours}"}},
	"ask-us": {"post_type": "tip", "groups": ["any"], "needs": [],
			   "en": {"kicker": "Tell us", "headline": "What should we add *next*?", "subline": "Reply in the comments — {business} reads every one."},
			   "ta": {"kicker": "சொல்லுங்கள்", "headline": "அடுத்து என்ன *சேர்க்கலாம்*?", "subline": "கருத்தில் சொல்லுங்கள் — {business} ஒவ்வொன்றையும் படிக்கிறது."}},
	# food
	"fresh-today": {"post_type": "product", "groups": ["food"], "needs": ["about"],
					"en": {"kicker": "Fresh & tasty", "headline": "Made *today*", "subline": "{about}", "cta": "Order now"},
					"ta": {"kicker": "சுடச்சுட", "headline": "*இன்று* செய்தது", "subline": "{about}", "cta": "இப்போதே ஆர்டர் செய்யுங்கள்"}},
	"party-orders": {"post_type": "service", "groups": ["food"], "needs": ["phone"],
					 "en": {"kicker": "Celebrating?", "headline": "Party *orders* welcome", "subline": "Birthdays, functions and office lunches — call {phone}.", "cta": "Order now"},
					 "ta": {"kicker": "கொண்டாட்டமா?", "headline": "*விழா ஆர்டர்கள்* ஏற்கப்படும்", "subline": "பிறந்தநாள், விழாக்கள், அலுவலக மதிய உணவு — {phone} அழையுங்கள்.", "cta": "இப்போதே ஆர்டர் செய்யுங்கள்"}},
	# shops
	"gift-ideas": {"post_type": "product", "groups": ["shops"], "needs": ["products3"],
				   "en": {"kicker": "Looking for a gift?", "headline": "Gift *ideas*", "items": "products", "cta": "Visit us"},
				   "ta": {"kicker": "பரிசு தேடுகிறீர்களா?", "headline": "பரிசு *யோசனைகள்*", "items": "products", "cta": "வாருங்கள்"}},
	"visit-store": {"post_type": "contact", "groups": ["shops"], "needs": ["address", "hours"],
					"en": {"kicker": "Come in and look around", "headline": "Visit our *store*", "subline": "{address}\n{hours}"},
					"ta": {"kicker": "வந்து பாருங்கள்", "headline": "எங்கள் *கடைக்கு* வாருங்கள்", "subline": "{address}\n{hours}"}},
	# beauty & health
	"self-care": {"post_type": "service", "groups": ["beauty"], "needs": ["bookings"],
				  "en": {"kicker": "You deserve it", "headline": "Time for some *self-care*", "subline": "{bookings}", "cta": "Book now"},
				  "ta": {"kicker": "உங்களுக்குத் தகுதியானது", "headline": "*உங்களைக்* கவனியுங்கள்", "subline": "{bookings}", "cta": "இப்போதே முன்பதிவு"}},
	"tip-water": {"post_type": "tip", "groups": ["beauty"], "needs": [],
				  "en": {"kicker": "Tip of the week", "headline": "Drink enough *water* — your skin and body will thank you.", "subline": "Small habits, big difference."},
				  "ta": {"kicker": "இந்த வாரக் குறிப்பு", "headline": "போதுமான *தண்ணீர்* குடியுங்கள் — உங்கள் தோலும் உடலும் நன்றி சொல்லும்.", "subline": "சிறு பழக்கம், பெரிய மாற்றம்."}},
	"tip-walk": {"post_type": "tip", "groups": ["beauty"], "needs": [],
				 "en": {"kicker": "Health tip", "headline": "A *30-minute walk* a day keeps you going.", "subline": "Start today — it's free."},
				 "ta": {"kicker": "ஆரோக்கியக் குறிப்பு", "headline": "தினமும் *30 நிமிட நடை* உங்களை உற்சாகமாக வைக்கும்.", "subline": "இன்றே தொடங்குங்கள் — இது இலவசம்."}},
	# services
	"talk-expert": {"post_type": "service", "groups": ["services"], "needs": ["phone"],
					"en": {"kicker": "Not sure where to start?", "headline": "Talk to an *expert*", "subline": "Call {phone} — {business} is here to help.", "cta": "Call now"},
					"ta": {"kicker": "எங்கே தொடங்குவது என்று தெரியவில்லையா?", "headline": "ஒரு *நிபுணரிடம்* பேசுங்கள்", "subline": "{phone} அழையுங்கள் — {business} உதவத் தயார்.", "cta": "இப்போதே அழையுங்கள்"}},
	"tip-documents": {"post_type": "tip", "groups": ["services"], "needs": [],
					  "en": {"kicker": "Tip of the week", "headline": "Keep your bills and papers in *one folder* — it saves hours at tax time.", "subline": "A little order goes a long way."},
					  "ta": {"kicker": "இந்த வாரக் குறிப்பு", "headline": "பில்களையும் ஆவணங்களையும் *ஒரே கோப்பில்* வையுங்கள் — வரி நேரத்தில் மணிநேரம் மிச்சம்.", "subline": "கொஞ்சம் ஒழுங்கு, நிறைய நன்மை."}},
	# technology
	"go-online": {"post_type": "service", "groups": ["technology"], "needs": [],
				  "en": {"kicker": "Is your business", "headline": "*Online* yet?", "subline": "Customers search before they visit. Let them find you.", "cta": "Talk to {business}"},
				  "ta": {"kicker": "உங்கள் வணிகம்", "headline": "*ஆன்லைனில்* உள்ளதா?", "subline": "வாடிக்கையாளர்கள் வருவதற்கு முன் தேடுகிறார்கள். அவர்கள் உங்களைக் கண்டுபிடிக்கட்டும்.", "cta": "{business} உடன் பேசுங்கள்"}},
	"automate": {"post_type": "problem", "groups": ["technology"], "needs": [],
				 "en": {"kicker": "Automate. *Optimize.* Grow.", "headline": "Stop doing it *by hand*",
						"subline": "Repeated work costs time and brings mistakes.", "cta": "Ask {business} how"},
				 "ta": {"kicker": "தானியங்கி. *சீராக்கு.* வளர்.", "headline": "*கையால்* செய்வதை நிறுத்துங்கள்",
						"subline": "திரும்பத் திரும்பச் செய்யும் வேலை நேரத்தை வீணாக்கி தவறுகளைக் கொண்டுவரும்.", "cta": "{business}-இடம் கேளுங்கள்"}},
	"tip-backup": {"post_type": "tip", "groups": ["technology"], "needs": [],
				   "en": {"kicker": "Tech tip", "headline": "Back up your *website and files* every day — one bad day can cost months of work.", "subline": "Automatic backups are the easiest."},
				   "ta": {"kicker": "தொழில்நுட்பக் குறிப்பு", "headline": "உங்கள் *இணையதளத்தையும் கோப்புகளையும்* தினமும் காப்புப் பிரதி எடுங்கள் — ஒரு மோசமான நாள் மாத வேலையை அழிக்கலாம்.", "subline": "தானியங்கி காப்புப் பிரதி மிக எளிது."}},
	"tip-password": {"post_type": "tip", "groups": ["technology"], "needs": [],
					 "en": {"kicker": "Stay safe", "headline": "Use a *different password* for every account — and turn on two-step sign-in.", "subline": "It takes a minute and stops most break-ins."},
					 "ta": {"kicker": "பாதுகாப்பாக இருங்கள்", "headline": "ஒவ்வொரு கணக்குக்கும் *வெவ்வேறு கடவுச்சொல்* — இரண்டு படி உள்நுழைவையும் இயக்குங்கள்.", "subline": "ஒரு நிமிடம் போதும், பெரும்பாலான ஊடுருவல்களைத் தடுக்கும்."}},
	# places (real estate, hotels, events)
	"dream-home": {"post_type": "listing", "groups": ["places"], "needs": ["phone"],
				   "en": {"kicker": "Looking for a home?", "headline": "Your dream home *starts here*", "subline": "Call {phone} for site visits.", "cta": "Book a site visit"},
				   "ta": {"kicker": "வீடு தேடுகிறீர்களா?", "headline": "உங்கள் கனவு இல்லம் *இங்கே தொடங்குகிறது*", "subline": "இட வருகைக்கு {phone} அழையுங்கள்.", "cta": "இட வருகைக்கு முன்பதிவு"}},
	"plan-event": {"post_type": "event", "groups": ["places"], "needs": ["phone"],
				   "en": {"kicker": "Planning a celebration?", "headline": "Let's make it *special*", "subline": "Weddings, birthdays and functions — call {phone}.", "cta": "Enquire now"},
				   "ta": {"kicker": "கொண்டாட்டம் திட்டமிடுகிறீர்களா?", "headline": "அதைச் *சிறப்பாக்குவோம்*", "subline": "திருமணம், பிறந்தநாள், விழாக்கள் — {phone} அழையுங்கள்.", "cta": "இப்போதே விசாரியுங்கள்"}},
	# education & industry
	"admissions-open": {"post_type": "course", "groups": ["industry"], "needs": ["phone"],
						"en": {"kicker": "Enrol now", "headline": "Admissions *open*", "subline": "Call {phone} to know the batches and fees.", "cta": "Call now"},
						"ta": {"kicker": "இப்போதே சேருங்கள்", "headline": "*சேர்க்கை* நடைபெறுகிறது", "subline": "வகுப்புகள், கட்டண விவரங்களுக்கு {phone} அழையுங்கள்.", "cta": "இப்போதே அழையுங்கள்"}},
	"learn-new": {"post_type": "course", "groups": ["industry"], "needs": ["products3"],
				  "en": {"kicker": "This month at {business}", "headline": "Learn something *new*", "items": "products", "cta": "Join today"},
				  "ta": {"kicker": "இந்த மாதம் {business}-இல்", "headline": "*புதிதாகக்* கற்றுக்கொள்ளுங்கள்", "items": "products", "cta": "இன்றே சேருங்கள்"}},
	"made-to-order": {"post_type": "service", "groups": ["industry"], "needs": ["phone"],
					  "en": {"kicker": "Send us your drawing", "headline": "Made *to order*", "subline": "Small and large batches — call {phone}.", "cta": "Get a quote"},
					  "ta": {"kicker": "உங்கள் வரைபடத்தை அனுப்புங்கள்", "headline": "*ஆர்டருக்கு ஏற்ப* தயாரிப்பு", "subline": "சிறிய, பெரிய அளவுகள் — {phone} அழையுங்கள்.", "cta": "விலை கேளுங்கள்"}},
	# community & worship
	"join-us": {"post_type": "event", "groups": ["other"], "needs": ["hours"],
				"en": {"kicker": "Everyone is welcome", "headline": "Join *us*", "subline": "{hours}"},
				"ta": {"kicker": "அனைவரும் வரவேற்கப்படுகிறீர்கள்", "headline": "எங்களுடன் *இணையுங்கள்*", "subline": "{hours}"}},
	"volunteers": {"post_type": "announcement", "groups": ["other"], "needs": ["phone"],
				   "en": {"kicker": "Lend a hand", "headline": "Volunteers *welcome*", "subline": "Give a few hours a month with {business}. Call {phone}."},
				   "ta": {"kicker": "கை கொடுங்கள்", "headline": "தன்னார்வலர்கள் *வரவேற்கப்படுகிறார்கள்*", "subline": "மாதம் சில மணிநேரம் {business} உடன் சேவை செய்யுங்கள். {phone} அழையுங்கள்."}},
}

# ---- occasions --------------------------------------------------------------------------------------------------------
# key: (English name, Tamil name, fixed date "MM-DD" or None — then QTT Occasion in Desk holds each year's date)
OCCASIONS = {
	"new-year": ("New Year", "புத்தாண்டு", "01-01"),
	"pongal": ("Pongal", "பொங்கல்", None),
	"republic-day": ("Republic Day", "குடியரசு தினம்", "01-26"),
	"womens-day": ("Women's Day", "மகளிர் தினம்", "03-08"),
	"tamil-new-year": ("Tamil New Year", "தமிழ்ப் புத்தாண்டு", "04-14"),
	"eid-ul-fitr": ("Ramzan", "ரம்ஜான்", None),
	"may-day": ("May Day", "மே தினம்", "05-01"),
	"bakrid": ("Bakrid", "பக்ரீத்", None),
	"independence-day": ("Independence Day", "சுதந்திர தினம்", "08-15"),
	"onam": ("Onam", "ஓணம்", None),
	"ganesh-chaturthi": ("Vinayagar Chathurthi", "விநாயகர் சதுர்த்தி", None),
	"teachers-day": ("Teachers' Day", "ஆசிரியர் தினம்", "09-05"),
	"ayudha-puja": ("Ayudha Puja", "ஆயுத பூஜை", None),
	"deepavali": ("Deepavali", "தீபாவளி", None),
	"childrens-day": ("Children's Day", "குழந்தைகள் தினம்", "11-14"),
	"karthigai-deepam": ("Karthigai Deepam", "கார்த்திகை தீபம்", None),
	"christmas": ("Christmas", "கிறிஸ்துமஸ்", "12-25"),
	"good-friday": ("Good Friday", "புனித வெள்ளி", None),
	"easter": ("Easter", "ஈஸ்டர்", None),
}
# The faith a festival belongs to. A church, temple or mosque (Business › Knowledge › Type of business: Church, temple &
# religious, with its faith) is offered only its own faith's festivals and the ones for everyone; other businesses get all.
OCCASION_FAITH = {
	"deepavali": "Hindu", "karthigai-deepam": "Hindu", "ganesh-chaturthi": "Hindu", "ayudha-puja": "Hindu", "onam": "Hindu",
	"eid-ul-fitr": "Muslim", "bakrid": "Muslim",
	"christmas": "Christian", "good-friday": "Christian", "easter": "Christian",
}
FAITHS = ("Christian", "Hindu", "Muslim", "Other")


def occasion_suits(key: str, *, business_type: str | None, faith: str | None) -> bool:
	"""Offer this festival to the business? Faith-bound festivals go to religious businesses of that faith only (one
	whose faith isn't set gets none of them); every other business gets all, as before."""
	own = OCCASION_FAITH.get(key)
	if not own or business_type != "religious":
		return True
	return (faith or "") == own
_WISH = {  # the wish under each greeting (en, ta)
	"new-year": ("May the new year bring health, happiness and success to you and your family.", "புத்தாண்டு உங்களுக்கும் உங்கள் குடும்பத்துக்கும் ஆரோக்கியம், மகிழ்ச்சி, வெற்றி தரட்டும்."),
	"pongal": ("May this harvest festival fill your home with sweetness and plenty.", "இந்த அறுவடைத் திருநாள் உங்கள் இல்லத்தை இனிமையாலும் செழிப்பாலும் நிறைக்கட்டும்."),
	"republic-day": ("Saluting the spirit of our Constitution and our nation.", "நம் அரசியலமைப்பின் உணர்வுக்கும் நம் நாட்டுக்கும் வணக்கம்."),
	"womens-day": ("To every woman who inspires us — thank you.", "எங்களை ஊக்குவிக்கும் ஒவ்வொரு பெண்ணுக்கும் — நன்றி."),
	"tamil-new-year": ("May this new year bring prosperity and joy to every home.", "இந்தப் புத்தாண்டு ஒவ்வொரு இல்லத்துக்கும் வளமும் மகிழ்ச்சியும் தரட்டும்."),
	"eid-ul-fitr": ("May this Eid bring peace, joy and blessings to you and your family.", "இந்த ஈத் உங்களுக்கும் உங்கள் குடும்பத்துக்கும் அமைதி, மகிழ்ச்சி, ஆசிகள் தரட்டும்."),
	"may-day": ("Honouring every worker who builds our world.", "நம் உலகைக் கட்டியெழுப்பும் ஒவ்வொரு உழைப்பாளிக்கும் வணக்கம்."),
	"bakrid": ("May this Bakrid bring peace and togetherness to your home.", "இந்த பக்ரீத் உங்கள் இல்லத்துக்கு அமைதியும் ஒற்றுமையும் தரட்டும்."),
	"independence-day": ("Proud to be Indian. Happy Independence Day!", "இந்தியர் என்பதில் பெருமை. இனிய சுதந்திர தின வாழ்த்துகள்!"),
	"onam": ("May this Onam bring joy, colour and togetherness.", "இந்த ஓணம் மகிழ்ச்சியும் வண்ணமும் ஒற்றுமையும் தரட்டும்."),
	"ganesh-chaturthi": ("May Lord Vinayagar remove every obstacle from your path.", "விநாயகப் பெருமான் உங்கள் பாதையிலுள்ள தடைகளை நீக்கட்டும்."),
	"teachers-day": ("Thank you to every teacher who shaped us.", "எங்களை உருவாக்கிய ஒவ்வொரு ஆசிரியருக்கும் நன்றி."),
	"ayudha-puja": ("May your work and tools bring you success all year.", "உங்கள் உழைப்பும் கருவிகளும் ஆண்டு முழுவதும் வெற்றி தரட்டும்."),
	"deepavali": ("May the festival of lights bring joy and sweetness to your home.", "ஒளித் திருநாள் உங்கள் இல்லத்துக்கு மகிழ்ச்சியும் இனிமையும் தரட்டும்."),
	"childrens-day": ("To every child — keep dreaming big.", "ஒவ்வொரு குழந்தைக்கும் — பெரிதாகக் கனவு காணுங்கள்."),
	"karthigai-deepam": ("May the light of the lamps fill your life with peace.", "தீப ஒளி உங்கள் வாழ்வை அமைதியால் நிறைக்கட்டும்."),
	"christmas": ("Wishing you peace, joy and love this Christmas.", "இந்தக் கிறிஸ்துமஸ் உங்களுக்கு அமைதி, மகிழ்ச்சி, அன்பு தரட்டும்."),
	"good-friday": ("“Greater love hath no man than this, that a man lay down his life for his friends.” — John 15:13",
					"“ஒருவன் தன் சிநேகிதருக்காகத் தன் ஜீவனைக் கொடுக்கிற அன்பிலும் அதிகமான அன்பு ஒருவரிடத்திலுமில்லை.” — யோவான் 15:13"),
	"easter": ("He is risen! Wishing you the joy and hope of Easter.", "அவர் உயிர்த்தெழுந்தார்! ஈஸ்டர் திருநாளின் மகிழ்ச்சியும் நம்பிக்கையும் உங்களுக்கு உண்டாகட்டும்."),
}
# A day that isn't "happy": its own heading words (en kicker, ta headline).
_SOLEMN = {"good-friday": ("Remembering", "புனித வெள்ளி")}
for _k, (_en, _ta, _d) in OCCASIONS.items():
	IDEAS[f"wish-{_k}"] = {
		"post_type": "greeting", "groups": ["any"], "needs": [], "occasion": _k,
		"en": {"kicker": _SOLEMN[_k][0] if _k in _SOLEMN else "Wishing you a happy", "headline": _en, "subline": _WISH[_k][0], "tagline": "— {business}"},
		"ta": {"kicker": "" if _k in _SOLEMN else "இனிய", "headline": _SOLEMN[_k][1] if _k in _SOLEMN else f"{_ta} நல்வாழ்த்துகள்",
			   "subline": _WISH[_k][1], "tagline": "— {business}"},
	}


# ---- facts and filling ------------------------------------------------------------------------------------------------
def facts(knowledge: dict, contacts: dict, business: str) -> dict:
	"""What ideas may use, from the business's own knowledge and profile. Missing → absent (the idea isn't offered)."""
	f = {"business": business}
	for key in ("about", "hours", "delivery", "payments", "bookings", "audience", "different"):
		v = str(knowledge.get(key) or "").strip()
		if v:
			f[key] = v
	for key in ("phone", "website", "address"):
		v = str((contacts or {}).get(key) or ((contacts or {}).get("whatsapp") if key == "phone" else "") or "").strip()
		if v:
			f[key] = v
	offers = [o for o in knowledge.get("offerings") or [] if o.get("active", 1) and str(o.get("item") or "").strip()]
	if offers:
		f["product"] = offers[0]["item"].strip()
		if str(offers[0].get("price") or "").strip():
			f["price"] = offers[0]["price"].strip()
		if str(offers[0].get("details") or "").strip():
			f["product_details"] = offers[0]["details"].strip()
	if len(offers) >= 3:
		f["products3"] = offers[:4]
	return f


def missing(idea: dict, f: dict) -> list[str]:
	"""The facts an idea needs that the business hasn't given."""
	return [n for n in idea.get("needs") or [] if not f.get(n)]


_SLOT = re.compile(r"\{(\w+)\}")


def _fill_text(text: str, f: dict) -> str | None:
	"""'{product} — {price}' with the facts; None when a fact it uses is missing (never left as a gap)."""
	gaps = [m for m in _SLOT.findall(text) if not f.get(m) or not isinstance(f.get(m), str)]
	if gaps:
		return None
	return _SLOT.sub(lambda m: f[m.group(1)], text)


ICONS = ("icon_check", "icon_star", "icon_heart", "icon_bolt")


def fill(idea: dict, f: dict, lang: str = "en") -> dict | None:
	"""The idea's slots in the language, filled from the facts; None when a needed fact is missing. A slot whose own
	optional fact is missing (a price, details) is simply left out."""
	if missing(idea, f):
		return None
	words = idea.get(lang if lang in LANGUAGES else "en") or idea["en"]
	out = {}
	for slot, text in words.items():
		if slot == "items" and text == "products":
			out["items"] = [{"icon": ICONS[k % len(ICONS)], "title": o["item"], "text": " · ".join(x for x in (o.get("price"), o.get("details")) if x)}
							for k, o in enumerate(f.get("products3") or [])]
			continue
		v = _fill_text(text, f)
		if v:
			out[slot] = v
	return out if out.get("headline") else None


def suits(idea: dict, *, post_types: list[str] | None = None, group: str | None = None, occasion: str | None = None) -> bool:
	if post_types and idea["post_type"] not in post_types:
		return False
	if group and "any" not in idea["groups"] and group not in idea["groups"]:
		return False
	if occasion and idea.get("occasion") != occasion:
		return False
	return True


def language_of(knowledge_language: str) -> str:
	return "ta" if "tamil" in str(knowledge_language or "").lower() or "தமிழ்" in str(knowledge_language or "") else "en"


# ---- article topics and newsletter ideas (by group) — the Marketing assistant's monthly drafts start from these ------
ARTICLE_TOPICS = {
	"any": ["How to choose the right {product} for you", "Questions our customers ask most — answered", "A day at {business}: how we work",
			"What makes {business} different"],
	"food": ["Why fresh ingredients make the difference", "How to plan the menu for a family function", "Our most-loved dishes and why"],
	"shops": ["How to pick the right size and fit", "Gift guide: ideas for every budget", "How to care for what you buy so it lasts"],
	"beauty": ["A simple skin routine for Indian weather", "How to prepare for your bridal makeup", "Small habits for better health"],
	"services": ["Documents to keep ready before tax time", "When should you call an expert?", "Common mistakes small businesses make"],
	"technology": ["Why every small business needs a website", "Five tasks you can automate this month", "How to keep your business data safe",
				   "WhatsApp for business: what customers expect"],
	"places": ["Checklist before you buy a plot or house", "How to plan a function without stress", "What to look for when you book a hall"],
	"industry": ["How to choose the right course for your child", "Study habits that really work", "What to check before you place a manufacturing order"],
	"other": ["How you can help your community", "A year of service: what we did together"],
}
NEWSLETTER_IDEAS = ["What's new at {business} this month", "Our favourites this month", "Thank you for being with us", "Coming up at {business}"]


def article_topics(group: str, f: dict) -> list[str]:
	"""Topics for the group (and every business), with the facts filled; ones needing a missing fact left out."""
	out = []
	for t in [*ARTICLE_TOPICS.get(group, []), *ARTICLE_TOPICS["any"]]:
		v = _fill_text(t, f)
		if v:
			out.append(v)
	return out
