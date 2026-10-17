#!/usr/bin/env python3
"""QTT server agent — reports this server's health to QTT OS (QTT Admin → Servers) every 5 minutes.

READ-ONLY: it only reads system information (disk, memory, load, updates, failed services, Docker containers,
listening ports, firewall/SSH settings, and Hermes usage counts where Hermes runs) and sends it to Frappe. It changes nothing on this server.

Installed by the one-line command from QTT Admin → Servers → (server) → Install agent:
  /usr/local/bin/qtt-server-agent      this file
  /etc/qtt-server-agent.env            QTT_URL, QTT_SERVER, QTT_TOKEN (chmod 600); optional QTT_ENDPOINT
                                       (a client server under Managed Services reports to qtt_services)
  /etc/cron.d/qtt-server-agent         runs it every 5 minutes as root
Remove: rm /usr/local/bin/qtt-server-agent /etc/qtt-server-agent.env /etc/cron.d/qtt-server-agent /var/cache/qtt-server-agent.json
Options: --verbose (print the report and the answer), --dry (collect and print, don't send).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.2"
ENV_FILE = "/etc/qtt-server-agent.env"
CACHE = "/var/cache/qtt-server-agent.json"
SLOW_EVERY = 3600  # seconds between slow checks (apt, journal, sshd)


def run(cmd, timeout=30):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 or out.stdout else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def have(binary):
    return shutil.which(binary) is not None


def env():
    values = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    values[k.strip()] = v.strip()
    except OSError:
        pass
    return values


def meminfo():
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    return info


def os_name():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def slow_checks(save=True):
    """Updates, failed SSH logins, firewall and SSH settings — cached for an hour
    (save=False for --dry: nothing is written)."""
    try:
        with open(CACHE) as f:
            cached = json.load(f)
        if time.time() - cached.get("at", 0) < SLOW_EVERY:
            return cached["data"]
    except (OSError, ValueError, KeyError):
        pass
    data = {}
    if have("apt"):
        lines = [l for l in run(["apt", "list", "--upgradable"], 60).splitlines() if "/" in l]
        data["updates"] = len(lines)
        data["security_updates"] = sum(1 for l in lines if "-security" in l)
    if have("journalctl"):
        log = run(["journalctl", "-u", "ssh", "-u", "sshd", "--since", "24 hours ago", "--no-pager", "-q"], 60)
        data["ssh_failed_24h"] = sum(1 for l in log.splitlines() if "Failed password" in l or "Invalid user" in l)
    # No ufw at all also means no host firewall in front of the open ports.
    data["firewall_active"] = "Status: active" in run(["ufw", "status"]) if have("ufw") else False
    if have("sshd"):
        cfg = run(["sshd", "-T"])
        m = re.search(r"^passwordauthentication (\w+)", cfg, re.M)
        if m:
            data["ssh_password_login"] = m.group(1) == "yes"
    if not save:
        return data
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump({"at": time.time(), "data": data}, f)
    except OSError:
        pass
    return data


def containers():
    if not have("docker"):
        return []
    out = []
    for line in run(["docker", "ps", "-a", "--format", "{{json .}}"]).splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        out.append({"name": c.get("Names"), "image": c.get("Image"), "state": c.get("State"), "status": c.get("Status")})
    return out


def ports():
    out, seen = [], set()
    for line in run(["ss", "-tlnpH"]).splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        addr = parts[3]
        host, _, port = addr.rpartition(":")
        if not port.isdigit():
            continue
        host = host.strip("[]")
        public = not (host.startswith("127.") or host in ("::1", "localhost") or host.startswith("%lo"))
        proc = re.search(r'users:\(\("([^"]+)"', line)
        key = (int(port), public)
        if key in seen:
            continue
        seen.add(key)
        out.append({"port": int(port), "public": public, "process": proc.group(1) if proc else ""})
    return out


HERMES_HOME = "/home/hermes/.hermes"


def hermes():
    """Hermes Agent on this server (QTT-AI-OS): who may talk to it and how much it's used — counts only, never
    user ids, chats or keys. None when Hermes isn't installed here."""
    db_path = os.path.join(HERMES_HOME, "state.db")
    if not os.path.exists(db_path):
        return None
    out = {"allowed_users": 0, "gateway_running": False}
    try:
        with open(os.path.join(HERMES_HOME, ".env")) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.endswith("_ALLOWED_USERS") and not k.startswith("#"):  # not the commented-out examples
                    out["allowed_users"] += len([x for x in v.strip().strip('"').split(",") if x.strip()])
    except OSError:
        pass
    try:
        with open(os.path.join(HERMES_HOME, "gateway.pid")) as f:
            pid = int(re.findall(r"\d+", f.read())[0])
        out["gateway_running"] = os.path.exists(f"/proc/{pid}")
    except (OSError, ValueError, IndexError):
        pass
    try:
        import sqlite3

        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        week = time.time() - 7 * 86400
        one = lambda sql, *a: db.execute(sql, a).fetchone()[0] or 0  # noqa: E731
        active = "coalesce(last_activity_at, started_at, 0) >= ?"
        out.update({
            "sessions": one("select count(*) from sessions"),
            "users": one("select count(distinct coalesce(user_id, chat_id)) from sessions where coalesce(user_id, chat_id) is not null"),
            "sessions_7d": one(f"select count(*) from sessions where {active}", week),
            "users_7d": one(f"select count(distinct coalesce(user_id, chat_id)) from sessions where {active} and coalesce(user_id, chat_id) is not null", week),
            "messages_7d": one("select count(*) from messages where timestamp >= ?", week),
            "cost_usd": round(float(one("select sum(estimated_cost_usd) from sessions")), 4),
            "cost_usd_7d": round(float(one("select sum(estimated_cost_usd) from session_model_usage where last_seen >= ?", week)), 4),
            "by_source_7d": {str(src or "other"): n for src, n in db.execute(
                f"select source, count(*) from sessions where {active} group by source order by 2 desc limit 6", (week,))},
        })
        db.close()
    except Exception as e:  # a Hermes upgrade may change its tables: report that, don't fail the whole report
        out["error"] = str(e)[:120]
    return out


