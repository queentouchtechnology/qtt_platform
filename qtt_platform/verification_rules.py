"""
Business and seller verification (GSTIN, PAN, bank account, company CIN) — pure rules, no Frappe, no network
(verification.py calls the service and keeps each check).

The service behind it is never named to anyone: not in the app, not on Edenza, not in an error.
"""

import hashlib
import re

KINDS = ("gstin", "pan", "bank", "cin")
TITLES = {"gstin": "GSTIN", "pan": "PAN", "bank": "Bank account", "cin": "Company (CIN)"}
# What QTT pays for each, in paise before GST (owner's price list, 26 Nov 2026) — for the monthly limit.
COST = {"gstin": 63, "pan": 117, "bank": 234, "cin": 156}
CACHE_DAYS = 30

PAN = re.compile(r"^[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z]$")
GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
CIN = re.compile(r"^[LUFG][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$|^[A-Z]{3}-[0-9]{4}$")  # CIN, or an LLPIN


class VerifyError(ValueError):
	"""Said to the person as it is."""


def gstin_checksum_ok(g: str) -> bool:
	chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	total = 0
	for i, c in enumerate(g[:14]):
		p = chars.index(c) * ((i % 2) + 1)
		total += p // 36 + p % 36
	return chars[(36 - total % 36) % 36] == g[14]


def clean(kind: str, number: str, ifsc: str | None = None) -> tuple[str, str | None]:
	"""(number, ifsc) cleaned; VerifyError with a plain message when it can't be right."""
	n = re.sub(r"[\s-]+", "", str(number or "")).upper() if kind != "cin" else re.sub(r"\s+", "", str(number or "")).upper()
	if kind == "pan":
		if not PAN.match(n):
			raise VerifyError("That PAN doesn't look right. It has 10 characters, like ABCPE1234F.")
	elif kind == "gstin":
		if not GSTIN.match(n) or not gstin_checksum_ok(n):
			raise VerifyError("That GSTIN doesn't look right. Check it against the GST certificate.")
	elif kind == "bank":
		n = re.sub(r"\D", "", n)
		i = re.sub(r"\s+", "", str(ifsc or "")).upper()
		if not 6 <= len(n) <= 18:
			raise VerifyError("The account number should have 6 to 18 digits.")
		if not IFSC.match(i):
			raise VerifyError("The IFSC code doesn't look right. It has 11 characters, like SBIN0001234.")
		return n, i
	elif kind == "cin":
		if not CIN.match(n):
			raise VerifyError("That CIN doesn't look right. It has 21 characters, like U72900TN2020PTC123456.")
	else:
		raise VerifyError("Unknown check.")
	return n, None


def mask(kind: str, number: str) -> str:
	"""What's kept and shown: GSTIN and CIN are public; a PAN and an account number are masked."""
	if kind == "pan":
		return number[:3] + "XXXX" + number[-3:]
	if kind == "bank":
		return "X" * max(0, len(number) - 4) + number[-4:]
	return number


def fingerprint(kind: str, number: str, ifsc: str | None = None) -> str:
	return hashlib.sha256(f"{kind}|{number}|{ifsc or ''}".encode()).hexdigest()


def request_for(kind: str, number: str, ifsc: str | None = None) -> tuple[str, dict]:
	"""(path, body) at the service."""
	return {
		"pan": ("/pan-verification-v1", {"pan": number}),
		"gstin": ("/gstin-basic-v1", {"gstin": number}),
		"bank": ("/bank-account-v1", {"account_number": number, "ifsc": ifsc}),
		"cin": ("/cin-basic-v1", {"cin": number}),
	}[kind]


def read(kind: str, status: int | None, body: dict | None) -> dict:
	"""The service's answer → {result, reason, record_name, details}. result: verified · not_found · inactive · invalid ·
	failed. Only safe facts are kept: never an Aadhaar number, never anything the person didn't need."""
	body = body if isinstance(body, dict) else {}
	if status == 200:
		found = bool(body.get("verified"))
		name = {"pan": body.get("name"), "gstin": body.get("legal_name"), "bank": body.get("account_holder_name"),
				"cin": body.get("company_name")}[kind] or ""
		details = {}
		if kind == "gstin":
			details = {k: body.get(k) for k in ("trade_name", "status", "constitution", "registration_date", "taxpayer_type") if body.get(k)}
		elif kind == "pan":
			details = {k: body.get(k) for k in ("category",) if body.get(k)}
			if isinstance(body.get("aadhaar_linked"), bool):
				details["aadhaar_linked"] = body["aadhaar_linked"]
		elif kind == "cin":
			details = {k: body.get(k) for k in ("roc_code", "company_status", "date_of_incorporation") if body.get(k)}
		result = "verified" if found else "not_found"
		if found and kind == "gstin" and str(details.get("status") or "").lower() not in ("", "active"):
			result = "inactive"
		return {"result": result, "reason": "", "record_name": " ".join(str(name).split()), "details": details}
	if status == 422 or status == 400:
		return {"result": "invalid", "reason": "The government record says this number isn't valid.", "record_name": "", "details": {}}
	reason = {401: "setup", 403: "setup", 402: "wallet", 429: "busy"}.get(status or 0, "busy")
	return {"result": "failed", "reason": reason, "record_name": "", "details": {}}


