#!/bin/bash
# QTT off-server copy on the n8n server (173.249.7.188) — /usr/local/bin/qtt-backup, /etc/cron.d/qtt-backup (03:45 IST)
# The Frappe server pushes each day's sites backup (databases + site configs) into /root/qtt-backups/incoming — its key
# can only write there (rrsync -wo); this server's outbound SSH is blocked on purpose, so it doesn't pull. This job
# moves it into /root/qtt-backups/frappe/<day>/, out of that key's reach, keeps 30 days, and links a files archive left
# out because it hadn't changed. The encrypted Files store is NOT copied here: no server other than the Frappe server
# holds both the files and the key that opens them.
set -uo pipefail
IN=/root/qtt-backups/incoming
OUT=/root/qtt-backups/frappe
umask 077
mkdir -p "$IN" "$OUT"; chmod 700 /root/qtt-backups
for d in "$IN"/20*; do
  [ -d "$d" ] || continue
  day=${d##*/}
  prev=$(ls -1d "$OUT"/20* 2>/dev/null | grep -v "/$day$" | tail -1)
  rm -rf "$OUT/$day.new"; mv "$d" "$OUT/$day.new"
  if [ -n "$prev" ]; then  # files archives not sent (unchanged): hard links to the day before
    for old in "$prev"/*files.tar; do
      [ -e "$old" ] || continue
      t=${old##*/}; t=${t#*-}
      ls "$OUT/$day.new"/*-"$t" >/dev/null 2>&1 || ln "$old" "$OUT/$day.new/${old##*/}"
    done
  fi
  rm -rf "$OUT/$day"; mv "$OUT/$day.new" "$OUT/$day"; touch "$OUT/$day"
done
find "$OUT" -mindepth 1 -maxdepth 1 -type d -mtime +29 -exec rm -rf {} +
newest=$(find "$OUT" -mindepth 1 -maxdepth 1 -type d -name '20*' -mmin -1560 | sort | tail -1)
if [ -n "$newest" ] && ls "$newest" | grep -q database && ls "$newest" | grep -q site_config; then
  /usr/local/bin/qtt-backup-status frappe-offsite "Frappe sites off-server copy" 1 "$newest" "$(ls -d "$OUT"/20* | wc -l) days kept"
else
  /usr/local/bin/qtt-backup-status frappe-offsite "Frappe sites off-server copy" 0 - "no copy from the Frappe server in the last 26 hours"
fi
