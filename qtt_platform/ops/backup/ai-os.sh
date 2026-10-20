#!/bin/bash
# QTT backup on QTT-AI-OS (31.220.83.224) — /usr/local/bin/qtt-backup, /etc/cron.d/qtt-backup (22:35 CEST daily)
# A consistent copy of Garage's metadata (garage meta snapshot) just before the Frappe server pulls the Files store
# (read-only key, rrsync on /opt/qtt-workplace/garage). Snapshots older than 3 days are removed here.
set -uo pipefail
G=/opt/qtt-workplace/garage
if docker exec qtt-workplace-garage-1 /garage meta snapshot >/tmp/qtt-backup-garage.log 2>&1; then
  find "$G/meta/snapshots" -mindepth 1 -maxdepth 1 -mtime +2 -exec rm -rf {} +
  /usr/local/bin/qtt-backup-status garage-snapshot "Files store metadata snapshot" 1 - "$(ls "$G/meta/snapshots" | wc -l) kept"
else
  /usr/local/bin/qtt-backup-status garage-snapshot "Files store metadata snapshot" 0 - "$(tail -1 /tmp/qtt-backup-garage.log | cut -c1-120)"
fi
