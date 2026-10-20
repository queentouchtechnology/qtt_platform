"""
Remote control — the QTT agent on company computers (PROJ-0015 E, hardening 2026-10-21).

Why: RustDesk's own server has no per-person access control — anyone holding QTT's server key (every Office Pulse
user can copy it), a computer's ID and its password can connect. So the password is the control, and QTT owns it:

  setup     an owner / admin / HR Admin asks for a setup code (one use, 1 hour) and runs one command on the computer
            (Windows PowerShell as Administrator, or sudo on Mac / Linux). It points RustDesk at QTT's server, applies
            the company policy (no direct IP connections, no LAN discovery, no remote settings changes, no tunnels,
            idle sessions end), sets a long random permanent password made by QTT — never shown to any person — and
            installs a small agent that checks in every 15 minutes.
  rotation  the password changes by itself when access is revoked: someone who connected with it leaves the
            business, is suspended or loses owner / admin / HR Admin rights; the computer is given to someone else;
            or an owner asks. Computers without the agent are flagged "change its password" instead.
  lock-out  removing a computer sets a password nobody knows and removes the agent.
  audit     every connect, setup, change and lock-out is in QTT Remote Access Log.

Agent endpoints (no sign-in; a secret per computer, kept hashed here):
  script    the setup script for one setup code (os = windows | mac | linux)
  enroll    setup code + the computer's RustDesk ID → the agent key and the first password
  sync      agent key → the policy, and a new password or "lock" when one is due
  confirm   agent key + the change applied → QTT keeps the new password (and finishes a lock-out)
"""

import hashlib
import os
import secrets
from datetime import timedelta

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime, get_url, now_datetime

from qtt_platform import workplace_rules as rules

DEVICE = "QTT Remote Device"
LOG = "QTT Remote Access Log"
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workplace_agent")
AGENT_VERSION = "1"

# RustDesk options the agent applies on every check-in (company policy).
POLICY = {
	"direct-server": "N",  # no direct IP connections — everything goes through QTT's server (and its key)
	"enable-lan-discovery": "N",
	"allow-remote-config-modification": "N",  # nobody connected can change this computer's RustDesk settings
	"enable-tunnel": "N",  # no TCP tunnels into the company network
	"verification-method": "use-both-passwords",  # QTT's password, or a one-time password read out by the person there
	"allow-auto-disconnect": "Y",
	"auto-disconnect-timeout": "30",  # idle sessions end after 30 minutes
}


def _hash(token: str) -> str:
	return hashlib.sha256(f"qtt-remote|{token}".encode()).hexdigest()


def new_password() -> str:
	"""A long random permanent password (RustDesk accepts letters, digits, - and _)."""
	return secrets.token_urlsafe(18)


def log(device, action: str, user: str | None = None, detail: str = "") -> None:
	frappe.get_doc({"doctype": LOG, "tenant": device.tenant, "device": device.name, "device_title": device.title, "user": user,
					"action": action, "detail": detail[:500], "ip": getattr(frappe.local, "request_ip", None)}).insert(ignore_permissions=True)


def ask_rotation(device, reason: str, by: str | None = None) -> None:
	"""The password must change: the agent does it on its next check-in; a computer without the agent is flagged and
	the business's owners / admins / HR Admins are told."""
	if device.state in ("Locking", "Locked"):
		return
	frappe.db.set_value(DEVICE, device.name, {"rotate_required": 1, "rotate_reason": reason[:140]}, update_modified=False)
	log(device, "Password change asked", by, reason)
	if not device.managed:
		_tell_managers(device.tenant, f"🔐 Change the RustDesk password on {device.title}",
					   f"{reason}. Without the QTT agent it can't change by itself — change it on the computer, then save it in Remote help.")


def _tell_managers(tenant: str, title: str, body: str) -> None:
	try:
		from qtt_platform.team_events import send_push

		rows = frappe.db.sql("""select m.user from `tabQTT Tenant Membership` m
			left join `tabQTT Product Access` a on a.membership = m.name and a.product = %s and a.status = 'active'
			where m.tenant = %s and m.status = 'active' and (m.tenant_role in ('Tenant Owner', 'Tenant Admin') or a.product_role = 'HR Admin')""",
							 (rules.PULSE, tenant))
		send_push([r[0] for r in rows], title, body, {"kind": "remote", "tenant": tenant})
	except Exception:
		frappe.log_error(title="Remote control: couldn't tell the managers")


