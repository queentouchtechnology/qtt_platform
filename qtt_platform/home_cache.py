"""Home's answers (api/home.py overview and actions) kept 30 seconds in Redis — Speed phase 3.

They are the two slowest calls people wait on (about a second each: every app adds its tiles, numbers and cards).

- **Never shared between people.** The key holds the call, the business, the person, the person's access counter
  (raised whenever their membership or app access changes — realtime.notify_users) and the business's change counter.
- **A save in the business shows at once.** Every successful change sent to the server in that business (POST/PUT/DELETE
  that isn't analytics, screen times or a ping) raises the business's counter (after_request hook `bump_after_save`),
  so the next Home is worked out fresh. Changes made outside the app (website orders, automations, the scheduler) show
  within 30 seconds.
"""

import frappe

TTL_SECONDS = 30
COUNTER_DAYS = 7

# Sent as changes but change nothing on Home (perf_rules covers servers and robots). Matched on the last part of the name.
_NO_CHANGE = {"ingest", "screens", "ping", "heartbeat", "register", "typing", "draft", "preview", "search", "ask", "translate", "validate"}
_CHANGE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def bumps(name: str | None, http_method: str | None, status: int | None) -> bool:
	"""Pure: does this finished request change what Home shows?"""
	if not name or (http_method or "").upper() not in _CHANGE_METHODS:
		return False
	if not status or status >= 400:
		return False
	last = name.rsplit(".", 1)[-1]
	return last not in _NO_CHANGE and not last.startswith(("preview_", "search_", "suggest", "track"))


def key(call: str, *, tenant: str, user: str, access: int, change: int) -> str:
	"""Pure: one person's Home answer in one business, at these counters."""
	return f"qtt_home|{call}|{tenant}|{user}|a{access}|c{change}"


def _counter(name: str) -> int:
	cache = frappe.cache()
	raw = cache.get(cache.make_key(name))
	try:
		return int(raw or 0)
	except (TypeError, ValueError):
		return 0


def _raise(name: str) -> None:
	cache = frappe.cache()
	k = cache.make_key(name)
	pipe = cache.pipeline(transaction=False)
	pipe.incr(k)
	pipe.expire(k, COUNTER_DAYS * 86400)
	pipe.execute()


def raise_business(tenant: str) -> None:
	_raise(f"qtt_home_change|{tenant}")


def raise_access(user: str) -> None:
	"""Their membership or app access changed (realtime.notify_users): their cached Home is never used again."""
	_raise(f"qtt_home_access|{user}")


def cached(call: str, user: str, tenant: str, work):
	"""Home's answer for [user] in [tenant]: from the cache when it's there, else worked out by [work]() and kept."""
	k = key(call, tenant=tenant, user=user, access=_counter(f"qtt_home_access|{user}"), change=_counter(f"qtt_home_change|{tenant}"))
	cache = frappe.cache()
	try:
		hit = cache.get_value(k)
	except Exception:
		hit = None
	if hit is not None:
		return hit
	value = work()
	try:
		cache.set_value(k, value, expires_in_sec=TTL_SECONDS)
	except Exception:
		pass
	return value


def bump_after_save(response=None, request=None) -> None:
	"""after_request: a change saved in a business → its Home counter goes up. Never raises."""
	try:
		from qtt_platform import perf_rules
		from qtt_platform.tenant.context import resolve_active_tenant

		name = perf_rules.endpoint(getattr(request, "path", None))
		if not bumps(name, getattr(request, "method", None), getattr(response, "status_code", None)):
			return
		user = getattr(getattr(frappe.local, "session", None), "user", None)
		if not user or user == "Guest":
			return
		tenant = resolve_active_tenant(user)
		if tenant:
			raise_business(tenant)
	except Exception:
		pass
