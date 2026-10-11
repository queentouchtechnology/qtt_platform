#!/usr/bin/env python3
"""QTT usage collector — AI spend, Hermes and n8n usage for QTT OS (QTT Admin → Usage).

READ-ONLY: reads n8n's execution history (its PostgreSQL, via docker compose), Hermes's own usage
records (~hermes/.hermes/state.db), the DeepSeek balance and — when an OpenAI Admin key is set —
OpenAI's daily costs. Sends one snapshot to Frappe. Changes nothing.

Installed by the command from QTT Admin → Usage → Install collector:
  /usr/local/bin/qtt-usage-collector      this file
  /etc/qtt-usage-collector.env            QTT_URL, QTT_TOKEN, optional DEEPSEEK_API_KEY, OPENAI_ADMIN_KEY,
                                          N8N_DIR (default /opt/qtt-auto), HERMES_DB (chmod 600)
  /etc/cron.d/qtt-usage-collector         every 30 minutes as root
Options: --verbose (print the snapshot and the answer), --dry (collect and print, don't send).
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

VERSION = "1.0"
ENV_FILE = "/etc/qtt-usage-collector.env"
DAYS = 30


def env():
	cfg = {}
	try:
		with open(ENV_FILE) as f:
			for line in f:
				if "=" in line and not line.lstrip().startswith("#"):
					k, v = line.strip().split("=", 1)
					cfg[k.strip()] = v.strip()
	except OSError:
		pass
	return cfg


def _get_json(url, headers, timeout=20):
	req = urllib.request.Request(url, headers={**headers, "User-Agent": "qtt-usage-collector/" + VERSION})
	with urllib.request.urlopen(req, timeout=timeout) as r:
		return json.loads(r.read().decode())


# --------------------------------------------------------------------------
def deepseek(cfg):
	key = cfg.get("DEEPSEEK_API_KEY")
	if not key:
		return {"connected": False}
	try:
		d = _get_json("https://api.deepseek.com/user/balance", {"Authorization": "Bearer " + key, "Accept": "application/json"})
		info = (d.get("balance_infos") or [{}])[0]
		return {"connected": True, "available": bool(d.get("is_available")), "currency": info.get("currency"),
				"balance": float(info.get("total_balance") or 0), "topped_up": float(info.get("topped_up_balance") or 0),
				"granted": float(info.get("granted_balance") or 0)}
	except Exception as e:
		return {"connected": True, "error": str(e)[:200]}


def openai(cfg):
	key = cfg.get("OPENAI_ADMIN_KEY")
	if not key:
		return {"connected": False}
	start = int(time.time()) - DAYS * 86400
	try:
		daily, by_line = [], {}
		url = f"https://api.openai.com/v1/organization/costs?start_time={start}&bucket_width=1d&limit={DAYS}&group_by=line_item"
		d = _get_json(url, {"Authorization": "Bearer " + key})
		for b in d.get("data") or []:
			day = datetime.fromtimestamp(b["start_time"], timezone.utc).strftime("%Y-%m-%d")
			total = 0.0
			for r in b.get("results") or []:
				v = float((r.get("amount") or {}).get("value") or 0)
				total += v
				line = r.get("line_item") or "other"
				by_line[line] = by_line.get(line, 0) + v
			daily.append({"date": day, "cost_usd": round(total, 4)})
		return {"connected": True, "daily": daily, "by_line_item": [{"name": k, "cost_usd": round(v, 4)} for k, v in sorted(by_line.items(), key=lambda x: -x[1])]}
	except urllib.error.HTTPError as e:
		return {"connected": True, "error": f"OpenAI answered {e.code}: {e.read()[:200].decode(errors='replace')}"}
	except Exception as e:
		return {"connected": True, "error": str(e)[:200]}


def hermes(cfg):
	path = cfg.get("HERMES_DB") or "/home/hermes/.hermes/state.db"
	if not os.path.exists(path):
		return {"installed": False}
	try:
		db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
		since = time.time() - DAYS * 86400

		def day_of(col):
			# started_at / first_seen may be unix seconds or ISO text; handle both.
			return f"CASE WHEN typeof({col}) IN ('integer','real') THEN date({col}, 'unixepoch') ELSE substr({col}, 1, 10) END"

		def since_ok(col):
			return f"(CASE WHEN typeof({col}) IN ('integer','real') THEN {col} >= {since} ELSE {col} >= '{datetime.fromtimestamp(since, timezone.utc).strftime('%Y-%m-%d')}' END)"

		daily = {}
		for day, sessions, msgs, tin, tout in db.execute(
				f"SELECT {day_of('started_at')} d, count(*), sum(message_count), sum(input_tokens), sum(output_tokens) FROM sessions WHERE {since_ok('started_at')} GROUP BY d"):
			daily[day] = {"date": day, "sessions": sessions or 0, "messages": msgs or 0, "input_tokens": tin or 0, "output_tokens": tout or 0, "cost_usd": 0.0}
		for day, cost in db.execute(
				f"SELECT {day_of('first_seen')} d, sum(coalesce(actual_cost_usd, estimated_cost_usd, 0)) FROM session_model_usage WHERE {since_ok('first_seen')} GROUP BY d"):
			daily.setdefault(day, {"date": day, "sessions": 0, "messages": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})["cost_usd"] = round(cost or 0, 4)
		models = [{"model": m, "calls": c or 0, "input_tokens": i or 0, "output_tokens": o or 0, "cost_usd": round(x or 0, 4)}
				  for m, c, i, o, x in db.execute(
					  f"SELECT model, sum(api_call_count), sum(input_tokens), sum(output_tokens), sum(coalesce(actual_cost_usd, estimated_cost_usd, 0)) "
					  f"FROM session_model_usage WHERE {since_ok('first_seen')} GROUP BY model ORDER BY 5 DESC")]
		sources = [{"source": s or "cli", "sessions": n} for s, n in db.execute(
			f"SELECT source, count(*) FROM sessions WHERE {since_ok('started_at')} GROUP BY source ORDER BY 2 DESC")]
		last = db.execute("SELECT max(started_at) FROM sessions").fetchone()[0]
		return {"installed": True, "daily": sorted(daily.values(), key=lambda r: r["date"]), "models": models, "sources": sources,
				"last_active": last if isinstance(last, str) else (datetime.fromtimestamp(last, timezone.utc).isoformat() if last else None)}
	except Exception as e:
		return {"installed": True, "error": str(e)[:200]}


def _psql(n8n_dir, sql):
	out = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "sh", "-c", 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "|" -c "$0"', sql],
						 cwd=n8n_dir, capture_output=True, text=True, timeout=60)
	if out.returncode != 0:
		raise RuntimeError(out.stderr.strip()[:200])
	return [line.split("|") for line in out.stdout.strip().splitlines() if line]


def n8n(cfg):
	n8n_dir = cfg.get("N8N_DIR") or "/opt/qtt-auto"
	if not os.path.exists(os.path.join(n8n_dir, "docker-compose.yml")):
		return {"installed": False}
	try:
		daily = [{"date": d, "total": int(t), "success": int(s), "error": int(e)} for d, t, s, e in _psql(n8n_dir,
			f"select to_char(\"startedAt\"::date,'YYYY-MM-DD'), count(*), count(*) filter (where status='success'), "
			f"count(*) filter (where status in ('error','crashed')) from execution_entity where \"startedAt\" > now() - interval '{DAYS} days' "
			f"group by 1 order by 1")]
		flows = [{"name": n, "active": a == "t", "total": int(t or 0), "error": int(e or 0), "last_run": lr or None}
				 for n, a, t, e, lr in _psql(n8n_dir,
			f"select w.name, w.active, count(x.id), count(x.id) filter (where x.status in ('error','crashed')), "
			f"to_char(max(x.\"startedAt\"),'YYYY-MM-DD\"T\"HH24:MI:SS') from workflow_entity w left join execution_entity x on x.\"workflowId\"=w.id "
			f"and x.\"startedAt\" > now() - interval '{DAYS} days' group by w.name, w.active order by w.name")]
		errors_24h = int(_psql(n8n_dir, "select count(*) from execution_entity where status in ('error','crashed') and \"startedAt\" > now() - interval '1 day'")[0][0])
		return {"installed": True, "daily": daily, "workflows": flows, "active_workflows": sum(1 for f in flows if f["active"]),
				"total_workflows": len(flows), "errors_24h": errors_24h}
	except Exception as e:
		return {"installed": True, "error": str(e)[:200]}


def collect(cfg):
	return {"version": VERSION, "taken_at": datetime.now(timezone.utc).isoformat(), "days": DAYS,
			"deepseek": deepseek(cfg), "openai": openai(cfg), "hermes": hermes(cfg), "n8n": n8n(cfg)}


def send(snapshot, cfg):
	req = urllib.request.Request(cfg["QTT_URL"].rstrip("/") + "/api/method/qtt_platform.api.usage_dashboard.ingest",
								 data=json.dumps(snapshot).encode(),
								 headers={"Content-Type": "application/json", "X-QTT-Usage-Token": cfg["QTT_TOKEN"],
										  "User-Agent": "qtt-usage-collector/" + VERSION}, method="POST")
	try:
		with urllib.request.urlopen(req, timeout=30) as r:
			return r.status, r.read()[:300].decode(errors="replace")
	except urllib.error.HTTPError as e:
		return e.code, e.read()[:300].decode(errors="replace")
	except OSError as e:
		return 0, str(e)


def main():
	cfg = env()
	snap = collect(cfg)
	verbose = "--verbose" in sys.argv or "--dry" in sys.argv
	if verbose:
		print(json.dumps(snap, indent=1))
	if "--dry" in sys.argv:
		return 0
	if not cfg.get("QTT_URL") or not cfg.get("QTT_TOKEN"):
		print("Missing QTT_URL / QTT_TOKEN in " + ENV_FILE, file=sys.stderr)
		return 2
	status, body = send(snap, cfg)
	if verbose or status != 200:
		print(f"QTT answered {status}: {body}", file=sys.stderr if status != 200 else sys.stdout)
	return 0 if status == 200 else 1


if __name__ == "__main__":
	sys.exit(main())
