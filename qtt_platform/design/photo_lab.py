"""
QTT Studio › Photo Lab (PROJ-0012 S1) — the picture work, Pillow only (no Frappe; tests/test_photo_lab.py).

  enhance       light, colour and sharpness put right in one go (dark photos lifted, washed-out ones given depth)
  smart_crop    the photo cut to any size (square post, story, store product, website banner…) around its busiest part
  studio_shot   a cut-out product or person on a clean backdrop in the brand's colours, standing on a soft shadow
  on_scene      a cut-out placed on an AI-made empty scene (the scene is made without the product, so the product itself
                is never redrawn or changed — only the business's own photo is used)
  scene_prompt  what the AI is asked for: an empty surface, no products, people, text or logos

Upscaling and tap-to-select wait for the worker server.
"""

import io
import math

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

# key: (width, height, label) — every size a business asks for
SIZES = {
	"square": (1080, 1080, "Square post"),
	"portrait": (1080, 1350, "Portrait post"),
	"story": (1080, 1920, "Story / Status"),
	"wide": (1200, 628, "Link and Facebook"),
	"product": (1000, 1000, "Store product"),
	"banner": (1920, 640, "Website banner"),
	"profile": (640, 640, "Profile picture"),
}
BACKDROPS = {"white": "Clean white", "soft": "Soft brand tint", "brand": "Your colour", "dark": "Dark"}
# key: (label, the empty scene) — AI backgrounds (credits)
SCENES = {
	"marble": ("Marble table", "a white marble tabletop in a bright, airy room"),
	"wood": ("Wooden table", "a warm wooden table in a cosy café, the café softly blurred behind"),
	"studio": ("Pastel studio", "a seamless pastel paper studio backdrop curving into the floor"),
	"kitchen": ("Kitchen counter", "a clean kitchen counter, the kitchen softly blurred behind"),
	"nature": ("Garden", "a flat stone in a garden, soft green leaves blurred behind"),
	"festive": ("Festive", "a table with glowing diya lamps and marigold flowers softly blurred in the background, Indian festival mood"),
	"luxury": ("Luxury", "a dark velvet surface with soft golden bokeh lights behind"),
	"shop": ("Shop shelf", "a neat, softly lit shop shelf with the store blurred behind"),
}
# the AI's picture sizes (gpt-image-1), by the shape asked for
AI_SIZES = {"square": "1024x1024", "product": "1024x1024", "profile": "1024x1024", "portrait": "1024x1536", "story": "1024x1536",
			"wide": "1536x1024", "banner": "1536x1024"}
MAX_SIDE = 3000  # bigger photos are brought down first (phones send 4000+)


def _rgb(data: bytes) -> Image.Image:
	im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
	if im.mode in ("RGBA", "LA", "P"):
		im = im.convert("RGBA")
		bg = Image.new("RGB", im.size, "#ffffff")
		bg.paste(im, mask=im.getchannel("A"))
		im = bg
	im = im.convert("RGB")
	if max(im.size) > MAX_SIDE:
		im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
	return im


def _jpeg(im: Image.Image, quality: int = 92) -> bytes:
	out = io.BytesIO()
	im.convert("RGB").save(out, "JPEG", quality=quality, optimize=True, progressive=True)
	return out.getvalue()


def size_of(key: str) -> tuple[int, int]:
	w, h, _ = SIZES.get(key) or SIZES["square"]
	return w, h


def too_small(data: bytes, key: str) -> bool:
	"""The photo has fewer pixels than the size needs (it will look soft when made bigger)."""
	w, h = size_of(key)
	im = Image.open(io.BytesIO(data))
	return im.size[0] * im.size[1] < w * h * 0.5


# ---- enhance -----------------------------------------------------------------------------------------------------------
def brightness(im: Image.Image) -> float:
	return ImageStat.Stat(im.convert("L")).mean[0] / 255


