"""
n8n public REST API client + the summary QTT Admin → Marketing shows.

Frappe-free so it can be unit-tested without a bench. Only the calls the
console needs: list workflows, list executions, activate / deactivate.
Nothing here can edit or delete a workflow or read its credentials.

n8n API: header X-N8N-API-KEY, paths under /api/v1, cursor pagination
({"data": [...], "nextCursor": ...}).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

TIMEOUT_SECONDS = 15
MAX_WORKFLOW_PAGES = 5  # 5 x 250 workflows is far beyond what QTT runs
RECENT_EXECUTIONS = 250


class N8nError(Exception):
	"""Message is safe to show a platform owner (no key, no raw body)."""


class N8nClient:
	def __init__(self, base_url: str, api_key: str, session=None, timeout: int = TIMEOUT_SECONDS):
		if not base_url or not api_key:
			raise N8nError("Add the n8n address and API key in Marketing settings first.")
		self.base_url = base_url.rstrip("/")
		self.api_key = api_key
		self.session = session or requests.Session()
		self.timeout = timeout

	# -- calls --------------------------------------------------------------
	def workflows(self) -> list[dict]:
		items: list[dict] = []
		cursor = None
		for _ in range(MAX_WORKFLOW_PAGES):
			params = {"limit": 250}
			if cursor:
				params["cursor"] = cursor
			page = self._request("GET", "/workflows", params=params)
			items.extend(page.get("data") or [])
			cursor = page.get("nextCursor")
			if not cursor:
				break
		return items

	def executions(self, *, status: str | None = None, workflow_id: str | None = None, limit: int = RECENT_EXECUTIONS) -> list[dict]:
		params: dict = {"limit": min(max(int(limit), 1), 250)}
		if status:
			params["status"] = status
		if workflow_id:
			params["workflowId"] = workflow_id
		return self._request("GET", "/executions", params=params).get("data") or []

	def executions_since(self, since: datetime, *, max_pages: int = 8) -> list[dict]:
		"""Newest first, paging back until runs start before `since` (UTC).
		Capped so one very chatty workflow can't make this slow."""
		items: list[dict] = []
		cursor = None
		for _ in range(max_pages):
			params: dict = {"limit": 250}
			if cursor:
				params["cursor"] = cursor
			page = self._request("GET", "/executions", params=params)
			batch = page.get("data") or []
			items.extend(batch)
			cursor = page.get("nextCursor")
			oldest = _parse_time(batch[-1].get("startedAt")) if batch else None
			if not cursor or (oldest and oldest < since):
				break
		return items

	def workflow(self, workflow_id: str) -> dict:
		return self._request("GET", f"/workflows/{workflow_id}")

	def update_workflow(self, workflow_id: str, body: dict) -> dict:
		return self._request("PUT", f"/workflows/{workflow_id}", json=body)

	def set_active(self, workflow_id: str, active: bool) -> dict:
		action = "activate" if active else "deactivate"
		return self._request("POST", f"/workflows/{workflow_id}/{action}")

	# -- transport ------------------------------------------------------------
	def _request(self, method: str, path: str, params: dict | None = None, json: dict | None = None) -> dict:
		url = f"{self.base_url}/api/v1{path}"
		kwargs = {"params": params, "headers": {"X-N8N-API-KEY": self.api_key, "Accept": "application/json"}, "timeout": self.timeout}
		if json is not None:
			kwargs["json"] = json
		try:
			response = self.session.request(method, url, **kwargs)
		except requests.Timeout as exc:
			raise N8nError(f"n8n at {self.base_url} didn't answer in time.") from exc
		except requests.RequestException as exc:
			raise N8nError(f"Can't reach n8n at {self.base_url}.") from exc

		if response.status_code == 401:
			raise N8nError("n8n rejected the API key. Create a new one in n8n → Settings → n8n API.")
		if response.status_code == 404:
			raise N8nError("Not found on n8n. Check the address, and that the n8n public API is enabled.")
		if response.status_code == 400:
			raise N8nError("n8n refused the change. Nothing was saved.")
		if response.status_code >= 400:
			raise N8nError(f"n8n returned an error ({response.status_code}).")
		try:
			return response.json() or {}
		except ValueError as exc:
			raise N8nError("n8n sent an unexpected reply. Check the address points at n8n.") from exc


# ---------------------------------------------------------------------------
# What the console shows (pure)
# ---------------------------------------------------------------------------
def _parse_time(value) -> datetime | None:
	if not value:
		return None
	try:
		dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
	except ValueError:
		return None
	return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _status(execution: dict) -> str:
	status = execution.get("status")
	if status:
		return "failed" if status in ("error", "crashed") else status
	return "success" if execution.get("finished") else "failed"


def run_row(execution: dict) -> dict:
	started = _parse_time(execution.get("startedAt"))
	stopped = _parse_time(execution.get("stoppedAt"))
	return {
		"id": str(execution.get("id")),
		"status": _status(execution),
		"mode": execution.get("mode"),
		"started_at": started.isoformat() if started else None,
		"duration_ms": int((stopped - started).total_seconds() * 1000) if started and stopped else None,
	}


def _trigger(workflow: dict) -> str:
	types = [str(n.get("type") or "").lower() for n in workflow.get("nodes") or []]
	if any("webhook" in t or "chatwoot" in t for t in types):
		return "webhook"
	if any("schedule" in t or "cron" in t for t in types):
		return "schedule"
	if any(t.endswith("trigger") for t in types):
		return "event"
	return "manual"


def summarize(workflows: list[dict], executions: list[dict], *, now: datetime | None = None) -> dict:
	"""Workflows with last run + 24 h counts. Order: active and failing
	first, then other active ones, then inactive — so problems are on top."""
	now = now or datetime.now(timezone.utc)
	since = now - timedelta(hours=24)

	never = datetime.min.replace(tzinfo=timezone.utc)
	last: dict[str, dict] = {}
	last_at: dict[str, datetime] = {}
	runs_24h: dict[str, int] = {}
	failed_24h: dict[str, int] = {}
	for ex in executions:
		wf = str(ex.get("workflowId") or "")
		if not wf:
			continue
		started = _parse_time(ex.get("startedAt"))
		if wf not in last or (started or never) > last_at[wf]:
			last[wf], last_at[wf] = ex, started or never
		if started and started >= since:
			runs_24h[wf] = runs_24h.get(wf, 0) + 1
			if _status(ex) == "failed":
				failed_24h[wf] = failed_24h.get(wf, 0) + 1

	rows = []
	for wf in workflows:
		wid = str(wf.get("id"))
		rows.append(
			{
				"id": wid,
				"name": wf.get("name") or wid,
				"active": bool(wf.get("active")),
				"trigger": _trigger(wf),
				"tags": [t.get("name") for t in wf.get("tags") or [] if isinstance(t, dict) and t.get("name")],
				"updated_at": wf.get("updatedAt"),
				"last_run": run_row(last[wid]) if wid in last else None,
				"runs_24h": runs_24h.get(wid, 0),
				"failed_24h": failed_24h.get(wid, 0),
			}
		)
	rows.sort(key=lambda r: (not r["active"], r["failed_24h"] == 0, r["name"].lower()))
	return {
		"totals": {
			"workflows": len(rows),
			"active": sum(1 for r in rows if r["active"]),
			"runs_24h": sum(runs_24h.values()),
			"failed_24h": sum(failed_24h.values()),
			"failing_workflows": sum(1 for r in rows if r["failed_24h"]),
		},
		"workflows": rows,
	}
