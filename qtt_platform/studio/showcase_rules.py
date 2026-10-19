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
BACKDROP = ("scene_device", "chips_cloud", "open_book")  # the directions that show a background picture

# The order directions are suggested in when the owner doesn't choose: the strongest first, different kinds of
# composition next to each other (reviewed on real screenshots — see the S10 report).
SUGGESTED = ("ui_showcase", "device_tilt", "split_benefits", "stat_hero", "pop_cards", "magazine_cover", "glass_cards", "chips_cloud",
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
