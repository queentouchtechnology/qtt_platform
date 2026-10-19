"""
Rendering a library template into a picture (PROJ-0011 C) — the Frappe side of the design base.

render(...) builds the page from a template (layout + variant), a brand (palette colours, fonts, logo) and content, and
sends it with its pictures (logo, photos) to the renderer. Photos for samples come from the website / store kits
(qtt_services/wordpress/kit-images); a business's own photos come with its post (D).
"""

from pathlib import Path

import frappe

from qtt_platform.design import archetypes, base, catalog, layouts, render as renderer

SIZES = {"square": 1080, "portrait": 1350, "story": 1920}
EXTRA_FACES = ("Kaushan Script", "Caveat", "Bebas Neue", "Cinzel", "Great Vibes", "Lilita One", "Rubik Dirt", "Pacifico",
			   "Dancing Script", "Satisfy", "Anton")


def kit_root() -> Path | None:
	try:
		p = Path(frappe.get_app_path("qtt_services")) / "wordpress" / "kit-images"  # get_app_path would turn the "-" into "_"
	except Exception:
		return None
	return p if p.is_dir() else None


def kit_photos(kit: str, count: int = 5) -> list[tuple[str, bytes]]:
	"""Up to `count` photos of a kit (wide scenes first), as (file name, bytes)."""
	root = kit_root()
	if not root:
		return []
	d = root / kit if (root / kit).is_dir() else root / "other"
	files = sorted(f for f in d.iterdir() if f.suffix.lower() in (".webp", ".jpg", ".jpeg", ".png")) if d.is_dir() else []
	wide = [f for f in files if f.name.startswith(("hero", "banner", "about"))] + [f for f in files if not f.name.startswith(("hero", "banner", "about"))]
	return [(f"photo{k}{f.suffix.lower()}", f.read_bytes()) for k, f in enumerate(wide[:count])]


def page_for(layout: str, variant: dict, *, colors: dict, fonts: tuple[str, str], look: str, fmt: str, content: dict,
			 photo_names: list[str], language: str = "", out_width: int = 1080, edits: dict | None = None) -> tuple[str, int, int]:
	"""(html, width, height) of one post. `edits`: Studio's Move and resize changes ({format: {piece: …}})."""
	from qtt_platform.design import arrange

	hh = SIZES.get(fmt, 1080)
	p = base.palette(colors)
	f = base.fonts(fonts[0], fonts[1], language, extra=EXTRA_FACES)
	x = layouts.Ctx(palette=p, fonts=f, height=hh, look=look if look in layouts.LOOKS else "light", content=content, photos=photo_names)
	body, css = archetypes.LAYOUTS[layout](x, variant or {})
	out_h = round(out_width * hh / 1080)
	return layouts.page(body, css, x, out_width, out_h, arrange.script_for(edits, fmt)), out_width, out_h


def files_for(content: dict, photos: list[tuple[str, bytes]], logo: tuple[str, bytes] | None) -> tuple[dict, dict]:
	"""(the page's files by name, the content with the logo's file name)."""
	files = dict(photos)
	if logo and logo[1]:
		files[logo[0]] = logo[1]
		content = {**content, "logo": logo[0]}
	return files, content


def render(layout: str, variant: dict, *, colors: dict, fonts: tuple[str, str], look: str, fmt: str, content: dict,
		   photos: list[tuple[str, bytes]], logo: tuple[str, bytes] | None = None, language: str = "", out_width: int = 1080,
		   edits: dict | None = None) -> bytes:
	files, content = files_for(content, photos, logo)
	page, w, h = page_for(layout, variant, colors=colors, fonts=fonts, look=look, fmt=fmt, content=content,
						  photo_names=[n for n, _ in photos], language=language, out_width=out_width, edits=edits)
	return renderer.png(page, w, h, files)


def thumbnail(t: dict, group: str, out_width: int = 540) -> bytes:
	"""The library picture of a template for a business group: its showcase palette and fonts, the group's sample."""
	content = catalog.sample_for(t["layout"], group)
	photos = kit_photos(catalog.sample_kit(t["layout"], group), 5)
	return render(t["layout"], t["variant"], colors=catalog.PALETTES[t["palette"]], fonts=catalog.FONT_SETS[t["fonts"]], look=t["look"],
				  fmt="square", content=content, photos=photos, language="Tamil" if "லட்சம்" in str(content) else "", out_width=out_width)
