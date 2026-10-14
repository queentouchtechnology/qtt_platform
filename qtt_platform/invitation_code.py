"""
Short invitation codes people can read out and type: 8 characters shown as K7M2-QX9P, from an
alphabet without look-alikes (no 0/O, 1/I/L). Pure — tested in tests/test_invitation_code.py.

31^8 ≈ 850 billion codes; accept_invitation is rate-limited, so guessing one isn't practical.
The older 48-character tokens keep working (looks_like_code tells them apart).
"""

import secrets

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 8


def new_code() -> str:
	"""Stored form: 8 characters, no dash."""
	return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalize(text: str | None) -> str:
	"""What someone typed or pasted → stored form: case, spaces and dashes don't matter."""
	return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def looks_like_code(text: str | None) -> bool:
	n = normalize(text)
	return len(n) == LENGTH and all(ch in ALPHABET for ch in n)


def display(code: str | None) -> str:
	"""K7M2QX9P → K7M2-QX9P (anything else unchanged)."""
	n = normalize(code)
	return f"{n[:4]}-{n[4:]}" if len(n) == LENGTH else (code or "")
