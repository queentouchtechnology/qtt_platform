"""
Live refresh for client apps — product-agnostic.

Whenever something that changes "what this user may see" is saved — a
membership, a product access grant, a subscription, the tenant's own
status — every affected user gets one `qtt:context_changed` Socket.IO
event in their own user room, and the app re-fetches
api.app_context.get_app_context(). The event carries no data beyond the
tenant and a reason: clients always re-read through the normal,
permission-checked endpoint, so a stale or forged event can never grant
anything.

Wired in hooks.py doc_events. after_commit=True: nothing is announced for
a transaction that rolls back.
"""

import frappe

CONTEXT_CHANGED_EVENT = "qtt:context_changed"


def notify_users(users, *, tenant: str | None = None, reason: str | None = None) -> None:
	for user in sorted({u for u in users if u and u not in ("Guest", "Administrator")}):
		frappe.publish_realtime(
			CONTEXT_CHANGED_EVENT,
			{"tenant": tenant, "reason": reason},
			user=user,
			after_commit=True,
		)


def tenant_users(tenant: str) -> list[str]:
	return frappe.get_all(
		"QTT Tenant Membership", filters={"tenant": tenant, "status": "active"}, pluck="user"
	)


# --------------------------------------------------------------------------
# doc_events handlers
# --------------------------------------------------------------------------
def on_membership_change(doc, method=None):
	notify_users([doc.user], tenant=doc.tenant, reason="membership")


def on_product_access_change(doc, method=None):
	user = frappe.db.get_value("QTT Tenant Membership", doc.membership, "user")
	notify_users([user], tenant=doc.tenant, reason="product_access")


def on_subscription_change(doc, method=None):
	notify_users(tenant_users(doc.tenant), tenant=doc.tenant, reason="subscription")


def on_tenant_change(doc, method=None):
	# Includes members of a now-suspended tenant — they must learn they've
	# lost access, so tenant_users() is filtered on membership, not tenant status.
	notify_users(tenant_users(doc.name), tenant=doc.name, reason="tenant")
