"""
QTT Studio › Poster variations (PROJ-0012 S10) — the decisions, pure (no Frappe; tests/test_showcase.py): which
directions to make for the owner's content, their words cleaned, and each concept's colours.
"""

from qtt_platform.design import palettes, showcase
from qtt_platform.studio import rules

MAX_BYTES = 10 * 1024 * 1024
MAX_SHOTS = 3
MAX_CONCEPTS = 8
SMALL = 1200  # a screenshot shorter than this looks soft on a 1080-wide poster
UPSCALE_TO = 1800  # a small screenshot is enlarged to this long side at upload (TASK-217)
FITS = ("top", "middle", "bottom", "whole")
BACKDROP = ("scene_device", "chips_cloud", "open_book")  # the directions that show a background picture

# The order directions are suggested in when the owner doesn't choose: the strongest first, different kinds of
# composition next to each other (reviewed on real screenshots — see the S10 report).
SUGGESTED = ("ui_showcase", "laptop_showcase", "before_after", "tablet_showcase", "device_tilt", "split_benefits", "stat_hero", "pop_cards", "magazine_cover", "glass_cards", "chips_cloud",
			 "timeline_steps", "cinematic", "minimal_device", "bold_promo", "globe_reach", "editorial", "screen_pop", "steps_flow",
			 "stat_badge", "product_stage", "connected_chips", "tilt_premium", "swiss_grid", "big_type", "color_blocks", "duo_screens",
			 "ui_orbit", "diagonal_layers", "full_phone", "scene_device", "open_book", "pill_rows", "problem_solution_ui")


def clean_brief(d: dict) -> dict:
	"""The owner's words for the posters → known slots only (headline, kicker, subline, cta, points, number, chips,
	steps, problems)."""
	words = rules.clean_words({**d, "items": [{"title": t} if isinstance(t, str) else t for t in (d.get("items") or [])]})
	if words.get("stat") and not words.get("stat_label"):
		words.pop("stat")  # a number alone says nothing — it needs what it counts
	return words


def clean_media(d: dict, shots: int) -> dict:
	"""How the screenshots sit (TASK-218/219): fit — per screenshot, top / middle / bottom / whole (anything else: top);
	clear — keep the screen clear of cards and points."""
	fits = d.get("fit") if isinstance(d.get("fit"), list) else []
	out = {"fit": [f if f in FITS else "top" for f in fits[:shots]]}
	out["fit"] += ["top"] * (shots - len(out["fit"]))
	out["clear"] = str(d.get("clear") or "").lower() in ("1", "true")
	return out


def upscale(data: bytes) -> tuple[bytes, int, int] | None:
	"""A small screenshot (both sides under SMALL) enlarged so it stays sharp on the poster: Lanczos to UPSCALE_TO on the
	long side and a light sharpen, as PNG. None when it is big enough (kept exactly as it is)."""
	import io

	from PIL import Image, ImageFilter

	im = Image.open(io.BytesIO(data))
	w, h = im.size
	if w >= SMALL or h >= SMALL:
		return None
	k = UPSCALE_TO / max(w, h)
	im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
	big = im.resize((round(w * k), round(h * k)), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
	buf = io.BytesIO()
	big.save(buf, "PNG", optimize=True)
	return buf.getvalue(), big.size[0], big.size[1]


def pick_directions(asked: list, words: dict, shots: int, on: dict, count: int) -> list[str]:
	"""The directions to make: the ones asked for that this content can fill (in that order), else the suggested order —
	only directions whose needs are met (a number, steps, chips, two screens…)."""
	usable = [k for k in (asked or SUGGESTED) if k in on and k in showcase.DIRECTIONS and showcase.can_use(k, words, shots)]
	return usable[:count]


def colour_sets(choice: str, has_brand: bool, ranked: list[str], n: int) -> list[str | None]:
	"""Each concept's colours: None = the business's own brand. 'brand' (or nothing chosen, with a brand) → all brand;
	'auto' (or no brand) → the colour sets that suit the screenshot best, one per concept; a set's key → that one."""
	if choice in palettes.CURATED:
		return [choice] * n
	if choice == "brand" or (not choice and has_brand):
		return [None] * n
	return [ranked[i % len(ranked)] for i in range(n)]
