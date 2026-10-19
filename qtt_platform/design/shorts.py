"""
QTT Studio › Shorts (PROJ-0012 S6) — 9:16 videos (1080 × 1920) for Reels, YouTube Shorts and WhatsApp Status, made from
the business's own photos: each photo a scene with a slow zoom and its caption, the first with the hook, then a brand end
card (logo, a line, phone and website). Words are drawn as pictures by the renderer (brand fonts, Tamil shaped
properly); the video is put together here with FFmpeg (imageio-ffmpeg's own binary). No Frappe; tests/test_shorts.py.

  overlay_page   a scene's words as a transparent 1080 × 1920 page (hook big at the top, the caption in a band below)
  end_page       the end card as a page
  timing         how long each scene and the end card run
  build          photos + overlays + end card → an MP4 (H.264, a silent sound track so every app takes it)
  clean_script   the words checked (hook, up to 4 captions, end line)
"""

import html
import io
import re
import subprocess

W, H, FPS = 1080, 1920, 30
SCENE_S, END_S, MAX_SCENES = 2.8, 2.2, 4


def _e(t) -> str:
	return html.escape(str(t or ""), quote=True)


def _rich(t) -> str:
	return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", _e(t)).replace("\n", "<br>")


def clean_script(d: dict) -> dict:
	"""{hook, captions: [..up to 4], end_line} — trimmed, nothing empty kept."""
	d = d if isinstance(d, dict) else {}
	caps = [re.sub(r"\s+", " ", str(c or "")).strip()[:90] for c in (d.get("captions") or [])][:MAX_SCENES]
	return {"hook": re.sub(r"\s+", " ", str(d.get("hook") or "")).strip()[:70], "captions": caps,
			"end_line": re.sub(r"\s+", " ", str(d.get("end_line") or "")).strip()[:70]}


def timing(scenes: int) -> tuple[float, float]:
	"""(the whole video's seconds, one scene's seconds)."""
	n = max(1, min(scenes, MAX_SCENES))
	return round(n * SCENE_S + END_S, 2), SCENE_S


def _head(fonts: dict, pal: dict) -> str:
	links = "".join(f'<link rel="stylesheet" href="{_e(u)}">' for u in (fonts.get("urls") or [fonts.get("url")]) if u)
	from qtt_platform.design.base import mix

	accent = pal["accent"] if "accent" in (pal.get("owner") or []) else pal["primary"]
	bright = mix(accent, "#ffffff", 0.45)  # the starred word on the dark caption band
	return (f'<!doctype html><html><head><meta charset="utf-8">{links}<style>*{{margin:0;padding:0;box-sizing:border-box}}'
			f"html,body{{width:{W}px;height:{H}px;background:transparent;overflow:hidden}}"
			f"body{{font-family:{fonts['css_body']};position:relative}}"
			f".hook{{position:absolute;left:70px;right:70px;top:170px;font-family:{fonts['css_heading']};font-weight:800;font-size:92px;"
			f"line-height:1.05;color:#fff;text-shadow:0 4px 24px rgba(0,0,0,.55)}}.hook em{{font-style:normal;color:{_e(accent)};"
			f"background:#fff;padding:0 14px;border-radius:12px;text-shadow:none}}"
			f".cap{{position:absolute;left:60px;right:60px;bottom:250px;padding:30px 38px;border-radius:28px;background:rgba(0,0,0,.62);"
			f"color:#fff;font-weight:700;font-size:56px;line-height:1.2;text-align:center}}.cap em{{font-style:normal;color:{_e(bright)}}}"
			"</style></head>")


_READY = "<script>(async()=>{try{await document.fonts.ready}catch(e){}window.qttReady=true})()</script>"


def overlay_page(caption: str, pal: dict, fonts: dict, *, hook: str = "") -> str:
	"""A scene's words as a transparent page: the hook (first scene) and the caption."""
	parts = (f'<div class="hook">{_rich(hook)}</div>' if hook else "") + (f'<div class="cap">{_rich(caption)}</div>' if caption else "")
	return f"{_head(fonts, pal)}<body>{parts}{_READY}</body></html>"