def enhance(data: bytes) -> bytes:
	"""Light, colour and sharpness put right: contrast stretched (the darkest and lightest ½% clipped, colours kept true),
	a dark or washed-out photo brought towards a natural middle, colour a touch richer, a gentle sharpen. JPEG."""
	im = _rgb(data)
	im = ImageOps.autocontrast(im, cutoff=(0.5, 0.5), preserve_tone=True)
	lum = brightness(im)
	if lum < 0.38 or lum > 0.66:
		target = 0.47 if lum < 0.38 else 0.58
		g = max(0.55, min(1.7, math.log(target) / math.log(max(0.04, min(0.96, lum)))))
		lut = [round(255 * (i / 255) ** g) for i in range(256)]
		im = im.point(lut * 3)
	im = ImageEnhance.Color(im).enhance(1.10)
	im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
	return _jpeg(im)


# ---- smart crop --------------------------------------------------------------------------------------------------------
def _best_window(energy: list[float], window: int) -> int:
	"""Where a window of `window` cells catches the most detail along one line (a little pull to the middle)."""
	n = len(energy)
	if window >= n:
		return 0
	run = sum(energy[:window])
	best, at = -1.0, 0
	mid = (n - window) / 2
	total = sum(energy) or 1
	for i in range(0, n - window + 1):
		if i:
			run += energy[i + window - 1] - energy[i - 1]
		score = run / total - 0.08 * abs(i - mid) / max(1, n)
		if score > best:
			best, at = score, i
	return at


def crop_box(size: tuple[int, int], target: tuple[int, int], energy_cols: list[float] | None = None,
			 energy_rows: list[float] | None = None) -> tuple[int, int, int, int]:
	"""The crop (left, top, right, bottom) of an image `size` for the shape of `target`, placed where the detail is."""
	w, h = size
	ratio = target[0] / target[1]
	if w / h > ratio:  # too wide: choose along x
		cw, ch = round(h * ratio), h
		x = 0
		if energy_cols:
			x = round(_best_window(energy_cols, max(1, round(len(energy_cols) * cw / w))) * w / len(energy_cols))
		else:
			x = (w - cw) // 2
		x = max(0, min(w - cw, x))
		return x, 0, x + cw, ch
	cw, ch = w, round(w / ratio)
	if energy_rows:
		y = round(_best_window(energy_rows, max(1, round(len(energy_rows) * ch / h))) * h / len(energy_rows))
	else:
		y = (h - ch) // 3  # a little above the middle: heads and tops of products
	y = max(0, min(h - ch, y))
	return 0, y, cw, y + ch


def _energy(im: Image.Image) -> tuple[list[float], list[float]]:
	"""Detail along each column and row: edges, counted more where there's colour (the subject — food, a product — is
	busy AND colourful; a plain table is colourful but not busy, a window busy but grey)."""
	small = im.copy()
	small.thumbnail((240, 240))
	edges = small.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: min(255, v * 3))
	sat = small.convert("HSV").getchannel("S").point(lambda v: 70 + v * 0.72)
	both = ImageChops.multiply(edges, sat)
	w, h = both.size
	px = both.load()
	cols = [sum(px[x, y] for y in range(h)) for x in range(w)]
	rows = [sum(px[x, y] for x in range(w)) for y in range(h)]
	return cols, rows


def smart_crop(data: bytes, key: str) -> bytes:
	"""The photo cut to a size (SIZES) around where its detail is, then made exactly that size. JPEG."""
	im = _rgb(data)
	target = size_of(key)
	cols, rows = _energy(im)
	box = crop_box(im.size, target, cols, rows)
	return _jpeg(im.crop(box).resize(target, Image.LANCZOS))


# ---- studio shot -------------------------------------------------------------------------------------------------------
def _gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
	w, h = size
	mask = Image.linear_gradient("L").resize((w, h))
	return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)


