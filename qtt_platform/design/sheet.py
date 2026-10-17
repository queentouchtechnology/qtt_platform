"""
Pages for the renderer (PROJ-0011 B): page() wraps any design in a full HTML document at its exact size (fonts loaded,
right-to-left for Arabic); brand_sheet() is the "See your brand" preview — the palette, the fonts, every pattern and
element in the business's own colours, with its logo as it is.
"""

import html

from qtt_platform.design import base, elements, patterns


def page(body: str, width: int, height: int, f: dict, *, extra_css: str = "") -> str:
	"""A whole HTML page the renderer screenshots at width × height."""
	return (
		"<!doctype html><html" + (' dir="rtl"' if f.get("rtl") else "") + "><head><meta charset=\"utf-8\">"
		+ "".join(f'<link rel="stylesheet" href="{html.escape(u, quote=True)}">' for u in f.get("urls") or [f["url"]]) +
		"<style>*{box-sizing:border-box;margin:0;padding:0}"
		f"html,body{{width:{width}px;height:{height}px;overflow:hidden}}"
		f":root{{--font-heading:{f['css_heading']};--font-body:{f['css_body']}}}"
		"body{font-family:var(--font-body);-webkit-font-smoothing:antialiased}"
		"h1,h2,h3,.h{font-family:var(--font-heading)}" + extra_css + "</style></head>"
		f"<body>{body}</body></html>"
	)


SHEET_W = 1200


def brand_sheet(*, business: str, colors: dict, logo_file: str | None, font_heading: str = "", font_body: str = "",
				language: str = "") -> tuple[str, int, int]:
	"""(html, width, height) of the brand preview. logo_file: the logo's file name sent beside the page (as it is)."""
	p = base.palette(colors)
	f = base.fonts(font_heading, font_body, language)
	cell, gap, cols = 252, 18, 4
	names = list(patterns.PATTERNS)
	rows_p = -(-len(names) // cols)
	swatches = "".join(
		f'<div class="sw"><div class="chip" style="background:{p[k]};color:{p["on_" + k]}">Aa</div>'
		f'<b>{label}</b><span>{p[k]}{" · yours" if k in p["owner"] else ""}</span></div>'
		for k, label in (("primary", "Main"), ("secondary", "Second"), ("accent", "Accent"), ("dark", "Dark"), ("light", "Light")))
	pats = "".join(
		f'<div class="pt">{patterns.pattern(n, p, cell, cell, base=("light", "primary", "dark")[i % 3], seed=i)}'
		f'<span>{html.escape(patterns.PATTERNS[n][0])}</span></div>' for i, n in enumerate(names))
	els = "".join(
		f'<div class="el">{elements.element(n, p, 200, 90 if n in ("price_tag", "ribbon", "pill") else 120, text=t, tone=tone)}</div>'
		for n, t, tone in (("badge", "NEW", "accent"), ("price_tag", "₹120", "primary"), ("ribbon", "Open today", "accent"),
						   ("starburst", "Fresh", "primary"), ("pill", "Call us", "dark"), ("icon_phone", "", "primary"),
						   ("icon_pin", "", "accent"), ("icon_truck", "", "primary"), ("swash", "", "accent"), ("sparkle", "", "accent")))
	logo = (f'<img class="logo" src="{html.escape(logo_file, quote=True)}">' if logo_file else
			f'<div class="logo name h">{html.escape(business)}</div>')
	rows_e = -(-10 // 5)
	height = 96 + 150 + 175 + 160 + 80 + rows_p * (cell + 44) + 80 + rows_e * 152 + 120
	css = (
		f"body{{background:{p['light']};color:{p['dark']};padding:48px}}"
		f".top{{display:flex;align-items:center;gap:28px;margin-bottom:30px}}.logo{{max-height:110px;max-width:320px;object-fit:contain}}"
		f".name{{font-size:44px;font-weight:800;color:{p['primary']}}}.top h1{{font-size:40px}}.top p{{font-size:20px;opacity:.75}}"
		f".row{{display:flex;gap:{gap}px;flex-wrap:wrap}}.sw{{width:200px}}.chip{{height:110px;border-radius:18px;display:flex;align-items:center;"
		f"justify-content:center;font:800 40px var(--font-heading);box-shadow:0 2px 8px rgba(0,0,0,.08)}}.sw b{{display:block;margin-top:8px;font-size:18px}}"
		f".sw span{{font-size:15px;opacity:.7}}h2{{font-size:26px;margin:34px 0 16px}}"
		f".pt{{width:{cell}px}}.pt svg{{border-radius:16px;display:block}}.pt span{{display:block;font-size:16px;margin:8px 0 14px}}"
		f".el{{width:200px;height:130px;display:flex;align-items:center;justify-content:center;background:#fff;border-radius:16px}}"
		f".type .h{{font-size:46px;font-weight:800;color:{p['primary']}}}.type p{{font-size:22px;margin-top:6px}}"
	)
	body = (
		f'<div class="top">{logo}<div>' + (f'<h1 class="h">{html.escape(business)}</h1>' if logo_file else "")
		+ '<p>Your brand kit — every post uses only these</p></div></div>'
		f'<div class="row">{swatches}</div>'
		f'<div class="type"><h2>Fonts</h2><div class="h">{html.escape(f["heading"])} for headings</div>'
		f'<p>{html.escape(f["body"])} for everything else — fresh today, open till 10 pm.</p></div>'
		f'<h2>Patterns</h2><div class="row">{pats}</div><h2>Elements</h2><div class="row">{els}</div>'
	)
	return page(body, SHEET_W, height, f, extra_css=css), SHEET_W, height
