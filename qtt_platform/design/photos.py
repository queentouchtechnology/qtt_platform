"""
Photo backgrounds (PROJ-0011 B): the hand-picked free photos (Pexels, Unsplash, Pixabay) and the earlier made photos
that the website and store kits already carry, by business type — qtt_services/wordpress/kit-images/<kit>/manifest.json.
A post on a photo always gets a scrim in the brand's own dark colour so its words read; the photo is never a logo,
a brand mark or a recognisable face (the kits were picked that way).
"""

import json
from pathlib import Path

ROLES = ("hero", "about", "banner", "section", "category", "product")


def _role(file: str) -> str:
	f = file.lower()
	for r, starts in (("hero", "hero"), ("about", "about"), ("banner", "banner"), ("category", "cat-")):
		if f.startswith(starts):
			return r
	return "product" if "-" in f else "section"


def library(root: Path) -> dict[str, list[dict]]:
	"""{kit: [{file, role}]} for every kit folder with pictures (manifest or not)."""
	out = {}
	root = Path(root)
	if not root.is_dir():
		return out
	for d in sorted(p for p in root.iterdir() if p.is_dir()):
		files = sorted(f.name for f in d.iterdir() if f.suffix.lower() in (".webp", ".jpg", ".jpeg", ".png"))
		if files:
			out[d.name] = [{"file": f, "role": _role(f)} for f in files]
	return out


def pick(lib: dict, kit: str, *, role: str | None = None, seed: int = 0) -> dict | None:
	"""One photo for a kit (its heroes, banners and about first — wide scenes suit backgrounds), the same for the same
	seed; another kit's when this one has none."""
	rows = lib.get(kit) or lib.get("other") or next(iter(lib.values()), [])
	if not rows:
		return None
	wide = [r for r in rows if r["role"] in (("hero", "banner", "about", "section") if role is None else (role,))] or rows
	return {"kit": kit if lib.get(kit) else None, **wide[seed % len(wide)]}


def scrim(palette: dict, strength: float = 0.55) -> str:
	"""The CSS gradient laid over a photo: the brand's dark colour, strongest where the words go (bottom)."""
	from qtt_platform.design.base import _rgb

	r, g, b = (round(x * 255) for x in _rgb(palette["dark"]))
	s = max(0.2, min(0.85, strength))
	return f"linear-gradient(180deg, rgba({r},{g},{b},{s * .35:.2f}) 0%, rgba({r},{g},{b},{s:.2f}) 70%, rgba({r},{g},{b},{min(.92, s + .2):.2f}) 100%)"


def manifest_sources(root: Path, kit: str) -> dict:
	"""Where the kit's pictures came from (for QTT Admin's credits view)."""
	m = Path(root) / kit / "manifest.json"
	try:
		return json.loads(m.read_text(encoding="utf-8")).get("made", {})
	except (OSError, ValueError):
		return {}
