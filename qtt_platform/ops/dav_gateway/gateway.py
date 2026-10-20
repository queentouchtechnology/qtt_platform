"""
QTT WebDAV gateway — Office Pulse Files as a drive (PROJ-0016 E2). Runs on QTT-AI-OS (/opt/qtt-workplace/dav, container
qtt-dav) behind Caddy at https://office.queentouchtech.in/dav/.

It holds no files and makes no decisions: every step is a call to Frappe (qtt_platform.api.dav.gw_*), signed with the
gateway secret and carrying the person's email + sync password, so rights, locks, versions, the recycle bin, activity,
quotas and encryption are exactly the app's. Only WebDAV's own locks and "dead" properties (what Windows / macOS keep
while editing) live here, in memory.

Env: QTT_URL (https://app.queentouchtech.in), QTT_GATEWAY_SECRET.
"""

import hashlib
import io
import os
import tempfile
import threading
import time
from datetime import datetime

import requests
from cheroot import wsgi
from wsgidav.util import join_uri  # first: wsgidav.dav_error and wsgidav.util import each other
from wsgidav.dav_error import (HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_INSUFFICIENT_STORAGE, HTTP_NOT_FOUND, HTTP_PRECONDITION_FAILED,
							   DAVError)
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider
from wsgidav.dc.base_dc import BaseDomainController
from wsgidav.wsgidav_app import WsgiDAVApp

QTT = os.environ.get("QTT_URL", "https://app.queentouchtech.in").rstrip("/") + "/api/method/qtt_platform.api.dav."
SECRET = os.environ["QTT_GATEWAY_SECRET"]
_local = threading.local()


def _session() -> requests.Session:
	s = getattr(_local, "s", None)
	if s is None:
		s = _local.s = requests.Session()
	return s


def call(environ, op: str, method="GET", params=None, data=None, raw=False):
	"""One call to Frappe as the person signed in on this request."""
	user, pw = environ["qtt.creds"]
	r = _session().request(method, QTT + op, params=params, data=data, timeout=(10, 300),
						   headers={"X-QTT-Gateway": SECRET, "X-QTT-User": user, "X-QTT-Pass": pw, "Accept": "application/json"})
	if r.status_code >= 400:
		text = r.text[:400]
		if r.status_code == 404:
			raise DAVError(HTTP_NOT_FOUND)
		if r.status_code in (401, 403):
			raise DAVError(HTTP_FORBIDDEN, text[:120])
		if "space is full" in text:
			raise DAVError(HTTP_INSUFFICIENT_STORAGE)
		if "exists" in text:
			raise DAVError(HTTP_PRECONDITION_FAILED)
		raise DAVError(HTTP_CONFLICT, text[:120])
	return r.content if raw else r.json().get("message")


def _ts(s) -> float | None:
	try:
		return datetime.fromisoformat(str(s)).timestamp() if s else None
	except ValueError:
		return None


def listing(environ, path: str) -> list[dict]:
	"""A folder's items, asked once per request."""
	cache = environ.setdefault("qtt.cache", {})
	key = path.rstrip("/") or "/"
	if key not in cache:
		cache[key] = call(environ, "gw_list", params={"path": key})["items"]
	return cache[key]


def forget(environ):
	environ.pop("qtt.cache", None)


class Folder(DAVCollection):
	def __init__(self, path, environ, info=None):
		super().__init__(path, environ)
		self.info = info or {}

	def get_display_name(self):
		return self.name

	def get_member_names(self):
		return [i["name"] for i in listing(self.environ, self.path)]

	def get_member(self, name):
		for i in listing(self.environ, self.path):
			if i["name"] == name:
				p = join_uri(self.path, name)
				return Folder(p, self.environ, i) if i["is_dir"] else File(p, self.environ, i)
		return None

	def get_member_list(self):
		return [Folder(join_uri(self.path, i["name"]), self.environ, i) if i["is_dir"] else File(join_uri(self.path, i["name"]), self.environ, i)
				for i in listing(self.environ, self.path)]

	def get_last_modified(self):
		return _ts(self.info.get("modified"))

	def get_etag(self):
		return None

	def create_empty_resource(self, name):
		forget(self.environ)
		return File(join_uri(self.path, name), self.environ, {"name": name, "is_dir": False, "size": 0}, new=True)

	def create_collection(self, name):
		call(self.environ, "gw_mkdir", "POST", params={"path": join_uri(self.path, name)})
		forget(self.environ)

	def support_recursive_delete(self):
		return True

	def delete(self):
		call(self.environ, "gw_delete", "POST", params={"path": self.path})
		forget(self.environ)
		self.remove_all_properties(recursive=True)
		self.remove_all_locks(recursive=True)

	def copy_move_single(self, dest_path, *, is_move):
		if is_move:
			return self.move_recursive(dest_path)
		call(self.environ, "gw_mkdir", "POST", params={"path": dest_path.rstrip("/")})  # its contents are copied one by one after
		forget(self.environ)

	def support_recursive_move(self, dest_path):
		return True

	def move_recursive(self, dest_path):
		call(self.environ, "gw_move", "POST", params={"src": self.path.rstrip("/"), "dst": dest_path.rstrip("/"), "overwrite": 1})
		forget(self.environ)


