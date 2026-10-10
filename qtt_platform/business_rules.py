"""
Pure checks for business and customer profiles (no Frappe imports, so they
are unit-tested directly). Each `clean_*` returns the normalised value, or
raises ProfileError with a message the app shows as is.
"""

import re

GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# GST state codes (first two digits of a GSTIN).
GST_STATES = {
	"01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
	"06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
	"12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
	"18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
	"24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
	"30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
	"35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
}

_GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_UPI = re.compile(r"^[A-Za-z0-9._\-]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_URL = re.compile(r"^https?://[^\s/$.?#][^\s]*\.[^\s]{2,}$", re.I)
_PINCODE = re.compile(r"^[1-9]\d{5}$")
_ACCOUNT = re.compile(r"^\d{6,18}$")


class ProfileError(ValueError):
	pass


def _text(v) -> str:
	return (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


def gstin_check_char(first14: str) -> str:
	total = 0
	for i, c in enumerate(first14):
		p = GST_CHARS.index(c) * (2 if i % 2 else 1)
		total += p // 36 + p % 36
	return GST_CHARS[(36 - total % 36) % 36]


def clean_gstin(v) -> str | None:
	g = _text(v).upper().replace(" ", "")
	if not g:
		return None
	if not _GSTIN.match(g) or g[:2] not in GST_STATES:
		raise ProfileError("GSTIN must look like 33ABCDE1234F1Z5 (15 characters).")
	if gstin_check_char(g[:14]) != g[14]:
		raise ProfileError("This GSTIN's last character doesn't match. Check for a typing mistake.")
	return g


def gst_state(gstin: str | None) -> str | None:
	return GST_STATES.get(gstin[:2]) if gstin else None


def clean_pan(v) -> str | None:
	p = _text(v).upper().replace(" ", "")
	if not p:
		return None
	if not _PAN.match(p):
		raise ProfileError("PAN must look like ABCDE1234F.")
	return p


def check_gstin_pan(gstin: str | None, pan: str | None):
	if gstin and pan and gstin[2:12] != pan:
		raise ProfileError("The PAN doesn't match the GSTIN (characters 3–12 of a GSTIN are the PAN).")


def clean_ifsc(v) -> str | None:
	s = _text(v).upper().replace(" ", "")
	if not s:
		return None
	if not _IFSC.match(s):
		raise ProfileError("IFSC must look like SBIN0001234 (11 characters).")
	return s


def clean_account_number(v) -> str | None:
	s = re.sub(r"[\s-]", "", _text(v))
	if not s:
		return None
	if not _ACCOUNT.match(s):
		raise ProfileError("Account number must be 6 to 18 digits.")
	return s


def clean_upi(v) -> str | None:
	s = _text(v)
	if not s:
		return None
	if not _UPI.match(s):
		raise ProfileError("UPI ID must look like name@bank.")
	return s.lower()


def clean_email(v) -> str | None:
	s = _text(v).lower()
	if not s:
		return None
	if not _EMAIL.match(s):
		raise ProfileError("Enter a valid email address, e.g. hello@example.com.")
	return s


def clean_colour(v) -> str | None:
	s = _text(v)
	if not s:
		return None
	if not s.startswith("#"):
		s = "#" + s
	if not _COLOUR.match(s):
		raise ProfileError("Brand colour must look like #3858F8.")
	return s.upper()


def clean_url(v) -> str | None:
	s = _text(v)
	if not s:
		return None
	if not re.match(r"^https?://", s, re.I):
		s = "https://" + s
	if not _URL.match(s):
		raise ProfileError("Enter a valid web address, e.g. https://www.example.com.")
	return s


def clean_pincode(v, country: str | None = "India") -> str | None:
	s = _text(v).replace(" ", "")
	if not s:
		return None
	if (country or "India") == "India" and not _PINCODE.match(s):
		raise ProfileError("PIN code must be 6 digits.")
	if len(s) > 12:
		raise ProfileError("Postal code is too long.")
	return s


def normalize_phone(v, default_cc: str = "91") -> str | None:
	"""+<country code><number>. 10-digit numbers get the default code (India);
	a leading 0 trunk prefix is dropped. None if it isn't a phone number."""
	raw = _text(v)
	if not raw:
		return None
	digits = re.sub(r"\D", "", raw)
	if raw.startswith("+"):
		pass
	elif raw.startswith("00"):
		digits = digits[2:]
	elif len(digits) == 11 and digits.startswith("0"):
		digits = default_cc + digits[1:]
	elif len(digits) == 10:
		digits = default_cc + digits
	if not 8 <= len(digits) <= 15:
		return None
	return "+" + digits


def clean_phone(v, default_cc: str = "91") -> str | None:
	if not _text(v):
		return None
	p = normalize_phone(v, default_cc)
	if not p:
		raise ProfileError("Enter a valid phone number, e.g. +91 98765 43210.")
	return p


def clean_tags(v) -> str | None:
	"""Comma-separated, trimmed, de-duplicated (case-insensitive), max 20."""
	items = v if isinstance(v, list) else _text(v).split(",")
	out, seen = [], set()
	for t in items:
		t = re.sub(r"\s+", " ", _text(t))[:40]
		if t and t.lower() not in seen:
			seen.add(t.lower())
			out.append(t)
	return ", ".join(out[:20]) or None


def tag_list(v) -> list[str]:
	return [t.strip() for t in (v or "").split(",") if t.strip()]
