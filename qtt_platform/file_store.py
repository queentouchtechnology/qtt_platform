"""
Office Pulse Files' storage: one private S3 bucket (Garage on QTT-AI-OS — QTT Workplace Settings › storage_*), reached
only by Frappe. Folders are prefixes (an empty folder is a zero-byte "<name>/" marker). Nothing is ever deleted at
once: a deleted or replaced file is moved to trash/<day>/ and purged after 30 days (purge_trash, daily).
The rules (keys, listings, quotas) are in workplace_rules.py.
"""

import threading
from datetime import date

import frappe
from frappe import _

from qtt_platform import workplace_rules as rules

SETTINGS = "QTT Workplace Settings"
_local = threading.local()


def _client():
	"""One S3 client per worker thread (kept-alive connections), rebuilt when the settings change."""
	s = frappe.get_cached_doc(SETTINGS)
	secret = s.get_password("storage_secret", raise_exception=False)
	if not s.files_enabled or not s.storage_url or not s.storage_key or not secret:
		frappe.throw(_("Files aren't set up yet."))
	sig = f"{s.storage_url}|{s.storage_key}|{secret}"
	c = getattr(_local, "client", None)
	if c is None or getattr(_local, "sig", None) != sig:
		import boto3
		from botocore.config import Config

		c = boto3.client("s3", endpoint_url=s.storage_url.rstrip("/"), region_name=s.storage_region or "garage",
						 aws_access_key_id=s.storage_key, aws_secret_access_key=secret,
						 config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3},
									   connect_timeout=10, read_timeout=120, max_pool_connections=10))
		_local.client, _local.sig = c, sig
	return c


def bucket() -> str:
	return frappe.get_cached_doc(SETTINGS).storage_bucket or "qtt-files"


def _fail(e: Exception, what: str):
	from botocore.exceptions import ClientError

	code = e.response.get("Error", {}).get("Code") if isinstance(e, ClientError) else None
	if code in ("NoSuchKey", "404", "NotFound"):
		frappe.throw(_("That isn't here any more."), frappe.DoesNotExistError)
	frappe.log_error(title=f"Files: storage {what} failed", message=frappe.get_traceback())
	frappe.throw(_("Files are having a problem right now. Please try again in a minute."))


# ---- reading -----------------------------------------------------------------------------------------------------------
def list_folder(prefix: str) -> list[dict]:
	"""One folder's items (folders first)."""
	folders, files, token = [], [], None
	try:
		while True:
			kw = {"Bucket": bucket(), "Prefix": prefix, "Delimiter": "/", "MaxKeys": 1000}
			if token:
				kw["ContinuationToken"] = token
			r = _client().list_objects_v2(**kw)
			folders += [p["Prefix"] for p in r.get("CommonPrefixes") or []]
			files += r.get("Contents") or []
			if not r.get("IsTruncated"):
				break
			token = r.get("NextContinuationToken")
	except Exception as e:
		_fail(e, "list")
	return rules.listing(prefix, folders, files)


def keys_under(prefix: str) -> list[dict]:
	"""Every object under a prefix (deep): [{Key, Size, ETag}]."""
	out, token = [], None
	try:
		while True:
			kw = {"Bucket": bucket(), "Prefix": prefix, "MaxKeys": 1000}
			if token:
				kw["ContinuationToken"] = token
			r = _client().list_objects_v2(**kw)
			out += r.get("Contents") or []
			if not r.get("IsTruncated"):
				break
			token = r.get("NextContinuationToken")
	except Exception as e:
		_fail(e, "list")
	return out


def used(prefix: str) -> int:
	"""Bytes used under a prefix (kept a minute — every upload clears it)."""
	key = f"qtt_files_used|{prefix}"
	hit = frappe.cache().get_value(key)
	if hit is not None:
		return int(hit)
	n = sum(int(o.get("Size") or 0) for o in keys_under(prefix))
	frappe.cache().set_value(key, n, expires_in_sec=60)
	return n


def _forget_use(key: str) -> None:
	parts = key.split("/")
	for i in range(2, min(len(parts), 4) + 1):  # <tenant>/<space>/ and <tenant>/people/<id>/
		frappe.cache().delete_value(f"qtt_files_used|{'/'.join(parts[:i])}/")


