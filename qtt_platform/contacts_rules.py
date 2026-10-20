"""
Office Pulse Contacts (PROJ-0016 C2) — vCard (.vcf) in and out, pure (tests/test_contacts.py). Phones and Google /
Outlook contacts export .vcf; QTT reads the name, organisation, phones, emails, address and notes, and writes the same.
"""

import re

KINDS = ("Customer", "Supplier", "Partner", "Other")


def _unfold(text: str) -> list[str]:
	return re.sub(r"\r?\n[ \t]", "", str(text or "").replace("\r\n", "\n")).split("\n")


def _unesc(v: str) -> str:
	return re.sub(r"\\([,;\\nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def _esc(v) -> str:
	return re.sub(r"([,;\\])", r"\\\1", str(v or "")).replace("\n", "\\n")


def parse_vcf(text: str) -> list[dict]:
	"""Each card → {customer_name, company_name, phone, whatsapp, email, address_line1, city, state, pincode, notes}.
	The first phone is the phone; a second mobile becomes WhatsApp. Cards without a name or a number / email are left out."""
	out, cur = [], None
	for line in _unfold(text):
		if not line.strip():
			continue
		up = line.upper()
		if up.startswith("BEGIN:VCARD"):
			cur = {"phones": [], "emails": []}
			continue
		if up.startswith("END:VCARD"):
			if cur is not None:
				c = cur
				name = c.get("fn") or " ".join(x for x in (c.get("given"), c.get("family")) if x)
				if name.strip() and (c["phones"] or c["emails"]):
					out.append({"customer_name": name.strip()[:140], "company_name": c.get("org") or None,
								"phone": c["phones"][0] if c["phones"] else None, "whatsapp": c["phones"][1] if len(c["phones"]) > 1 else None,
								"email": c["emails"][0] if c["emails"] else None, "address_line1": c.get("street"), "city": c.get("city"),
								"state": c.get("region"), "pincode": c.get("pin"), "notes": c.get("note"),
								"customer_type": "Business" if c.get("org") and not (c.get("given") or c.get("family")) else "Individual"})
			cur = None
			continue
		if cur is None or ":" not in line:
			continue
		key, val = line.split(":", 1)
		prop = key.split(";", 1)[0].split(".")[-1].upper()  # item1.TEL → TEL
		val = val.strip()
		if prop == "FN":
			cur["fn"] = _unesc(val)
		elif prop == "N":
			parts = [_unesc(p) for p in re.split(r"(?<!\\);", val)] + ["", ""]
			cur["family"], cur["given"] = parts[0].strip(), parts[1].strip()
		elif prop == "ORG":
			cur["org"] = _unesc(re.split(r"(?<!\\);", val)[0]).strip() or None
		elif prop == "TEL":
			num = re.sub(r"^tel:", "", val, flags=re.I).strip()
			if re.sub(r"\D", "", num):
				cur["phones"].append(num)
		elif prop == "EMAIL" and "@" in val:
			cur["emails"].append(_unesc(val).strip().lower())
		elif prop == "ADR":
			p = [_unesc(x).strip() for x in re.split(r"(?<!\\);", val)] + [""] * 7
			cur["street"], cur["city"], cur["region"], cur["pin"] = p[2] or None, p[3] or None, p[4] or None, p[5] or None
		elif prop == "NOTE":
			cur["note"] = _unesc(val)[:2000]
	return out


def to_vcf(rows: list[dict]) -> str:
	"""Cards for the address book (customer_name, company_name, phone, whatsapp, email, address, notes, kind)."""
	out = []
	for r in rows:
		lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_esc(r.get('customer_name'))}", f"N:;{_esc(r.get('customer_name'))};;;"]
		if r.get("company_name"):
			lines.append(f"ORG:{_esc(r['company_name'])}")
		if r.get("phone"):
			lines.append(f"TEL;TYPE=CELL:{r['phone']}")
		if r.get("whatsapp") and r.get("whatsapp") != r.get("phone"):
			lines.append(f"TEL;TYPE=CELL:{r['whatsapp']}")
		if r.get("email"):
			lines.append(f"EMAIL;TYPE=INTERNET:{r['email']}")
		if any(r.get(k) for k in ("address_line1", "city", "state", "pincode")):
			lines.append(f"ADR;TYPE=WORK:;;{_esc(r.get('address_line1'))};{_esc(r.get('city'))};{_esc(r.get('state'))};{_esc(r.get('pincode'))};{_esc(r.get('country'))}")
		if r.get("kind"):
			lines.append(f"CATEGORIES:{_esc(r['kind'])}")
		if r.get("notes"):
			lines.append(f"NOTE:{_esc(r['notes'])}")
		lines.append("END:VCARD")
		out.append("\r\n".join(lines))
	return "\r\n".join(out) + ("\r\n" if out else "")
