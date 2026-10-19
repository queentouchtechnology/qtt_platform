"""
The functions every print format can call (hooks.jinja › methods — Frappe makes each function here a template global by
its own name): qtt_brand(company), qtt_gst_summary(doc), qtt_hsn(item_code). The work is in print_brand.py.

Only these three functions belong in this module: Frappe adds every function in it to every template.
"""


def qtt_brand(company=None, tenant=None):
	"""The business's logo, name, details, bank, colour and document style for a document's header and footer."""
	from qtt_platform.print_brand import brand

	return brand(company, tenant)


def qtt_gst_summary(doc):
	"""HSN-wise taxable value and CGST / SGST / IGST of an invoice-like document."""
	from qtt_platform.print_brand import gst_summary

	return gst_summary(doc)


def qtt_hsn(item_code):
	"""An item's HSN/SAC code ("" when unknown)."""
	from qtt_platform.print_brand import hsn

	return hsn(item_code)
