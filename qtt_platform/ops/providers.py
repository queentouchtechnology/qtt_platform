"""
QTT Admin → Servers and Domains: read-only data from the hosting providers.

  Contabo   servers (status, plan) and their snapshots
  Hostinger domains (status, expiry)

Only GET calls (plus Contabo's token request): nothing here can change a
server or a domain. The rules (`snapshot_state`, `server_notices`,
`domain_level`) are plain functions so they are tested without a bench.
"""

import uuid
from datetime import date, datetime, timezone

import requests

CONTABO_TOKEN_URL = "https://auth.contabo.com/auth/realms/contabo/protocol/openid-connect/token"
CONTABO_API = "https://api.contabo.com/v1"
HOSTINGER_API = "https://developers.hostinger.com"
TIMEOUT = 20


class ProviderError(Exception):
	pass


# --------------------------------------------------------------------------
# HTTP (read-only)
# --------------------------------------------------------------------------
def contabo_token(client_id: str, client_secret: str, user: str, password: str, http=requests) -> str:
	try:
		r = http.post(CONTABO_TOKEN_URL, timeout=TIMEOUT, data={
			"client_id": client_id, "client_secret": client_secret,
			"username": user, "password": password, "grant_type": "password",
		})
		data = r.json()
	except (requests.RequestException, ValueError) as exc:
		raise ProviderError(f"Contabo sign-in failed: {exc}") from exc
	token = data.get("access_token")
	if not token:
		raise ProviderError(f"Contabo sign-in failed: {data.get('error_description') or data.get('error') or r.status_code}")
	return token


def _contabo_get(token: str, path: str, http=requests) -> list:
	try:
		r = http.get(f"{CONTABO_API}{path}", timeout=TIMEOUT,
					 headers={"Authorization": f"Bearer {token}", "x-request-id": str(uuid.uuid4())})
		data = r.json()
	except (requests.RequestException, ValueError) as exc:
		raise ProviderError(f"Contabo {path}: {exc}") from exc
	if r.status_code >= 400:
		raise ProviderError(f"Contabo {path}: {data.get('message') or r.status_code}")
	return data.get("data") or []


def contabo_inventory(client_id: str, client_secret: str, user: str, password: str, http=requests) -> list[dict]:
	token = contabo_token(client_id, client_secret, user, password, http=http)
	out = []
	for i in _contabo_get(token, "/compute/instances?size=100", http=http):
		snaps = _contabo_get(token, f"/compute/instances/{i['instanceId']}/snapshots", http=http)
		out.append({
			"instance_id": str(i.get("instanceId")),
			"name": i.get("name"),
			"display_name": i.get("displayName") or i.get("name"),
			"ip": ((i.get("ipConfig") or {}).get("v4") or {}).get("ip"),
			"status": i.get("status"),
			"plan": " · ".join(str(x) for x in (i.get("productName") or i.get("productId"), f"{i.get('cpuCores')} CPU",
												  f"{round((i.get('ramMb') or 0) / 1024)} GB RAM",
												  f"{round((i.get('diskMb') or 0) / 1024)} GB disk") if x),
			"region": i.get("regionName") or i.get("region"),
			"cancel_date": i.get("cancelDate"),
			"snapshots": [{"name": s.get("name"), "created": s.get("createdDate"), "auto_delete": s.get("autoDeleteDate")} for s in snaps],
		})
	return out


def hostinger_domains(token: str, http=requests) -> list[dict]:
	try:
		r = http.get(f"{HOSTINGER_API}/api/domains/v1/portfolio", timeout=TIMEOUT,
					 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
		data = r.json()
	except (requests.RequestException, ValueError) as exc:
		raise ProviderError(f"Hostinger domains: {exc}") from exc
	if r.status_code >= 400 or not isinstance(data, list):
		raise ProviderError(f"Hostinger domains: {(data or {}).get('message') if isinstance(data, dict) else r.status_code}")
	return [{"domain": d.get("domain"), "status": d.get("status"), "expires_on": (d.get("expires_at") or "")[:10] or None}
			for d in data if d.get("domain") and d.get("type", "domain") == "domain"]


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
def _dt(value) -> datetime | None:
	if not value:
		return None
	if isinstance(value, datetime):
		return value if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
	try:
		parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
	except ValueError:
		return None
	return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def snapshot_state(snapshots: list[dict]) -> dict:
	"""Newest snapshot time, how many, and when the newest is auto-deleted (UTC, naive)."""
	dated = sorted((s for s in snapshots if _dt(s.get("created"))), key=lambda s: _dt(s["created"]), reverse=True)
	newest = dated[0] if dated else None
	return {
		"last_snapshot_at": _dt(newest["created"]) if newest else None,
		"snapshot_auto_delete": _dt(newest.get("auto_delete")) if newest else None,
		"snapshot_count": len(snapshots),
	}


def server_notices(*, last_snapshot_at, snapshot_auto_delete, provider_status, now: datetime, max_age_days: int = 14) -> list[str]:
	"""Plain-English "to fix" lines for one server from its provider data."""
	notes = []
	if provider_status and provider_status != "running":
		notes.append(f"Contabo says this server is {provider_status}.")
	last = _dt(last_snapshot_at)
	if not last:
		notes.append("No Contabo snapshot. Take one before any big change.")
	else:
		age = (now - last).days
		if age > max_age_days:
			notes.append(f"Last snapshot is {age} days old.")
		gone = _dt(snapshot_auto_delete)
		if gone and 0 <= (gone - now).days <= 5:
			notes.append(f"Contabo deletes the last snapshot on {gone.date().isoformat()}. Take a new one.")
	return notes


def domain_level(*, status: str | None, expires_on, today: date, warn_days: int = 30, watch: bool = True) -> tuple[str, int | None]:
	"""(level, days_left). Levels: ok, warning (expires within warn_days),
	critical (within 7 days, or expired while still watched), lapsed (expired and
	not watched — let go on purpose), ignored (not watched, still active)."""
	try:
		days = (date.fromisoformat(str(expires_on)[:10]) - today).days if expires_on else None
	except ValueError:
		days = None
	expired = (status or "").lower() == "expired" or (days is not None and days < 0)
	if not watch:
		return ("lapsed" if expired else "ignored"), days
	if expired:
		return "critical", days
	if days is not None and days <= 7:
		return "critical", days
	if days is not None and days <= warn_days:
		return "warning", days
	return "ok", days
