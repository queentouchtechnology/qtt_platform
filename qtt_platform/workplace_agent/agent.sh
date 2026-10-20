#!/bin/bash
# QTT OS - Remote help: set up this company computer (Mac / Linux). Run:
#   curl -fsSL "<the link from QTT OS > Remote help > Add computer>" | sudo bash
# What it does: points RustDesk at QTT's own server, applies the company policy (no direct IP connections, no LAN
# discovery, no remote settings changes, no tunnels, idle sessions end), sets a long random permanent password made by
# QTT (never shown), and adds a small agent (every 15 minutes) that changes the password when QTT asks - e.g. when
# someone's access is revoked. Remove the computer in QTT OS to lock it. RustDesk must be installed first (rustdesk.com).
set -euo pipefail
BASE="__QTT_BASE__"
CODE="__QTT_CODE__"
CONFIG="__QTT_CONFIG__"
POLICY="__QTT_POLICY__"
OS="__QTT_OS__"
DIR=/etc/qtt-remote-help

[ "$(id -u)" = 0 ] || { echo "Run it with sudo (... | sudo bash)."; exit 1; }
if [ "$OS" = mac ]; then RD="/Applications/RustDesk.app/Contents/MacOS/RustDesk"; else RD="$(command -v rustdesk || true)"; fi
if [ -z "$RD" ] || [ ! -x "$RD" ]; then echo "Install RustDesk first (rustdesk.com/download), open it once, then run this again."; exit 1; fi

"$RD" --config "$CONFIG" >/dev/null 2>&1 || true
IFS=';' read -ra KV <<< "$POLICY"; for kv in "${KV[@]}"; do "$RD" --option "${kv%%=*}" "${kv#*=}" >/dev/null 2>&1 || true; done
ID=""; for i in $(seq 1 15); do ID="$("$RD" --get-id 2>/dev/null | tr -d '[:space:]' || true)"; [ -n "$ID" ] && break; sleep 2; done
[ -n "$ID" ] || { echo "RustDesk didn't give an ID yet - open RustDesk once, then run this again."; exit 1; }

field() { sed -n "s/.*\"$1\": *\"\([^\"]*\)\".*/\1/p" | head -1; }
R="$(curl -fsS -X POST "$BASE/api/method/qtt_platform.api.workplace_agent.enroll" --data-urlencode "code=$CODE" --data-urlencode "rustdesk_id=$ID" --data-urlencode "os=$OS" --data-urlencode "host=$(hostname)")"
KEY="$(echo "$R" | field agent_key)"; PW="$(echo "$R" | field password)"
[ -n "$KEY" ] && [ -n "$PW" ] || { echo "QTT didn't accept the setup code (it works once, for an hour) - make a new one."; exit 1; }
"$RD" --password "$PW" >/dev/null 2>&1

umask 077; mkdir -p "$DIR"; chmod 700 "$DIR"
printf 'BASE=%q\nKEY=%q\nRD=%q\n' "$BASE" "$KEY" "$RD" > "$DIR/agent.env"
cat > "$DIR/agent.sh" <<'AGENT'
#!/bin/bash
set -uo pipefail
. /etc/qtt-remote-help/agent.env
field() { sed -n "s/.*\"$1\": *\"\([^\"]*\)\".*/\1/p" | head -1; }
ID="$("$RD" --get-id 2>/dev/null | tr -d '[:space:]')"
R="$(curl -fsS -X POST "$BASE/api/method/qtt_platform.api.workplace_agent.sync" --data-urlencode "agent_key=$KEY" --data-urlencode "rustdesk_id=$ID" --data-urlencode "version=__QTT_VERSION__")" || exit 0
CFG="$(echo "$R" | field config)"; [ -n "$CFG" ] && "$RD" --config "$CFG" >/dev/null 2>&1
for k in direct-server enable-lan-discovery allow-remote-config-modification enable-tunnel verification-method allow-auto-disconnect auto-disconnect-timeout; do
  v="$(echo "$R" | field "$k")"; [ -n "$v" ] && "$RD" --option "$k" "$v" >/dev/null 2>&1
done
PW="$(echo "$R" | field password)"; NONCE="$(echo "$R" | field nonce)"
if [ -n "$PW" ]; then
  "$RD" --password "$PW" >/dev/null 2>&1 && curl -fsS -X POST "$BASE/api/method/qtt_platform.api.workplace_agent.confirm" --data-urlencode "agent_key=$KEY" --data-urlencode "nonce=$NONCE" >/dev/null
  if echo "$R" | grep -q '"lock": *true'; then
    rm -f /etc/cron.d/qtt-remote-help; launchctl bootout system /Library/LaunchDaemons/in.queentouchtech.remote-help.plist 2>/dev/null
    rm -f /Library/LaunchDaemons/in.queentouchtech.remote-help.plist; rm -rf /etc/qtt-remote-help
  fi
fi
AGENT
chmod 700 "$DIR/agent.sh"

if [ "$OS" = mac ]; then
  cat > /Library/LaunchDaemons/in.queentouchtech.remote-help.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>in.queentouchtech.remote-help</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/agent.sh</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST
  launchctl bootstrap system /Library/LaunchDaemons/in.queentouchtech.remote-help.plist 2>/dev/null || launchctl load /Library/LaunchDaemons/in.queentouchtech.remote-help.plist
else
  echo "*/15 * * * * root /bin/bash $DIR/agent.sh >/dev/null 2>&1" > /etc/cron.d/qtt-remote-help
  echo "@reboot root sleep 60; /bin/bash $DIR/agent.sh >/dev/null 2>&1" >> /etc/cron.d/qtt-remote-help
  chmod 644 /etc/cron.d/qtt-remote-help
fi
echo
echo "Done - this computer is in QTT OS > Remote help as $(hostname) (RustDesk ID $ID)."
echo "Its RustDesk password is managed by QTT and changes by itself when access is revoked."