# ---- names
TITLES_WORDS = {"MR", "MRS", "MS", "MISS", "SMT", "SHRI", "SRI", "DR", "KUMARI", "M/S", "MS.", "THE"}
COMPANY_WORDS = {"PVT": "PRIVATE", "PVT.": "PRIVATE", "LTD": "LIMITED", "LTD.": "LIMITED", "CO": "COMPANY", "CORP": "CORPORATION",
				 "MOHD": "MOHAMMED", "MD": "MOHAMMED", "KR": "KUMAR"}


def _words(name: str) -> list[str]:
	n = str(name or "").upper().replace("&", " AND ").replace("M/S", " ")
	out = []
	for w in re.split(r"[^A-Z0-9]+", n):
		if not w or w in TITLES_WORDS:
			continue
		out.append(COMPANY_WORDS.get(w, w))
	return out


def name_score(a: str, b: str) -> int:
	"""0–100: how likely two spellings are the same person or business (order, titles, initials and spacing don't matter)."""
	x, y = _words(a), _words(b)
	if not x or not y:
		return 0
	if x == y:
		return 100
	if sorted(x) == sorted(y) or "".join(sorted(x)) == "".join(sorted(y)):
		return 95
	if "".join(x) == "".join(y):
		return 95  # VIJAYKUMAR / VIJAY KUMAR
	short, long_ = (x, y) if len(x) <= len(y) else (y, x)
	matched, pool = 0, list(long_)
	for w in short:
		hit = next((p for p in pool if p == w or (len(w) == 1 and p.startswith(w)) or (len(p) == 1 and w.startswith(p))), None)
		if hit is None:
			hit = next((p for p in pool if len(w) > 3 and len(p) > 3 and _close(w, p)), None)
		if hit is not None:
			pool.remove(hit)
			matched += 1
	if matched == len(short):
		# every word of the shorter name is in the longer one (a missing middle name, initials)
		return 90 if len(short) >= 2 or len(long_) == 1 else 70
	return int(100 * matched / len(long_) * 0.8)


def _sound(w: str) -> str:
	"""How a name sounds, for spellings of the same Indian name: PREETI / PRITI, RAFIQ / RAFIK, LAKSHMI / LAXMI."""
	for x, y in (("EE", "I"), ("OO", "U"), ("PH", "F"), ("TH", "T"), ("DH", "D"), ("KH", "K"), ("BH", "B"), ("GH", "G"), ("KSH", "X"), ("KS", "X"),
				 ("Q", "K"), ("W", "V"), ("Z", "J"), ("Y", "I")):
		w = w.replace(x, y)
	return re.sub(r"(.)+", r"", w)


def _close(a: str, b: str) -> bool:
	"""The same sound, or one letter different (PREETI / PRITI, RAFIQ / RAFIK)."""
	a, b = _sound(a), _sound(b)
	if a == b:
		return True
	if abs(len(a) - len(b)) > 1:
		return False
	i = 0
	while i < min(len(a), len(b)) and a[i] == b[i]:
		i += 1
	return a[i + 1:] == b[i + 1:] or a[i + 1:] == b[i:] or a[i:] == b[i + 1:]


def matches(a: str, b: str, threshold: int = 80) -> bool:
	return name_score(a, b) >= threshold


def summary(kind: str, result: str, record_name: str, details: dict, given_name: str | None, score: int | None, threshold: int) -> str:
	"""One plain line for an admin or the owner."""
	t = TITLES[kind]
	if result == "verified":
		line = f"{t} found: {record_name}" if record_name else f"{t} found"
		if kind == "gstin" and details.get("trade_name") and details["trade_name"] != record_name:
			line += f" (trading as {details['trade_name']})"
		if given_name and score is not None:
			line += f". Name matches ({score})." if score >= threshold else f". Name doesn't match \"{given_name}\" ({score})."
		return line
	if result == "inactive":
		return f"{t} found but its status is {details.get('status')}: {record_name}."
	if result == "not_found":
		return f"No {t} record found for this number."
	if result == "invalid":
		return f"The {t} isn't valid."
	return "Couldn't check right now. Try again later."