def _glow(size: tuple[int, int], centre: str, edge: str) -> Image.Image:
	w, h = size
	mask = Image.radial_gradient("L").resize((round(max(w, h) * 1.5),) * 2)
	mask = mask.crop(((mask.size[0] - w) // 2, round((mask.size[1] - h) * 0.4), (mask.size[0] - w) // 2 + w, round((mask.size[1] - h) * 0.4) + h))
	return Image.composite(Image.new("RGB", size, edge), Image.new("RGB", size, centre), mask)


def backdrop(size: tuple[int, int], kind: str, pal: dict) -> Image.Image:
	"""The clean background for a studio shot, in the brand's colours."""
	from qtt_platform.design.base import mix

	if kind == "dark":
		return _glow(size, mix(pal["dark"], "#ffffff", 0.16), mix(pal["dark"], "#000000", 0.35))
	if kind == "brand":
		return _glow(size, mix(pal["primary"], "#ffffff", 0.22), pal["primary_deep"])
	if kind == "soft":
		return _gradient(size, pal["primary_soft"], mix(pal["primary_soft"], pal["primary"], 0.22))
	return _gradient(size, "#ffffff", "#e9ecef")


def _place(bg: Image.Image, cut: Image.Image, *, dark: bool) -> Image.Image:
	"""Stand the cut-out in the middle on a floor line, with a soft contact shadow under it and a faint one behind."""
	W, H = bg.size
	cut = cut.convert("RGBA")
	box = cut.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
	if box:
		cut = cut.crop(box)
	tall = H / W > 1.3
	max_w, max_h = W * (0.74 if W >= H else 0.80), H * (0.50 if tall else 0.66)
	s = min(max_w / cut.size[0], max_h / cut.size[1])
	cut = cut.resize((max(1, round(cut.size[0] * s)), max(1, round(cut.size[1] * s))), Image.LANCZOS)
	cw, ch = cut.size
	floor = round(H * (0.78 if tall else 0.84))
	x, y = (W - cw) // 2, floor - ch
	out = bg.convert("RGBA")
	strength = 70 if dark else 120
	# a soft shadow behind (the cut-out's own shape, blurred, a little lower)
	behind = Image.new("L", out.size, 0)
	behind.paste(cut.getchannel("A").point(lambda a: a * 45 // 255), (x + round(cw * 0.02), y + round(ch * 0.03)))
	behind = behind.filter(ImageFilter.GaussianBlur(max(4, round(cw * 0.03))))
	# a contact shadow where it stands
	contact = Image.new("L", out.size, 0)
	ew, eh = round(cw * 0.86), max(10, round(min(cw, ch) * 0.07))
	ImageDraw.Draw(contact).ellipse((W // 2 - ew // 2, floor - eh // 2, W // 2 + ew // 2, floor + eh // 2), fill=strength)
	contact = contact.filter(ImageFilter.GaussianBlur(max(6, round(eh * 0.6))))
	shadow = ImageChops.lighter(behind, contact)
	out = Image.composite(Image.new("RGBA", out.size, (0, 0, 0, 255)), out, shadow)
	out.alpha_composite(cut, (x, y))
	return out.convert("RGB")


def studio_shot(cutout_png: bytes, key: str, kind: str, pal: dict) -> bytes:
	"""A cut-out (product or person) on a clean backdrop (BACKDROPS) in the brand's colours, standing on a soft shadow. JPEG."""
	size = size_of(key)
	bg = backdrop(size, kind if kind in BACKDROPS else "white", pal)
	return _jpeg(_place(bg, Image.open(io.BytesIO(cutout_png)), dark=kind in ("dark", "brand")))


def on_scene(scene_bytes: bytes, cutout_png: bytes, key: str) -> bytes:
	"""A cut-out placed on an AI-made empty scene, the scene cut to the size first. JPEG."""
	size = size_of(key)
	bg = _rgb(scene_bytes)
	bg = bg.crop(crop_box(bg.size, size)).resize(size, Image.LANCZOS)
	return _jpeg(_place(bg, Image.open(io.BytesIO(cutout_png)), dark=brightness(bg) < 0.4))


def scene_prompt(scene: str, custom: str = "") -> str:
	"""The AI's brief for an empty scene. The product is never drawn — it's added afterwards from the business's photo."""
	what = (custom or "").strip()[:200] or (SCENES.get(scene) or SCENES["studio"])[1]
	return ("A realistic product-photography background: " + what + ". Seen from the front at table height, with clear empty "
			"space in the lower centre where a product will be placed later. Soft, even light, shallow depth of field, high "
			"quality. Empty: no products, no objects in the centre, no people, no hands, no text, no letters, no numbers, "
			"no logos, no watermarks.")
