#!/bin/bash
# QTT backup watch on the CloudPanel server (169.58.212.154) — /usr/local/bin/qtt-backup, /etc/cron.d/qtt-backup
# (05:30 daily). CloudPanel makes its own nightly backup of every site (/home/clp/backups/<date>, 04:15); this only
# checks the newest one is there and recent, for QTT Admin › Servers. It reads nothing inside the backups.
set -uo pipefail
newest=$(find /home/clp/backups -mindepth 1 -maxdepth 1 -type d -mmin -1560 2>/dev/null | sort | tail -1)
if [ -n "$newest" ] && [ -n "$(ls -A "$newest" 2>/dev/null)" ]; then
  /usr/local/bin/qtt-backup-status cloudpanel "CloudPanel sites (CloudPanel's own nightly backup)" 1 - "$(basename "$newest"), $(du -sh "$newest" | cut -f1)"
else
  /usr/local/bin/qtt-backup-status cloudpanel "CloudPanel sites (CloudPanel's own nightly backup)" 0 - "no CloudPanel backup in the last 26 hours"
fi