def on_access_lost(tenant: str, user: str, reason: str) -> None:
	"""Someone lost access (left, suspended, no longer owner / admin / HR Admin): every company computer whose saved
	password they used, and the ones given to them, get a new password."""
	try:
		used = set(frappe.get_all(LOG, filters={"tenant": tenant, "user": user, "action": "Connect with saved password"}, pluck="device"))
		given = set(frappe.get_all(DEVICE, filters={"tenant": tenant, "assigned_to": user}, pluck="name"))
		for name in used | given:
			if frappe.db.exists(DEVICE, name):
				ask_rotation(frappe.get_doc(DEVICE, name), reason)
	except Exception:
		frappe.log_error(title="Remote control: rotation after lost access failed")


# ---- what owners / HR do (called from api.workplace) ---------------------------------------------------------------
def setup_code(device) -> dict:
	"""A one-use setup code (1 hour) and the commands to run on the computer."""
	code = secrets.token_urlsafe(24)
	frappe.db.set_value(DEVICE, device.name, {"enroll_hash": _hash(code), "enroll_expires_at": now_datetime() + timedelta(hours=1)}, update_modified=False)
	base = get_url().rstrip("/")
	url = f"{base}/api/method/qtt_platform.api.workplace_agent.script"
	return {
		"expires_in_minutes": 60,
		"windows": f'irm "{url}?os=windows&code={code}" | iex',
		"mac": f'curl -fsSL "{url}?os=mac&code={code}" | sudo bash',
		"linux": f'curl -fsSL "{url}?os=linux&code={code}" | sudo bash',
	}


def lock(device, by: str) -> None:
	"""Remove a computer: with the agent it gets a password nobody knows and the agent removes itself; without it the
	record goes and the owners are told to change the password on the computer."""
	if device.managed and device.agent_hash:
		frappe.db.set_value(DEVICE, device.name, {"state": "Locking", "assigned_to": None}, update_modified=False)
		log(device, "Lock-out asked", by)
	else:
		log(device, "Removed", by, "no agent — its RustDesk password must be changed on the computer")
		if device.password:
			_tell_managers(device.tenant, f"🔐 Change the RustDesk password on {device.title}",
						   "It was removed from Company computers. Change its RustDesk password on the computer so the old one stops working.")
		frappe.delete_doc(DEVICE, device.name, ignore_permissions=True)


# ---- agent endpoints ---------------------------------------------------------------------------------------------------
def _by_code(code: str):
	name = frappe.db.get_value(DEVICE, {"enroll_hash": _hash(code or "")}, "name") if code else None
	d = frappe.get_doc(DEVICE, name) if name else None
	if not d or not d.enroll_expires_at or get_datetime(d.enroll_expires_at) < now_datetime():
		frappe.throw(_("This setup code isn't valid any more — make a new one in Remote help."), frappe.PermissionError)
	return d


def _by_agent(key: str):
	name = frappe.db.get_value(DEVICE, {"agent_hash": _hash(key or "")}, "name") if key else None
	if not name:
		frappe.throw(_("Unknown computer."), frappe.PermissionError)
	return frappe.get_doc(DEVICE, name)