class File(DAVNonCollection):
	def __init__(self, path, environ, info, new=False):
		super().__init__(path, environ)
		self.info, self.new, self._buf = info, new, None

	def get_content_length(self):
		return int(self.info.get("size") or 0)

	def get_content_type(self):
		import mimetypes

		return mimetypes.guess_type(self.name)[0] or "application/octet-stream"

	def get_display_name(self):
		return self.name

	def get_last_modified(self):
		return _ts(self.info.get("modified"))

	def get_etag(self):
		return hashlib.md5(str(self.info.get("etag") or self.path).encode()).hexdigest()

	def support_etag(self):
		return True

	def support_ranges(self):
		return True

	def get_content(self):
		return io.BytesIO(call(self.environ, "gw_get", params={"path": self.path}, raw=True))

	def begin_write(self, *, content_type=None):
		self._buf = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
		return _Keep(self._buf)

	def end_write(self, *, with_errors):
		buf, self._buf = self._buf, None
		if buf is None:
			return
		try:
			if not with_errors:
				buf.seek(0)
				call(self.environ, "gw_put", "POST", params={"path": self.path}, data=buf)
				forget(self.environ)
		finally:
			buf.close()

	def delete(self):
		call(self.environ, "gw_delete", "POST", params={"path": self.path})
		forget(self.environ)
		self.remove_all_properties(recursive=True)
		self.remove_all_locks(recursive=True)

	def copy_move_single(self, dest_path, *, is_move):
		call(self.environ, "gw_move" if is_move else "gw_copy", "POST", params={"src": self.path.rstrip("/"), "dst": dest_path.rstrip("/"), "overwrite": 1})
		forget(self.environ)

	def support_recursive_move(self, dest_path):
		return True

	def move_recursive(self, dest_path):
		self.copy_move_single(dest_path, is_move=True)


class _Keep:
	"""What WsgiDAV writes the upload into; closing it doesn't drop the data (end_write sends it)."""

	def __init__(self, f):
		self.f = f

	def write(self, b):
		return self.f.write(b)

	def close(self):
		pass


class Provider(DAVProvider):
	def get_resource_inst(self, path, environ):
		self._count_get_resource_inst += 1
		parts = [p for p in path.split("/") if p]
		if not parts:
			return Folder("/", environ, {"name": "", "is_dir": True})
		parent = "/" + "/".join(parts[:-1])
		for i in listing(environ, parent):
			if i["name"] == parts[-1]:
				p = "/" + "/".join(parts)
				return Folder(p, environ, i) if i["is_dir"] else File(p, environ, i)
		return None


_ok = {}


class Login(BaseDomainController):
	"""Email + sync password, checked by Frappe (remembered a minute)."""

	def get_domain_realm(self, path_info, environ):
		return "QTT Files"

	def require_authentication(self, realm, environ):
		return True

	def supports_http_digest_auth(self):
		return False

	def basic_auth_user(self, realm, user_name, password, environ):
		user = (user_name or "").strip().lower()
		key = hashlib.sha256(f"{user}|{password}".encode()).hexdigest()
		if _ok.get(key, 0) > time.time():
			environ["qtt.creds"] = (user, password)
			return True
		environ["qtt.creds"] = (user, password)
		try:
			call(environ, "gw_auth")
		except DAVError:
			environ.pop("qtt.creds", None)
			return False
		if len(_ok) > 5000:
			_ok.clear()
		_ok[key] = time.time() + 60
		return True


CONFIG = {
	"host": "0.0.0.0",
	"port": 8080,
	"provider_mapping": {"/dav": Provider()},  # Caddy passes /dav/… through as it is
	"http_authenticator": {"domain_controller": Login, "accept_basic": True, "accept_digest": False, "default_to_digest": False},
	"lock_storage": True,
	"property_manager": True,
	"dir_browser": {"enable": False},
	"hotfixes": {"emulate_win32_lastmod": True},
	"add_header_MS_Author_Via": True,
	"verbose": 2,
	"logging": {"enable": True},
}

if __name__ == "__main__":
	app = WsgiDAVApp(CONFIG)
	server = wsgi.Server((CONFIG["host"], CONFIG["port"]), app, numthreads=24, request_queue_size=48, timeout=300)
	print("QTT WebDAV gateway on :8080/dav", flush=True)
	try:
		server.start()
	except KeyboardInterrupt:
		server.stop()