def collect(save=True):
    disk = shutil.disk_usage("/")
    mem = meminfo()
    swap_total = mem.get("SwapTotal", 0)
    with open("/proc/uptime") as f:
        uptime = float(f.read().split()[0])
    failed = [l.split()[0] for l in run(["systemctl", "--failed", "--plain", "--no-legend"]).splitlines() if l.strip()]
    report = {
        "agent_version": VERSION,
        "hostname": socket.gethostname(),
        "os": os_name(),
        "kernel": os.uname().release,
        "cpu_count": os.cpu_count() or 1,
        "load": list(os.getloadavg()),
        "uptime_seconds": int(uptime),
        "disk": {"total_bytes": disk.total, "used_bytes": disk.used},
        "memory": {"total_bytes": mem.get("MemTotal", 0), "available_bytes": mem.get("MemAvailable", 0)},
        "swap": {"used_pct": round((swap_total - mem.get("SwapFree", 0)) / swap_total * 100, 1) if swap_total else 0},
        "reboot_required": os.path.exists("/var/run/reboot-required"),
        "failed_services": failed,
        "containers": containers(),
        "ports": ports(),
    }
    h = hermes()
    if h is not None:
        report["hermes"] = h
    report.update(slow_checks(save))
    return report


def send(report, cfg):
    req = urllib.request.Request(
        cfg["QTT_URL"].rstrip("/") + "/api/method/" + (cfg.get("QTT_ENDPOINT") or "qtt_platform.api.servers.ingest"),
        data=json.dumps(report).encode(),
        headers={"Content-Type": "application/json", "X-QTT-Server": cfg["QTT_SERVER"], "X-QTT-Token": cfg["QTT_TOKEN"],
                 "User-Agent": "qtt-server-agent/" + VERSION},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()[:500].decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:500].decode(errors="replace")
    except OSError as e:
        return 0, str(e)


def main():
    verbose = "--verbose" in sys.argv or "--dry" in sys.argv
    report = collect(save="--dry" not in sys.argv)
    if verbose:
        print(json.dumps(report, indent=1))
    if "--dry" in sys.argv:
        return 0
    cfg = env()
    if not all(cfg.get(k) for k in ("QTT_URL", "QTT_SERVER", "QTT_TOKEN")):
        print("Missing QTT_URL / QTT_SERVER / QTT_TOKEN in " + ENV_FILE, file=sys.stderr)
        return 2
    status, body = send(report, cfg)
    if verbose or status != 200:
        print(f"QTT answered {status}: {body}", file=sys.stderr if status != 200 else sys.stdout)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
