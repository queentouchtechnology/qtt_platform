#!/bin/bash
# QTT off-server copy on the n8n server (173.249.7.188) — /usr/local/bin/qtt-backup, /etc/cron.d/qtt-backup (03:45 IST)
# Pulls the Frappe sites' backups (databases + site configs) from the Frappe server, read-only key (rrsync on
# /root/qtt-backups/frappe), into /root/qtt-backups/frappe/ — 30 days. The encrypted Files store is NOT copied here:
# no server other than the Frappe server holds both the files and the key that opens them.
set -uo pipefail
OUT=/root/qtt-backups/frappe
umask 077
mkdir -p "$OUT"; chmod 700 /root/qtt-backups
if rsync -a -e "ssh -i /root/.ssh/qtt_backup_pull -o BatchMode=yes -o ConnectTimeout=20" root@185.217.127.94:/ "$OUT/" >/tmp/qtt-backup-offsite.log 2>&1 \
   && newest=$(find "$OUT" -mindepth 1 -maxdepth 1 -type d -name '20*' -mmin -1560 | sort | tail -1) && ls "$newest" | grep -q database; then
  # (the Frappe server names days by its own clock � CEST; the copy is checked by age, not by today's date here)
  find "$OUT" -mindepth 1 -maxdepth 1 -type d -mtime +29 -exec rm -rf {} +
  /usr/local/bin/qtt-backup-status frappe-offsite "Frappe sites off-server copy" 1 "$newest" "$(ls -d "$OUT"/20* | wc -l) days kept"
else
  /usr/local/bin/qtt-backup-status frappe-offsite "Frappe sites off-server copy" 0 - "$(tail -1 /tmp/qtt-backup-offsite.log | cut -c1-120)"
fi
