#!/usr/bin/env python3
"""qtt-backup-status <job-file> <name> <ok 0|1> <path to measure or -> [detail] [max_age_hours]

Writes /var/lib/qtt-backup/<job-file>.json for the QTT server agent (QTT Admin › Servers shows a failed or missed
backup as a problem and alerts). Installed as /usr/local/bin/qtt-backup-status."""
import json
import os
import sys
import time

job, name, ok, path = sys.argv[1:5]
detail = sys.argv[5] if len(sys.argv) > 5 else ""
max_age = int(sys.argv[6]) if len(sys.argv) > 6 else 26
size = 0
if path != "-" and os.path.exists(path):
    for root, _dirs, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            if not os.path.islink(p):
                st = os.lstat(p)
                if st.st_nlink == 1:  # blocks hard-linked from yesterday's copy aren't counted again
                    size += st.st_size
os.makedirs("/var/lib/qtt-backup", exist_ok=True)
tmp = f"/var/lib/qtt-backup/.{job}.json"
with open(tmp, "w") as f:
    json.dump({"name": name, "ok": ok == "1", "finished_at": int(time.time()), "size_bytes": size, "detail": detail[:160],
               "max_age_hours": max_age}, f)
os.replace(tmp, f"/var/lib/qtt-backup/{job}.json")