def end_page(name: str, line: str, phone: str, website: str, pal: dict, fonts: dict, *, logo: str | None = None) -> str:
	"""The end card: the brand's colour, logo, the business name, a line, phone and website."""
	logo_html = (f'<img src="{_e(logo)}" style="max-width:420px;max-height:300px;object-fit:contain;background:#fff;padding:24px;border-radius:36px;margin-bottom:60px">'
				 if logo else "")
	contact = "<br>".join(_e(x) for x in (phone, website) if x)
	return (f"{_head(fonts, pal)}<body style=\"background:{_e(pal['primary'])};color:{_e(pal['on_primary'])};display:flex;flex-direction:column;"
			f'align-items:center;justify-content:center;text-align:center;padding:120px">{logo_html}'
			f'<div style="font-family:{fonts["css_heading"]};font-weight:800;font-size:84px;line-height:1.1">{_e(name)}</div>'
			f'<div style="width:160px;height:8px;border-radius:4px;background:{_e(pal["on_primary"])};opacity:.6;margin:46px auto"></div>'
			f'<div style="font-size:54px;font-weight:600;line-height:1.3">{_rich(line)}</div>'
			f'<div style="font-size:46px;margin-top:60px;opacity:.92;line-height:1.5">{contact}</div>{_READY}</body></html>')


def _cover(im, Image):
	s = max(W / im.width, H / im.height) * 1.1  # 10% room for the zoom
	return im.convert("RGB").resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def build(photos: list[bytes], overlays: list[bytes], end_card: bytes, ffmpeg: str) -> bytes:
	"""The MP4: each photo with a slow zoom (in, then out, alternating) under its overlay; then the end card. A silent
	sound track is added so Instagram, YouTube and WhatsApp all accept it."""
	import os
	import tempfile

	from PIL import Image

	n = max(1, min(len(photos), MAX_SCENES))
	total, per = timing(n)
	base = [_cover(Image.open(io.BytesIO(p)), Image) for p in photos[:n]]
	over = [Image.open(io.BytesIO(o)).convert("RGBA").resize((W, H)) for o in overlays[:n]]
	card = Image.open(io.BytesIO(end_card)).convert("RGB").resize((W, H))
	out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
	out.close()
	cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
		   "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-map", "0:v", "-map", "1:a", "-shortest",
		   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "96k",
		   "-t", f"{total}", "-movflags", "+faststart", out.name]
	p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
	last = card  # the frame the end card fades in from (set by each scene)
	try:
		for fr in range(int(total * FPS)):
			t = fr / FPS
			if t >= n * per:
				# the end card fades in over 0.3 s
				k = min(1.0, (t - n * per) / 0.3)
				img = Image.blend(last, card, k) if k < 1 else card
			else:
				i = min(int(t / per), n - 1)
				k = (t - i * per) / per
				z = 1.0 + 0.09 * k if i % 2 == 0 else 1.09 - 0.09 * k
				b = base[i]
				# the photo was made to cover 1.1 × the frame: at zoom 1 the window is the frame's shape × 1.1, smaller as it zooms
				cw, ch = W * 1.1 / z, H * 1.1 / z
				cx, cy = b.width / 2, b.height / 2
				frame = b.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))).resize((W, H), Image.BILINEAR)
				img = Image.alpha_composite(frame.convert("RGBA"), over[i]).convert("RGB")
				last = img
			p.stdin.write(img.tobytes())
		p.stdin.close()
		err = p.stderr.read().decode("utf-8", "replace")
		if p.wait() != 0:
			raise RuntimeError(f"ffmpeg failed: {err[-400:]}")
		with open(out.name, "rb") as f:
			return f.read()
	finally:
		try:
			os.unlink(out.name)
		except OSError:
			pass