def head(key: str) -> dict | None:
	from botocore.exceptions import ClientError

	try:
		return _client().head_object(Bucket=bucket(), Key=key)
	except ClientError as e:
		if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
			return None
		_fail(e, "head")


def read(key: str) -> bytes:
	try:
		return _client().get_object(Bucket=bucket(), Key=key)["Body"].read()
	except Exception as e:
		_fail(e, "read")


# ---- writing -----------------------------------------------------------------------------------------------------------
def _today() -> str:
	return date.today().isoformat()


def to_trash(key: str) -> None:
	"""Keep a copy for 30 days (a deleted or replaced file), then remove the original."""
	try:
		_client().copy_object(Bucket=bucket(), Key=rules.trash_key(key, _today()), CopySource={"Bucket": bucket(), "Key": key})
		_client().delete_object(Bucket=bucket(), Key=key)
	except Exception as e:
		_fail(e, "trash")
	_forget_use(key)


def write(key: str, data: bytes, content_type: str | None = None) -> str:
	"""Put a file (an older one with the same name goes to the trash first). → its etag."""
	if head(key):
		try:
			_client().copy_object(Bucket=bucket(), Key=rules.trash_key(key, _today()), CopySource={"Bucket": bucket(), "Key": key})
		except Exception as e:
			_fail(e, "keep old version")
	try:
		kw = {"ContentType": content_type} if content_type else {}
		r = _client().put_object(Bucket=bucket(), Key=key, Body=data, **kw)
	except Exception as e:
		_fail(e, "write")
	_forget_use(key)
	return str(r.get("ETag") or "").strip('"')


def mkdir(prefix: str) -> None:
	try:
		_client().put_object(Bucket=bucket(), Key=prefix.rstrip("/") + "/", Body=b"")
	except Exception as e:
		_fail(e, "folder")


def delete(key: str, is_dir: bool) -> int:
	"""A file, or a folder with everything in it, to the trash. → how many files."""
	objs = keys_under(key.rstrip("/") + "/") if is_dir else [{"Key": key}]
	for o in objs:
		if o["Key"].endswith("/"):
			_client().delete_object(Bucket=bucket(), Key=o["Key"])  # a folder marker: nothing to keep
		else:
			to_trash(o["Key"])
	return len(objs)


def move(old: str, new: str, is_dir: bool) -> None:
	"""Rename a file or a folder (S3 has no rename: copy, then remove the original)."""
	pairs = ([(o["Key"], new.rstrip("/") + "/" + o["Key"][len(old.rstrip("/") + "/"):]) for o in keys_under(old.rstrip("/") + "/")]
			 if is_dir else [(old, new)])
	try:
		for a, b in pairs:
			_client().copy_object(Bucket=bucket(), Key=b, CopySource={"Bucket": bucket(), "Key": a})
		for a, _b in pairs:
			_client().delete_object(Bucket=bucket(), Key=a)
	except Exception as e:
		_fail(e, "rename")


def exists_dir(prefix: str) -> bool:
	try:
		r = _client().list_objects_v2(Bucket=bucket(), Prefix=prefix.rstrip("/") + "/", MaxKeys=1)
	except Exception as e:
		_fail(e, "list")
	return bool(r.get("KeyCount"))


# ---- trash -------------------------------------------------------------------------------------------------------------
def purge_trash() -> None:
	"""Scheduler (daily): files deleted or replaced more than 30 days ago are removed for good."""
	try:
		s = frappe.get_cached_doc(SETTINGS)
		if not s.files_enabled or not s.storage_url:
			return
		r = _client().list_objects_v2(Bucket=bucket(), Prefix=rules.TRASH, Delimiter="/")
		days = [p["Prefix"][len(rules.TRASH):].strip("/") for p in r.get("CommonPrefixes") or []]
		for day in rules.trash_days_to_purge(days, _today()):
			objs = keys_under(f"{rules.TRASH}{day}/")
			for i in range(0, len(objs), 1000):
				_client().delete_objects(Bucket=bucket(), Delete={"Objects": [{"Key": o["Key"]} for o in objs[i:i + 1000]], "Quiet": True})
	except Exception:
		frappe.log_error(title="Files: trash purge failed")
