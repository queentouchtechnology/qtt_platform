"""
The design base (PROJ-0011 B) — pure rules, no Frappe; tests/test_design.py.

Every post, story, article picture and newsletter header is built from the same parts:
  palette   the business's locked brand colours (Business › Knowledge › Brand kit) worked out into every role a design
            needs — the owner's colours are never changed, only completed (a missing one is derived from theirs) — and a
            readable text colour for each background (WCAG contrast)
  fonts     Google Fonts (open licence) in pairs, with Tamil, Hindi and Arabic faces so every language renders
  formats   the post sizes each platform wants
The patterns and elements (patterns.py, elements.py) draw only with the palette, so a design always looks like the
business. The logo is placed as it is — never recoloured, cropped or redrawn.
"""

import colorsys
import re

FORMATS = {  # key: (width, height, label, where)
	"square": (1080, 1080, "Square", "Instagram and Facebook feed"),
	"portrait": (1080, 1350, "Portrait", "Instagram feed (4:5)"),
	"story": (1080, 1920, "Story", "Instagram and Facebook stories, WhatsApp status"),
	"landscape": (1200, 630, "Wide", "Facebook link posts, LinkedIn, X"),
	"gbp": (1200, 900, "Google", "Google Business profile posts (4:3)"),
}
DEFAULT_PRIMARY = "#1d4ed8"


# ---- colour ----------------------------------------------------------------------------------------------------------
def hex6(v) -> str:
	m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(v or "").strip())
	return f"#{m.group(1).lower()}" if m else ""


def _rgb(h: str) -> tuple[float, float, float]:
	h = hex6(h)[1:]
	return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(r: float, g: float, b: float) -> str:
	return "#" + "".join(f"{max(0, min(255, round(x * 255))):02x}" for x in (r, g, b))


def mix(a: str, b: str, t: float) -> str:
	"""a → b by t (0 = a, 1 = b)."""
	(r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
	return _hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)


def luminance(h: str) -> float:
	def ch(c: float) -> float:
		return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

	r, g, b = _rgb(h)
	return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
	la, lb = sorted((luminance(a), luminance(b)), reverse=True)
	return (la + 0.05) / (lb + 0.05)


def on(bg: str, dark: str = "#111827", light: str = "#ffffff") -> str:
	"""The readable text colour on bg: the brand's dark or white, whichever contrasts more."""
	return dark if contrast(bg, dark) >= contrast(bg, light) else light


def _hls(h: str) -> tuple[float, float, float]:
	return colorsys.rgb_to_hls(*_rgb(h))


def _from_hls(hh: float, ll: float, ss: float) -> str:
	return _hex(*colorsys.hls_to_rgb(hh % 1, max(0, min(1, ll)), max(0, min(1, ss))))


def palette(colors: dict | None) -> dict:
	"""The brand kit's colours (primary, secondary, accent, dark, light — any may be missing) → every role a design uses.
	The owner's own colours are kept exactly; only missing ones are worked out from the main colour."""
	c = {k: hex6(v) for k, v in (colors or {}).items()}
	primary = c.get("primary") or DEFAULT_PRIMARY
	h, l, s = _hls(primary)
	secondary = c.get("secondary") or _from_hls(h, max(0.18, l * 0.68), s * 0.9)  # a deeper shade of the main colour
	accent = c.get("accent") or _from_hls(h + 0.5, 0.55, max(s, 0.65))  # its opposite, bright
	dark = c.get("dark") or _from_hls(h, 0.13, min(s, 0.45))
	light = c.get("light") or _from_hls(h, 0.965, min(s, 0.6))
	p = {"primary": primary, "secondary": secondary, "accent": accent, "dark": dark, "light": light, "white": "#ffffff"}
	for k in ("primary", "secondary", "accent", "dark", "light"):
		p[f"on_{k}"] = on(p[k], dark=dark)
	p["primary_soft"] = mix(primary, "#ffffff", 0.82)
	p["primary_deep"] = mix(primary, dark, 0.45)
	p["accent_soft"] = mix(accent, "#ffffff", 0.75)
	p["owner"] = sorted(k for k in ("primary", "secondary", "accent", "dark", "light") if c.get(k))  # which are theirs
	return p


# ---- fonts -----------------------------------------------------------------------------------------------------------
# Google Fonts, all under the SIL Open Font Licence. (heading, body) pairs; the first is the default.
PAIRS = (
	("Poppins", "Inter"), ("Montserrat", "Open Sans"), ("Playfair Display", "Lato"), ("Oswald", "Roboto"),
	("Baloo 2", "Nunito"), ("DM Serif Display", "DM Sans"), ("Bebas Neue", "Montserrat"), ("Lora", "Source Sans 3"),
	("Raleway", "Roboto"), ("Merriweather", "Open Sans"), ("Archivo Black", "Archivo"), ("Pacifico", "Quicksand"),
)
SCRIPTS = {  # the face each script falls back to, heading then body
	"tamil": ("Baloo Thambi 2", "Noto Sans Tamil"),
	"devanagari": ("Baloo 2", "Noto Sans Devanagari"),
	"arabic": ("Cairo", "Noto Naskh Arabic"),
}
LANGUAGE_SCRIPT = {"tamil": "tamil", "hindi": "devanagari", "marathi": "devanagari", "arabic": "arabic", "urdu": "arabic"}
FONTS = sorted({f for pair in PAIRS for f in pair} | {f for pair in SCRIPTS.values() for f in pair})


def _known(name: str) -> str:
	n = re.sub(r"\s+", " ", str(name or "")).strip().lower()
	return next((f for f in FONTS if f.lower() == n), "")


def script_of(text_or_language: str) -> str | None:
	"""'Tamil' / 'हिंदी text' → the script it needs (None: Latin is enough)."""
	t = str(text_or_language or "")
	if t.strip().lower() in LANGUAGE_SCRIPT:
		return LANGUAGE_SCRIPT[t.strip().lower()]
	if re.search(r"[஀-௿]", t):
		return "tamil"
	if re.search(r"[ऀ-ॿ]", t):
		return "devanagari"
	if re.search(r"[؀-ۿ]", t):
		return "arabic"
	return None


def fonts(heading: str = "", body: str = "", language: str = "") -> dict:
	"""The brand's fonts (unknown names → the default pair), with the language's script faces behind them."""
	h, b = _known(heading), _known(body)
	if not h and not b:
		h, b = PAIRS[0]
	h, b = h or b, b or h
	script = script_of(language)
	sh, sb = SCRIPTS.get(script, ("", ""))
	families = [f for f in dict.fromkeys((h, b, sh, sb)) if f]
	url = "https://fonts.googleapis.com/css2?" + "&".join(
		"family=" + f.replace(" ", "+") + (":wght@400;600;700;800" if f not in ("Bebas Neue", "Archivo Black", "Pacifico") else "")
		for f in families) + "&display=block"
	stack = lambda first, alt: ", ".join(f"'{x}'" for x in (first, alt) if x) + ", sans-serif"  # noqa: E731
	return {"heading": h, "body": b, "css_heading": stack(h, sh), "css_body": stack(b, sb), "url": url, "script": script,
			"rtl": script == "arabic"}
