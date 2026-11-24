"""
QTT's invoice to a business as a PDF, in QTT's own look (logo, address, GSTIN) with the business it's for. The same PDF in
QTT Admin › Invoices (api.admin_invoices.pdf) and in the business's own Plans and billing (api.billing.invoice_pdf).
Whoever calls this has checked who may see the invoice.
"""

import frappe
from frappe.utils import formatdate, get_url, getdate, today

from qtt_platform import invoice_billing_rules as rules

_PDF_HTML = """
<div style="font-family: Helvetica, Arial, sans-serif; color: #1E293B; font-size: 12px; padding: 8px 4px">
  <table style="width: 100%; border-collapse: collapse"><tr>
    <td style="vertical-align: top">
      {% if logo %}<img src="{{ logo }}" style="max-height: 56px; max-width: 180px; margin-bottom: 6px"><br>{% endif %}
      <div style="font-size: 18px; font-weight: bold; color: {{ b.color }}">{{ b.name }}</div>
      {% for line in b.address %}<div style="color: #64748B">{{ line }}</div>{% endfor %}
      {% if b.gstin %}<div style="color: #64748B">GSTIN {{ b.gstin }}</div>{% endif %}
      <div style="color: #64748B">{{ [b.phone, b.email, b.website] | select | join(" · ") }}</div>
    </td>
    <td style="vertical-align: top; text-align: right">
      <div style="font-size: 22px; font-weight: bold; color: {{ b.color }}">INVOICE</div>
      <div style="color: #64748B">{{ inv.name }}</div>
      <div style="color: #64748B">{{ date }}</div>
      {% if due %}<div style="color: #64748B">Due {{ due }}</div>{% endif %}
      <div style="margin-top: 6px; font-weight: bold; color: {{ status_color }}">{{ status }}</div>
    </td>
  </tr></table>
  <div style="margin: 18px 0 10px; padding: 10px 12px; background: #F5F8FF; border-radius: 6px">
    <div style="color: #64748B; font-size: 11px">BILL TO</div>
    <div style="font-size: 14px; font-weight: bold">{{ to.name }}</div>
    {% for line in to.address %}<div style="color: #64748B">{{ line }}</div>{% endfor %}
    {% if to.gstin %}<div style="color: #64748B">GSTIN {{ to.gstin }}</div>{% endif %}
  </div>
  <table style="width: 100%; border-collapse: collapse">
    <tr style="background: {{ b.color }}; color: #FFFFFF">
      <th style="text-align: left; padding: 8px">#</th><th style="text-align: left; padding: 8px">Description</th>
      <th style="text-align: right; padding: 8px">Amount</th>
    </tr>
    {% for r in lines %}
    <tr style="border-bottom: 1px solid #E5E7EB">
      <td style="padding: 8px">{{ loop.index }}</td><td style="padding: 8px">{{ r.description }}</td>
      <td style="padding: 8px; text-align: right">{{ r.amount_text }}</td>
    </tr>
    {% endfor %}
  </table>
  <table style="width: 46%; margin-left: 54%; margin-top: 10px; border-collapse: collapse">
    <tr><td style="padding: 8px; font-weight: bold; border-top: 2px solid {{ b.color }}">Total</td>
        <td style="padding: 8px; text-align: right; font-weight: bold; font-size: 15px; border-top: 2px solid {{ b.color }}">{{ total }}</td></tr>
  </table>
  {% if paid %}<div style="margin-top: 18px; color: #15803D">Paid {{ paid }} — thank you.</div>
  {% elif void %}<div style="margin-top: 18px; color: #64748B">This invoice was cancelled. Nothing to pay.</div>
  {% else %}<div style="margin-top: 18px; color: #64748B">Pay in QTT OS › Business › Plans and billing.</div>{% endif %}
  <div style="margin-top: 28px; color: #64748B">Thank you — {{ b.name }}</div>
</div>
"""


def render(name: str) -> bytes:
	from frappe.utils.pdf import get_pdf

	from qtt_platform.api.leads import house_tenant
	from qtt_platform.leads_rules import money
	from qtt_platform.print_brand import brand

	inv = frappe.get_doc("QTT Invoice", name)
	b = brand(tenant=house_tenant())
	to = brand(tenant=inv.tenant)
	logo = b.logo if not b.logo or str(b.logo).startswith("http") else get_url(b.logo)
	cur = inv.currency or "INR"
	status = rules.shown_status(inv.status, getdate(inv.due_date) if inv.due_date else None, getdate(today()))
	paid_at = frappe.db.get_value("QTT Payment", {"invoice": name, "status": "succeeded"}, "paid_at", order_by="creation")
	html = frappe.render_template(_PDF_HTML, {
		"b": b, "logo": logo, "inv": inv,
		"to": {"name": frappe.db.get_value("QTT Tenant", inv.tenant, "tenant_name") or inv.tenant, "address": to.address, "gstin": to.gstin},
		"date": formatdate(inv.creation, "d MMM yyyy"), "due": formatdate(inv.due_date, "d MMM yyyy") if inv.due_date else "",
		"status": {"paid": "PAID", "overdue": "OVERDUE", "void": "VOID"}.get(status, "DUE"),
		"status_color": {"paid": "#15803D", "overdue": "#B91C1C", "void": "#64748B"}.get(status, "#1E293B"),
		"lines": [{"description": r.description, "amount_text": money(r.amount or 0, cur)} for r in inv.items],
		"total": money(inv.amount or 0, cur), "paid": formatdate(paid_at, "d MMM yyyy") if paid_at else None, "void": status == "void",
	})
	return get_pdf(html, {"page-size": "A4", "margin-top": "12mm", "margin-bottom": "12mm", "margin-left": "12mm", "margin-right": "12mm"})


def respond(name: str) -> None:
	frappe.local.response.filename = f"{name}.pdf"
	frappe.local.response.filecontent = render(name)
	frappe.local.response.type = "pdf"
