"""
The hardening review section 8 fix, implemented: atomic credit
deduction against a real database constraint, ledger stays authoritative
for history. See QTT Tenant Product Wallet's own description for the
relationship between the two tables.

Every function here writes via a single Frappe request-level transaction
— the raw SQL balance UPDATE and the subsequent QTT AI Credit Ledger
insert are two statements but one transaction (Frappe wraps each request
and commits/rolls back automatically; nothing here calls
frappe.db.commit() explicitly, which would break that atomicity — see the
same reasoning already applied in subscription/service.py).
"""

import frappe


def get_balance(tenant: str, product: str) -> float:
	return frappe.db.get_value(
		"QTT Tenant Product Wallet", {"tenant": tenant, "product": product}, "balance"
	) or 0.0


def _ensure_wallet(tenant: str, product: str) -> str:
	"""Lazily creates a zero-balance wallet row if none exists yet. Same
	insert-then-catch-UniqueValidationError-then-treat-as-already-created
	pattern as subscription/service.py's activate_pointer() — the
	database's real (tenant, product) unique constraint (patches/v0_5) is
	what makes concurrent first-creation safe, not this function's own
	logic."""
	existing = frappe.db.get_value(
		"QTT Tenant Product Wallet", {"tenant": tenant, "product": product}, "name"
	)
	if existing:
		return existing
	try:
		doc = frappe.get_doc(
			{"doctype": "QTT Tenant Product Wallet", "tenant": tenant, "product": product, "balance": 0}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
	except frappe.UniqueValidationError:
		return frappe.db.get_value(
			"QTT Tenant Product Wallet", {"tenant": tenant, "product": product}, "name"
		)


def deduct_credits(tenant: str, product: str, amount: float, *, reference: str) -> dict:
	"""The atomic operation itself: a conditional UPDATE whose WHERE
	clause is the entire safety guarantee — InnoDB's row lock during the
	UPDATE means of two concurrent deductions against a balance that can
	only satisfy one of them, exactly one succeeds and the other observes
	zero affected rows. No application-level lock is needed or used.

	Idempotent: a retried call with the same `reference` (e.g. a client
	retry after a timeout) is a safe no-op, checked before touching the
	balance at all.
	"""
	already_processed = frappe.db.exists(
		"QTT AI Credit Ledger", {"reference": reference, "source": "consumption"}
	)
	if already_processed:
		return {"ok": True, "already_processed": True}

	_ensure_wallet(tenant, product)
	affected = frappe.db.sql(
		"""
		UPDATE `tabQTT Tenant Product Wallet`
		SET balance = balance - %(amount)s
		WHERE tenant = %(tenant)s AND product = %(product)s AND balance >= %(amount)s
		""",
		{"tenant": tenant, "product": product, "amount": amount},
	)
	if not affected:
		return {"ok": False, "reason": "insufficient_credits"}

	frappe.get_doc(
		{
			"doctype": "QTT AI Credit Ledger",
			"tenant": tenant,
			"product": product,
			"source": "consumption",
			"amount": -amount,
			"reference": reference,
		}
	).insert(ignore_permissions=True)
	return {"ok": True}


def refund_credits(tenant: str, product: str, amount: float, *, reference: str) -> None:
	"""Reverses a specific consumption by its `reference` — idempotent,
	same as deduct_credits. Used by qtt_platform.ai.service when a
	provider call fails after credits were already reserved (reserve-
	before-call, refund-on-failure — see that module for why this
	ordering is the safer of the two options)."""
	already_refunded = frappe.db.exists("QTT AI Credit Ledger", {"reference": reference, "source": "refund"})
	if already_refunded:
		return

	_ensure_wallet(tenant, product)
	frappe.db.sql(
		"""UPDATE `tabQTT Tenant Product Wallet` SET balance = balance + %s WHERE tenant=%s AND product=%s""",
		(amount, tenant, product),
	)
	frappe.get_doc(
		{
			"doctype": "QTT AI Credit Ledger",
			"tenant": tenant,
			"product": product,
			"source": "refund",
			"amount": amount,
			"reference": reference,
		}
	).insert(ignore_permissions=True)


def grant_credits(
	tenant: str,
	product: str,
	amount: float,
	source: str,
	*,
	reference: str | None = None,
	user: str | None = None,
	expires_on=None,
) -> None:
	"""source: purchase | subscription_grant | bonus. Not idempotency-
	checked by reference the way deduct/refund are — a caller granting
	credits twice (e.g. two subscription renewal events) is expected to
	pass a unique `reference` per grant if it wants that protection;
	granting is not assumed to be a retry-prone operation the way a
	client-facing AI request is."""
	_ensure_wallet(tenant, product)
	frappe.db.sql(
		"""UPDATE `tabQTT Tenant Product Wallet` SET balance = balance + %s WHERE tenant=%s AND product=%s""",
		(amount, tenant, product),
	)
	frappe.get_doc(
		{
			"doctype": "QTT AI Credit Ledger",
			"tenant": tenant,
			"product": product,
			"user": user,
			"source": source,
			"amount": amount,
			"reference": reference,
			"expires_on": expires_on,
		}
	).insert(ignore_permissions=True)


def reconcile_wallet(tenant: str, product: str) -> dict:
	"""Recomputes balance from the ledger and corrects the wallet cache if
	it has drifted — the safety net named in the hardening review section
	8. Not registered as a scheduled job in this phase (no broader
	scheduler_events convention exists in this app yet — see hooks.py);
	callable directly for now, ready for Phase 9's billing reconciliation
	work to wire into a real cron alongside its own reconciliation needs.
	"""
	ledger_sum = frappe.db.sql(
		"""SELECT COALESCE(SUM(amount), 0) FROM `tabQTT AI Credit Ledger` WHERE tenant=%s AND product=%s""",
		(tenant, product),
	)[0][0]

	wallet_name = _ensure_wallet(tenant, product)
	cached_balance = frappe.db.get_value("QTT Tenant Product Wallet", wallet_name, "balance")

	if float(cached_balance or 0) != float(ledger_sum or 0):
		frappe.db.set_value("QTT Tenant Product Wallet", wallet_name, "balance", ledger_sum)
		return {"corrected": True, "was": cached_balance, "now": ledger_sum}
	return {"corrected": False, "balance": cached_balance}
