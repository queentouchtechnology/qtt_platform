"""
Queen Touch Technology's own documents — invoices from QTT, QTT's quotes — in the look of Desk's print format "QTT
Proposal" (owner, 25 Nov 2026): the dark band with the logo, the "Prepared for" strip, dark table heads, the blue totals.
The styles are read from that print format, so a change there shows here; FALLBACK_CSS is used only if it's gone.
Other businesses' documents keep their own look (print_brand).
"""

import base64
import os
import re
from html import unescape

import frappe

FORMAT = "QTT Proposal"
_LOGO = os.path.join(os.path.dirname(__file__), "print_assets", "qtt-logo-dark.png")
MARGINS = {"page-size": "A4", "margin-top": "10mm", "margin-bottom": "12mm", "margin-left": "10mm", "margin-right": "10mm"}
FALLBACK_CSS = """
.qp, .qp td, .qp th, .qp div { font-family: Helvetica, Arial, sans-serif; color: #222; font-size: 12px; line-height: 1.5; }
.qp .hdr { background: #0d0f14; padding: 26px 30px 22px; } .qp .htitle { color: #4c8dff; font-weight: 700; font-size: 14px; margin-top: 12px; }
.qp .meta { width: 100%; margin: 20px 0 6px; } .qp .meta td { font-weight: 700; padding: 2px 10px; }
.qp .for { background: #f3f6fb; border-left: 3px solid #2f6fed; padding: 9px 14px; margin: 10px 0 0; }
.qp table.items { width: 100%; border-collapse: collapse; margin-top: 16px; border: 1px solid #d9d9d9; }
.qp table.items th { background: #0d0f14; color: #fff; text-align: left; padding: 9px 12px; }
.qp table.items td { padding: 9px 12px; border-bottom: 1px solid #dcdcdc; } .qp .r, .qp table.items th.r { text-align: right; white-space: nowrap; }
.qp .sum { width: 100%; border-collapse: collapse; margin-top: 18px; border: 1px solid #d9d9d9; } .qp .sum td { padding: 10px 12px; border-bottom: 1px solid #dcdcdc; }
.qp .sum tr.tot td { background: #e8f0fe; font-weight: 700; } .qp .foot { margin-top: 30px; padding-top: 14px; border-top: 1px solid #d0d0d0; }
"""

_HTML = """<style>{{ css }}
.qp .hdr img { height: 46px; display: block; }
.qp tr { page-break-inside: avoid; }
</style>
<div class="qp">
  <div class="hdr"><img src="{{ logo }}" alt="{{ b.name | e }}"><div class="htitle">{{ title | e }}</div></div>
  <table class="meta"><tr><td>{{ left | e }}</td><td style="text-align: right{% if color %}; color: {{ color }}{% endif %}">{{ right | e }}</td></tr></table>
  <div class="for"><b>{{ to_label | e }}:</b> {{ to | select | map("e") | join(" &nbsp;·&nbsp; ") }}</div>
  <table class="items">
    <tr>{% for c in columns %}<th{% if not loop.first %} class="r"{% endif %}>{{ c | e }}</th>{% endfor %}</tr>
    {% for r in rows %}<tr>{% for c in r %}<td{% if not loop.first %} class="r"{% endif %}>{% for line in c.splitlines() %}{% if loop.first %}{{ line | e }}{% else %}<div class="desc">{{ line | e }}</div>{% endif %}{% endfor %}</td>{% endfor %}</tr>{% endfor %}
  </table>
  <table class="sum">{% for label, value, strong in totals %}<tr{% if strong %} class="tot"{% endif %}><td>{{ label | e }}</td><td class="r">{{ value | e }}</td></tr>{% endfor %}</table>
  {% if note %}<div class="note">{{ note | e }}</div>{% endif %}
  {% if terms %}<h2>Terms</h2><div class="terms">{{ terms }}</div>{% endif %}
  {% if b.bank.number or b.bank.upi %}<div class="note">Payment:
    {% if b.bank.number %}{{ (b.bank.account_name or b.name) | e }} · {{ b.bank.bank | e }} · A/c {{ b.bank.number | e }}{% if b.bank.ifsc %} · IFSC {{ b.bank.ifsc | e }}{% endif %}{% endif %}
    {% if b.bank.upi %} · UPI {{ b.bank.upi | e }}{% endif %}</div>{% endif %}
  <div class="foot"><b>{{ b.name | e }} (QTT)</b><br>{{ b.address | map("e") | join(", ") }}<br>
    {{ contacts | select | map("e") | join(" &nbsp;|&nbsp; ") }}{% if b.gstin %}<br>GSTIN {{ b.gstin | e }}{% endif %}</div>
</div>
"""


def css_of(html: str | None) -> str:
	"""The styles of the print format; "" when it has none."""
	found = re.search(r"<style[^>]*>(.*?)</style>", html or "", re.S | re.I)
	return found.group(1).strip() if found else ""


def details(name: str, description: str | None) -> str:
	"""A service and its deliverables, one line each (• points on their own lines); just the name when they're the same."""
	text = re.sub(r"<br\s*/?>|</li>|</p>|</div>", "\n", description or "")
	lines = [" ".join(x.split()) for x in unescape(frappe.utils.strip_html(text)).replace("•", "\n•").split("\n")]
	return "\n".join([name] + [x for x in lines if x.strip("• ") and x != name])


def is_qtt(tenant: str | None) -> bool:
	from qtt_platform.api.leads import house_tenant

	return bool(tenant) and tenant == house_tenant()


def render(*, title: str, left: str, right: str, to_label: str, to: list, columns: list, rows: list, totals: list, note: str = "",
		   terms: str = "", color: str = "") -> bytes:
	"""One of QTT's documents as a PDF. rows: text cells under `columns` (a new line in the first one is small text under it); totals: (label, amount, strong). `terms` is the
	document's own safe HTML; everything else is escaped."""
	from frappe.utils.pdf import get_pdf

	from qtt_platform.api.leads import house_tenant
	from qtt_platform.print_brand import brand

	b = brand(tenant=house_tenant())
	with open(_LOGO, "rb") as f:
		logo = "data:image/png;base64," + base64.b64encode(f.read()).decode()
	css = css_of(frappe.db.get_value("Print Format", {"name": FORMAT, "disabled": 0}, "html")) or FALLBACK_CSS
	html = frappe.render_template(_HTML, {
		"css": css, "logo": logo, "b": b, "title": title, "left": left, "right": right, "to_label": to_label, "to": to, "columns": columns,
		"rows": rows, "totals": totals, "note": note, "terms": frappe.utils.sanitize_html(terms) if terms else "", "color": color,
		"contacts": [re.sub(r"^https?://", "", b.website or ""), b.email, b.phone],
	})
	return get_pdf(html, dict(MARGINS))
