"""
View as (pure — no frappe; qtt_platform.view_as runs it): the business owner sees the app exactly as
one of their people sees it, without being able to change anything as them.

  can_view(...)          who may view as whom
  request_allowed(...)   what a "view as" request may do: read the QTT apps' screens, nothing else
"""

TTL_SECONDS = 30 * 60  # ends by itself after 30 minutes without use
OWNER_ROLE = "Tenant Owner"
# Never viewable: QTT staff and system accounts (their reads reach beyond one business).
STAFF_ROLES = ("System Manager", "Administrator")

# The QTT apps' own methods (each checks the person and their business itself), and who's signed in.
ALLOWED_PREFIXES = ("qtt_platform.", "qtt_office_pulse.", "qtt_orbitra.", "qtt_onbox.", "qtt_services.")
ALLOWED_METHODS = {"frappe.auth.get_logged_user"}
# Starting and stopping happen as the owner, never inside a view.
DENIED_PREFIXES = ("qtt_platform.api.view_as.",)
READ_HTTP = ("GET", "HEAD")

VIEW_ONLY = "View only: you're seeing {name}'s screens. Exit View as to make changes."
ENDED = "View as ended. You're back on your own account."


def can_view(*, owner: str, owner_role: str | None, target: str, target_member: bool, target_roles: list[str]) -> str | None:
	"""Why this owner can't view as this person — None when they can."""
	if owner_role != OWNER_ROLE:
		return "Only the business owner can view the app as someone else."
	if not target or target == owner:
		return "Choose someone else in your business."
	if not target_member:
		return "That person isn't in this business any more."
	if target in ("Administrator", "Guest") or any(r in STAFF_ROLES for r in target_roles or []):
		return "This account can't be viewed."
	return None


def request_allowed(http_method: str, path: str) -> tuple[bool, str]:
	"""(allowed, why not) for one request made while viewing as someone: reads of the QTT apps only."""
	if not (path or "").startswith("/api/method/"):
		return False, "not_app"
	cmd = path[len("/api/method/"):].strip("/")
	if cmd in ALLOWED_METHODS:
		pass
	elif not cmd.startswith(ALLOWED_PREFIXES) or cmd.startswith(DENIED_PREFIXES):
		return False, "not_app"
	if (http_method or "").upper() not in READ_HTTP:
		return False, "view_only"
	return True, ""