def _text(body: str, name: str) -> None:
	frappe.local.response.filename = name
	frappe.local.response.filecontent = body.encode()
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=30, seconds=3600)
def script(os: str = "windows", code: str = ""):
	"""The setup script for one setup code (plain text, to pipe into PowerShell / bash)."""
	frappe.local.flags.commit = True
	d = _by_code(code)
	s = frappe.get_cached_doc("QTT Workplace Settings")
	kind = "windows" if os == "windows" else "unix"
	with open(f"{SCRIPTS}/{'agent.ps1' if kind == 'windows' else 'agent.sh'}", encoding="utf-8") as f:
		body = f.read()
	policy = ";".join(f"{k}={v}" for k, v in POLICY.items())
	body = (body.replace("__QTT_BASE__", get_url().rstrip("/")).replace("__QTT_CODE__", code)
			.replace("__QTT_CONFIG__", rules.rustdesk_config(s.rustdesk_host, s.rustdesk_key)).replace("__QTT_POLICY__", policy)
			.replace("__QTT_OS__", os if os in ("mac", "linux") else "windows").replace("__QTT_VERSION__", AGENT_VERSION))
	_text(body, "qtt-rustdesk-setup.ps1" if kind == "windows" else "qtt-rustdesk-setup.sh")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def enroll(code: str, rustdesk_id: str, os: str = "", host: str = "") -> dict:
	"""Setup code + the computer's RustDesk ID → {agent_key, password, policy}. The code works once."""
	frappe.local.flags.commit = True
	d = _by_code(code)
	rid = rules.rustdesk_id(rustdesk_id)
	if not rid:
		frappe.throw(_("RustDesk didn't give an ID — is it installed and running?"))
	key, pw = secrets.token_urlsafe(32), new_password()
	d.rustdesk_id = rid
	d.password = pw
	d.managed = 1
	d.state = "Active"
	d.agent_hash = _hash(key)
	d.enroll_hash = None
	d.enroll_expires_at = None
	d.agent_os = f"{os} {host}".strip()[:80]
	d.agent_seen_at = now_datetime()
	d.password_set_at = now_datetime()
	d.rotate_required = 0
	d.rotate_reason = None
	if host and (not d.title or d.title == "New computer"):
		d.title = host[:80]
	d.save(ignore_permissions=True)
	log(d, "Set up", None, f"agent on {os} ({host})")
	return {"agent_key": key, "password": pw, "policy": POLICY, "every_minutes": 15}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=40, seconds=900)
def sync(agent_key: str, rustdesk_id: str = "", version: str = "") -> dict:
	"""Agent check-in: the policy every time; a new password when one is due ({password, nonce}); {lock: password}
	when the computer was removed."""
	frappe.local.flags.commit = True
	d = _by_agent(agent_key)
	frappe.db.set_value(DEVICE, d.name, "agent_seen_at", now_datetime(), update_modified=False)
	rid = rules.rustdesk_id(rustdesk_id)
	if rid and rid != d.rustdesk_id:
		frappe.db.set_value(DEVICE, d.name, "rustdesk_id", rid, update_modified=False)
	out = {"policy": POLICY, "config": None}
	s = frappe.get_cached_doc("QTT Workplace Settings")
	out["config"] = rules.rustdesk_config(s.rustdesk_host, s.rustdesk_key)
	if d.state == "Locking":
		pending = d.get_password("pending_password", raise_exception=False)
		if not pending:
			pending = new_password()
			d.pending_password = pending  # a Password field: saved encrypted
			d.save(ignore_permissions=True)
		return {**out, "lock": True, "password": pending, "nonce": _hash(pending)[:16]}
	if d.rotate_required:
		pending = d.get_password("pending_password", raise_exception=False)
		if not pending:
			pending = new_password()
			d.pending_password = pending
			d.save(ignore_permissions=True)
		return {**out, "password": pending, "nonce": _hash(pending)[:16]}
	return out


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=40, seconds=900)
def confirm(agent_key: str, nonce: str) -> dict:
	"""The agent applied the new password (or the lock-out): QTT keeps it, or forgets the computer."""
	frappe.local.flags.commit = True
	d = _by_agent(agent_key)
	pending = d.get_password("pending_password", raise_exception=False)
	if not pending or _hash(pending)[:16] != nonce:
		frappe.throw(_("Nothing to confirm."))
	if d.state == "Locking":
		log(d, "Locked", None, "password nobody knows; agent removed")
		frappe.delete_doc(DEVICE, d.name, ignore_permissions=True)
		return {"ok": True, "removed": True}
	d.password = pending
	d.pending_password = None
	d.rotate_required = 0
	reason = d.rotate_reason
	d.rotate_reason = None
	d.password_set_at = now_datetime()
	d.save(ignore_permissions=True)
	log(d, "Password changed", None, reason or "")
	return {"ok": True}
