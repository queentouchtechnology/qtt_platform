"""
Office Pulse Files — encryption at rest (PROJ-0016 E; the owner chose this instead of end-to-end encryption, which
would break preview, search and editing). QTT Workplace Settings › Encrypt stored files:

  on   new files are written encrypted at once (file_store.py); this job re-writes every file already stored —
       versions and the recycle bin too — encrypted with its business's key, in place
  off  the job writes them back plain

Each object is copied onto itself only if it hasn't changed since it was looked at (If-Match), so a file someone saves
meanwhile is never overwritten with its older copy. Progress shows in Settings › Status; the job stops if the switch
is turned the other way while it runs.
"""

import frappe
from frappe.utils import now_datetime

from qtt_platform import file_store as store

SETTINGS = "QTT Workplace Settings"


def _status(text: str) -> None:
	frappe.db.set_single_value(SETTINGS, "encryption_status", text[:140])
	frappe.db.commit()


def _wanted() -> bool:
	return bool(frappe.db.get_single_value(SETTINGS, "encrypt_files"))


def is_plain(key: str) -> tuple[bool, dict | None]:
	"""(stored plain?, its head). An encrypted object can't be looked at without its key."""
	from botocore.exceptions import ClientError

	c, b = store._client(), store.bucket()
	try:
		return True, c.head_object(Bucket=b, Key=key)
	except ClientError as e:
		if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
			return True, None
	return False, c.head_object(Bucket=b, Key=key, **store._sse(key, on=True))


def switch(on: bool) -> dict:
	"""Re-write every stored file encrypted (on) or plain (off). → counts."""
	from botocore.exceptions import ClientError

	c, b = store._client(), store.bucket()
	changed = skipped = failed = seen = 0
	token = None
	_status(f"{'Encrypting' if on else 'Decrypting'} stored files…")
	while True:
		kw = {"Bucket": b, "MaxKeys": 500}
		if token:
			kw["ContinuationToken"] = token
		r = c.list_objects_v2(**kw)
		for o in r.get("Contents") or []:
			key = o["Key"]
			if key.endswith("/"):
				continue  # an empty folder's marker — nothing in it
			seen += 1
			try:
				plain, h = is_plain(key)
				if h is None or plain != on:
					skipped += 1  # gone, or already the way it should be
					continue
				args = {"Bucket": b, "Key": key, "CopySource": {"Bucket": b, "Key": key}, "MetadataDirective": "REPLACE",
						"CopySourceIfMatch": h.get("ETag"), "Metadata": h.get("Metadata") or {}}
				if h.get("ContentType"):
					args["ContentType"] = h["ContentType"]
				if on:
					args.update(store._sse(key, on=True))
				else:
					args.update(store._sse(key, on=True, prefix="CopySource"))
				c.copy_object(**args)
				changed += 1
			except ClientError as e:
				if e.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
					skipped += 1  # saved again meanwhile — the new copy is already written the new way
				else:
					failed += 1
					frappe.log_error(title="Files: encryption switch failed for a file", message=f"{key}\n{frappe.get_traceback()}")
			except Exception:
				failed += 1
				frappe.log_error(title="Files: encryption switch failed for a file", message=f"{key}\n{frappe.get_traceback()}")
			if seen % 100 == 0:
				if _wanted() != on:
					_status(f"Stopped after {changed} files — the switch was turned {'off' if on else 'on'}")
					return {"changed": changed, "skipped": skipped, "failed": failed, "stopped": True}
				_status(f"{'Encrypting' if on else 'Decrypting'}… {changed} files done")
		if not r.get("IsTruncated"):
			break
		token = r.get("NextContinuationToken")
	when = now_datetime().strftime("%d %b %Y %H:%M")
	word = "On" if on else "Off"
	_status(f"{word} — {changed} files {'encrypted' if on else 'decrypted'}, {skipped} already done{f', {failed} failed (Error Log)' if failed else ''} · {when}")
	return {"changed": changed, "skipped": skipped, "failed": failed}


def start(on: bool) -> None:
	frappe.enqueue("qtt_platform.files_crypto.switch", queue="long", timeout=6 * 3600, on=on, enqueue_after_commit=True,
				   job_id="qtt-files-encryption", deduplicate=True)
