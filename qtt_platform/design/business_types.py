"""
Business types (PROJ-0011 B/C): what a business is, so its posts get the right photos, templates and ideas.

The same keys as the website and store kits (qtt_services/wordpress/kit-images/<key>), grouped for the library's
"business type" filter. Technology companies (like QTT itself) have their own group — software and app makers, IT
services, digital marketing — so the library keeps room for their kind of posts (launches, features, case studies,
tips, hiring), not only shop offers. A type without its own photo kit borrows the nearest one (`photos`).
"""

GROUPS = (
	("food", "Food and drink"), ("shops", "Shops and online stores"), ("beauty", "Beauty and health"),
	("services", "Services and professionals"), ("technology", "Technology"), ("places", "Hotels, homes and events"),
	("industry", "Industry and education"), ("other", "Other"),
)

# key: (label, group, photo kit)
TYPES = {
	"restaurant": ("Restaurant & café", "food", "restaurant"),
	"sweets": ("Sweets & bakery", "food", "sweets"),
	"grocery": ("Grocery & daily needs", "food", "grocery"),
	"retail": ("Shop & retail", "shops", "retail"),
	"fashion": ("Fashion & clothing", "shops", "fashion"),
	"jewellery": ("Jewellery", "shops", "jewellery"),
	"electronics": ("Electronics & mobiles", "shops", "electronics"),
	"furniture": ("Furniture & home", "shops", "furniture"),
	"general-store": ("General online store", "shops", "general-store"),
	"cosmetics": ("Beauty & cosmetics shop", "beauty", "cosmetics"),
	"beauty": ("Salon & beauty", "beauty", "beauty"),
	"health": ("Clinic & health", "beauty", "health"),
	"fitness": ("Gym & fitness", "beauty", "fitness"),
	"services": ("Services & consulting", "services", "services"),
	"finance": ("CA, tax & finance", "services", "finance"),
	"automotive": ("Car & bike service", "services", "automotive"),
	"photography": ("Photography & studio", "services", "photography"),
	"it": ("IT services & support", "technology", "it"),
	"software": ("Software, apps & SaaS", "technology", "it"),
	"digital-agency": ("Digital marketing & web agency", "technology", "it"),
	"tech-training": ("Tech training & courses", "technology", "education"),
	"hotel": ("Hotel & stay", "places", "hotel"),
	"interior": ("Interior design", "places", "interior"),
	"realestate": ("Real estate & construction", "places", "realestate"),
	"events": ("Events & weddings", "places", "events"),
	"education": ("Coaching & education", "industry", "education"),
	"manufacturing": ("Manufacturing & industry", "industry", "manufacturing"),
	"ngo": ("NGO & community", "other", "ngo"),
	"other": ("Other business", "other", "other"),
}


def valid(key) -> str:
	"""A known type key, or '' (not set)."""
	return key if key in TYPES else ""


def photo_kit(key) -> str:
	return TYPES.get(key, TYPES["other"])[2]


def group_of(key) -> str:
	return TYPES.get(key, TYPES["other"])[1]


def listing() -> list[dict]:
	"""For pickers: [{key, label, group, group_label}] in group order."""
	labels = dict(GROUPS)
	order = {g: i for i, (g, _) in enumerate(GROUPS)}
	return sorted(({"key": k, "label": v[0], "group": v[1], "group_label": labels[v[1]]} for k, v in TYPES.items()),
				  key=lambda x: (order[x["group"]], x["label"]))
