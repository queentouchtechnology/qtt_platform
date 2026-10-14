"""
The signed-in person's own profile photo (User.user_image) — shown in the app's menu, the
Account page and next to their name. Anyone signed in changes only their own.
"""

import frappe
from frappe import _

from qtt_platform.api.business import LOGO_TYPES, MAX_LOGO_BYTES, absolute_url
from qtt_platform.audit import write_audit_event
from qtt_platform.realtime import notify_users


def photo_url(user: str) -> str | None:
	"""Full URL of the person's photo: their own, else their employee photo (Office Pulse). Public files
	only — the app loads images without the session cookie."""
	image = frappe.db.get_value("User", user, "user_image")
	if not image and frappe.db.table_exists("Employee"):
		image = frappe.db.get_value("Employee", {"user_id": user, "status": "Active", "image": ["is", "set"]}, "image")
	if not image or image.startswith("/private/"):
		return None
	return absolute_url(image)


def _me() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Sign in first."), frappe.PermissionError)
	return user


def _set(user: str, url: str | None) -> None:
	old = frappe.db.get_value("User", user, "user_image")
	frappe.db.set_value("User", user, "user_image", url)
	if old and old != url:
		for name in frappe.get_all("File", filters={"file_url": old, "attached_to_doctype": "User", "attached_to_name": user}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True)
	notify_users([user], reason="profile")  # every open app of theirs refreshes the menu


@frappe.whitelist(methods=["POST"])
def upload_photo() -> dict:
	"""Multipart (field `file`): PNG / JPG / WEBP up to 2 MB."""
	user = _me()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a photo."))
	content = upload.stream.read(MAX_LOGO_BYTES + 1)
	name = (upload.filename or "photo.jpg").strip()
	if len(content) > MAX_LOGO_BYTES:
		frappe.throw(_("The photo must be 2 MB or smaller."))
	if not name.lower().endswith(LOGO_TYPES):
		frappe.throw(_("The photo must be a PNG, JPG or WEBP image."))
	f = frappe.get_doc({"doctype": "File", "file_name": f"photo-{frappe.generate_hash(length=8)}{name[name.rfind('.'):]}",
						"content": content, "attached_to_doctype": "User", "attached_to_name": user,
						"attached_to_field": "user_image", "is_private": 0}).insert(ignore_permissions=True)
	_set(user, f.file_url)
	write_audit_event("profile_photo_changed", actor=user, target_doctype="User", target_name=user)
	return {"image": photo_url(user)}


@frappe.whitelist(methods=["POST"])
def remove_photo() -> dict:
	user = _me()
	_set(user, None)
	write_audit_event("profile_photo_removed", actor=user, target_doctype="User", target_name=user)
	return {"image": photo_url(user)}
