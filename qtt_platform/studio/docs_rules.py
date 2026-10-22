"""
QTT Studio › Business documents (PROJ-0012 S3) — the pure rules. No Frappe; tests/test_docs_rules.py.

Every PDF a business prints (Orbitra invoices, quotations, challans, receipts; Office Pulse payslips, letters, ID cards)
uses one letterhead from templates/print/qtt.html. QTT's own style ("band": a dark band with the logo) is free for
everyone; the other styles are chosen in QTT Studio and need it — a business whose Studio ends goes back to "band".

  STYLES          the letterhead styles: key → (name, what it looks like)
  style_for       the style a business's PDFs use (its choice only while it has Studio)
  colours         the colours a style is drawn with, from the brand colour (text on it readable)
  letter_prompt   AI writes a letter from a few words and the business brief — never inventing facts
  parse_letter    the AI's answer → {subject, body}
"""

import json
import re

DEFAULT = "band"
STYLES = {
	"band": ("QTT dark band", "A dark band with your logo and name, a line in your colour"),
	"clean": ("Clean", "White and light: your name in your colour, a thin line, your details on the right"),
	"colour": ("Your colour", "A band in your own colour with your logo and name"),
	"classic": ("Classic letterhead", "Logo and name in the middle, your details below, a double line"),
	# premium (2026): the same tables-only page, finer type and colour
	"luxe": ("Luxe", "Centred serif name in spaced capitals between fine double lines — for jewellers, hotels, firms"),
	"modern": ("Modern block", "Your logo and name on a block of your colour, the document title on a soft tint"),
	"gradient": ("Gradient band", "A rich band that deepens from your colour, your logo on white"),
}
MAX_BODY = 6000


def style_for(saved: str | None, has_studio: bool) -> str:
	"""The style the business's PDFs use: its own choice while it has Studio, else QTT's free one."""
	return saved if has_studio and saved in STYLES else DEFAULT


def _rgb(h: str) -> tuple[float, float, float]:
	h = h.lstrip("#")
	return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _lum(h: str) -> float:
	def ch(c):
		return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

	r, g, b = (ch(c) for c in _rgb(h))
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(a: str, b: str, t: float) -> str:
	x, y = _rgb(a), _rgb(b)
	return "#" + "".join(f"{round((x[i] * (1 - t) + y[i] * t) * 255):02x}" for i in range(3))


def colours(color: str, style: str) -> dict:
	"""{head_bg, head_ink, head_muted, th_bg, th_ink, soft, tint, deep} for a style and a brand colour (#rrggbb) — every
	style the same keys (tint: a pale wash of the colour; deep: the colour darkened, for gradients)."""
	c = _colours(color, style)
	c.setdefault("tint", _mix(color, "#ffffff", 0.88))
	c.setdefault("deep", _mix(color, "#0B0D12", 0.55))
	return c


def _colours(color: str, style: str) -> dict:
	dark = "#0B0D12"
	L = _lum(color)
	on = "#ffffff" if 1.05 / (L + 0.05) >= (L + 0.05) / (_lum(dark) + 0.05) else dark  # whichever reads better on it
	soft = _mix(color, "#ffffff", 0.9)
	if style == "colour":
		return {"head_bg": color, "head_ink": on, "head_muted": _mix(on, color, 0.35), "th_bg": color, "th_ink": on, "soft": soft}
	if style == "clean":
		return {"head_bg": "#ffffff", "head_ink": dark, "head_muted": "#5b6475", "th_bg": soft, "th_ink": dark, "soft": soft}
	if style == "classic":
		return {"head_bg": "#ffffff", "head_ink": dark, "head_muted": "#5b6475", "th_bg": dark, "th_ink": "#ffffff", "soft": soft}
	if style == "luxe":
		return {"head_bg": "#ffffff", "head_ink": dark, "head_muted": "#6b6457", "th_bg": _mix(color, dark, 0.35), "th_ink": "#ffffff",
				"soft": _mix(color, "#ffffff", 0.93)}
	if style == "modern":
		return {"head_bg": color, "head_ink": on, "head_muted": _mix(on, color, 0.3), "th_bg": color, "th_ink": on, "soft": soft,
				"tint": _mix(color, "#ffffff", 0.88)}
	if style == "gradient":
		deep = _mix(color, dark, 0.55)
		return {"head_bg": color, "head_ink": "#ffffff", "head_muted": "#e6e9f2", "th_bg": deep, "th_ink": "#ffffff", "soft": soft, "deep": deep}
	return {"head_bg": dark, "head_ink": "#ffffff", "head_muted": "#aeb6c6", "th_bg": dark, "th_ink": "#ffffff", "soft": "#EEF1FF"}


# ---- AI: write a letter ---------------------------------------------------------------------------------------------
def letter_prompt(*, request: str, to: str, brief: str, language: str) -> list[dict]:
	"""A short request ("thank a customer for a big order", "tell staff the office is closed on Monday") → a letter."""
	return [
		{"role": "system", "content": (
			"You write one short business letter for a small business, to be printed on its letterhead. Use ONLY the facts in "
			"the business brief and the request — never invent prices, dates, numbers, names, offers or promises; where a "
			"fact is needed but not given, write [ ] for the owner to fill in. Plain, warm, professional; 2 to 5 short "
			"paragraphs; no letterhead, address block, date or signature (they are added). "
			f"Write in {'Tamil' if language == 'ta' else 'English'}. "
			'Reply with JSON only: {"subject": "...", "greeting": "Dear ...,", "body": "paragraphs separated by blank lines", '
			'"closing": "Warm regards,"}.')},
		{"role": "user", "content": f"Business brief:\n{brief}\n\nThe letter is to: {(to or 'the reader').strip()[:120]}\n\n"
									f"What it should say: {(request or '').strip()[:500]}"},
	]


def parse_letter(text: str) -> dict | None:
	"""The AI's answer → {subject, greeting, body, closing}; None without a body."""
	m = re.search(r"\{.*\}", text or "", re.S)
	try:
		d = json.loads(m.group(0)) if m else {}
	except ValueError:
		return None
	if not isinstance(d, dict) or not str(d.get("body") or "").strip():
		return None
	return {"subject": str(d.get("subject") or "").strip()[:160], "greeting": str(d.get("greeting") or "").strip()[:120],
			"body": str(d["body"]).strip()[:MAX_BODY], "closing": str(d.get("closing") or "").strip()[:80]}


def paragraphs(body: str) -> list[str]:
	"""A letter's words → its paragraphs (blank lines between; single line breaks kept inside a paragraph)."""
	return [p.strip() for p in re.split(r"\n\s*\n", (body or "").strip()) if p.strip()]
