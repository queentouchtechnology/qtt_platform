"""
QTT Studio › quality (PROJ-0012 S9) — what the nightly check looks for in a template's picture (no Frappe;
tests/test_quality.py): the renderer drew it, at the size asked, and it isn't blank (one flat colour — a page that failed
quietly). Every enabled template is drawn in every size each night; problems show in QTT Admin › Studio and on its home.
"""

import io

SIZES = {"square": (540, 540), "portrait": (540, 675), "story": (540, 960)}


def picture_problem(png: bytes, width: int, height: int) -> str | None:
	"""What's wrong with a drawn template picture, or None when it's fine."""
	from PIL import Image, ImageStat

	try:
		im = Image.open(io.BytesIO(png)).convert("RGB")
	except Exception:
		return "not a picture"
	if im.size != (width, height):
		return f"wrong size {im.size[0]}×{im.size[1]} (wanted {width}×{height})"
	small = im.resize((64, 64))
	spread = max(ImageStat.Stat(small).stddev)
	if spread < 4:
		return "blank — one flat colour"
	edges = sum(ImageStat.Stat(small.convert("L").point(lambda v: 255 if v > 0 else 0)).mean)
	if edges <= 0:
		return "blank — all black"
	return None


def summary(rows: list[dict]) -> dict:
	"""{ok, problem, unchecked} counts of template rows (check_status)."""
	out = {"ok": 0, "problem": 0, "unchecked": 0}
	for r in rows:
		out[r.get("check_status") if r.get("check_status") in ("ok", "problem") else "unchecked"] += 1
	return out
