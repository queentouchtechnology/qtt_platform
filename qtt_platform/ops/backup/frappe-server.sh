#!/bin/bash
# QTT backup on the Frappe server (185.217.127.94) — /usr/local/bin/qtt-backup, /etc/cron.d/qtt-backup (22:45 CEST daily)
#  1. Frappe sites: each site's database, site config (holds encryption_key — without it no password or the files key
#     can be opened) and its files → /root/qtt-backups/frappe/<day>/ (14 days). The n8n server copies this folder.
#  2. Files store: the Garage data of Office Pulse Files (already encrypted — SSE-C) and its metadata snapshot, pulled
#     from QTT-AI-OS read-only → /root/qtt-backups/files-store/<day>/ (14 days, unchanged blocks hard-linked).
# Status for QTT Admin › Servers: /var/lib/qtt-backup/{frappe-sites,files-store}.json (qtt-backup-status).
set -uo pipefail
DAY=$(date +%F)
ROOT=/root/qtt-backups
C=docker-frappe-1
B=/home/frappe/frappe-bench
umask 077
mkdir -p "$ROOT/frappe/$DAY" "$ROOT/files-store"
chmod 700 "$ROOT"

# ---- 1. Frappe sites --------------------------------------------------------------------------------------------------
ok=1; why=""
for site in $(docker exec $C bash -lc "ls $B/sites" | grep -E '\.' | grep -vE '\.(json|txt)$'); do
  if ! docker exec -u frappe $C bash -lc "cd $B && bench --site $site backup --with-files" >"/tmp/qtt-backup-$site.log" 2>&1; then
    ok=0; why="bench backup failed for $site"; continue
  fi
  dir=$B/sites/$site/private/backups
  stamp=$(docker exec $C bash -lc "ls -t $dir/*-database.sql.gz | head -1 | xargs -n1 basename | cut -d- -f1")
  for f in $(docker exec $C bash -lc "ls $dir/${stamp}-*"); do
    docker cp "$C:$f" "$ROOT/frappe/$DAY/" >/dev/null || { ok=0; why="copy failed for $site"; }
  done
  gzip -t "$ROOT/frappe/$DAY/${stamp}"-*-database.sql.gz 2>/dev/null || { ok=0; why="database dump unreadable for $site"; }
  ls "$ROOT/frappe/$DAY/${stamp}"-*site_config_backup.json >/dev/null 2>&1 || { ok=0; why="site config missing for $site"; }
  docker exec $C bash -lc "find $dir -type f -mtime +2 -delete"  # the container keeps only the last few days
done
docker cp "$C:$B/sites/common_site_config.json" "$ROOT/frappe/$DAY/common_site_config.json" >/dev/null 2>&1 || true
find "$ROOT/frappe" -mindepth 1 -maxdepth 1 -type d -mtime +13 -exec rm -rf {} +
/usr/local/bin/qtt-backup-status frappe-sites "Frappe sites (database, site config, files)" "$ok" "$ROOT/frappe/$DAY" "${why:-$(ls "$ROOT/frappe/$DAY" | wc -l) files}"

# ---- 2. Files store (Garage on QTT-AI-OS) -----------------------------------------------------------------------------
prev=$(ls -1d "$ROOT"/files-store/20* 2>/dev/null | grep -v "/$DAY$" | tail -1)
if rsync -a --delete --exclude 'meta/db.sqlite*' ${prev:+--link-dest="$prev"} -e "ssh -i /root/.ssh/qtt_backup_pull -o BatchMode=yes -o ConnectTimeout=20" \
     root@31.220.83.224:/ "$ROOT/files-store/$DAY/" >/tmp/qtt-backup-files-store.log 2>&1 \
   && ls "$ROOT/files-store/$DAY/meta/snapshots" | grep -q .; then
  find "$ROOT/files-store" -mindepth 1 -maxdepth 1 -type d -mtime +13 -exec rm -rf {} +
  /usr/local/bin/qtt-backup-status files-store "Office Pulse Files store (encrypted)" 1 "$ROOT/files-store/$DAY" "$(find "$ROOT/files-store/$DAY/data" -type f | wc -l) blocks"
else
  /usr/local/bin/qtt-backup-status files-store "Office Pulse Files store (encrypted)" 0 - "$(tail -1 /tmp/qtt-backup-files-store.log | cut -c1-120)"
fi
