"""
Office Pulse Files — search (PROJ-0016 B): file and folder names, tags, and the words inside PDFs, Word, Excel,
PowerPoint and text files (files_text.py). The index (QTT File Index) follows every change: files_core calls
index_later on a save, a new file, a restore; a rename moves its row (files_core.rekey), a delete removes it.

  search    what this person may open that matches every word: their spaces (folder rules apply), their own files,
            what's shared with them — name, where it is, a piece of the text around the match
  reindex   (System Manager) build the index for a business, or all of them
"""

import frappe

from qtt_platform import file_store as store
from qtt_platform import files_core as core
from qtt_platform import files_text as ft
from qtt_platform import workplace_rules as rules

INDEX = "QTT File Index"
MAX_BYTES = 50 * 1024 * 1024  # bigger files are found by name only


# ---- keeping the index -------------------------------------------------------------------------------------------------
def index_key(key: str) -> None:
	"""(Re)read one file into the index — or drop its row when it's gone."""
	tenant = key.split("/", 1)[0]
	row = frappe.db.get_value(INDEX, {"tenant": tenant, "file_key": key})
	h = store.head(key)
	if not h or key.endswith("/"):
		if row:
			frappe.delete_doc(INDEX, row, ignore_permissions=True, force=True)
		return
	size = int(h.get("ContentLength") or 0)
	name = key.rsplit("/", 1)[-1]
	text = ft.text_of(name, store.read(key)) if size <= MAX_BYTES and rules.ext(name) else ""
	if row:
		frappe.db.set_value(INDEX, row, {"size": size, "words": len(text), "body": text})
	else:
		frappe.get_doc({"doctype": INDEX, "tenant": tenant, "file_key": key, "size": size, "words": len(text), "body": text}).insert(ignore_permissions=True)


def index_prefix(prefix: str) -> int:
	n = 0
	for o in store.keys_under(prefix):
		if not o["Key"].endswith("/") and "/.versions/" not in o["Key"] and "/.bin/" not in o["Key"]:
			index_key(o["Key"])
			n += 1
	return n


def run_index(key: str = "", prefix: str = "") -> None:
	"""Background job: index a file or everything under a folder."""
	try:
		index_prefix(prefix) if prefix else index_key(key)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Files: search index not updated")


@frappe.whitelist()
def reindex(tenant: str = "") -> dict:
	"""(System Manager) Build the search index for one business, or every business."""
	frappe.only_for("System Manager")
	tenants = [tenant] if tenant else sorted({o["Key"].split("/", 1)[0] for o in store.keys_under("") if "/" in o["Key"] and not o["Key"].startswith("trash/")})
	done = {}
	for t in tenants:
		done[t] = index_prefix(f"{t}/")
		frappe.db.commit()
	return done


# ---- search ------------------------------------------------------------------------------------------------------------
def _where(ctx, key: str, shares: list, hr_folder: str):
	"""Where this person reaches this file (space, path) — or None."""
	from qtt_platform.api.workplace import _at

	parts = key.split("/", 2)
	if len(parts) < 3 or parts[0] != ctx.tenant:
		return None
	kind, rest = parts[1], parts[2]
	cand = []
	if kind in ("team", "company", "hr"):
		cand.append((kind, rest))
	if kind == "people" and rest.split("/", 1)[0] == rules.person_id(ctx.user):
		cand.append(("mine", rest.split("/", 1)[1] if "/" in rest else ""))
	if kind == "hr" and hr_folder and (rest == hr_folder or rest.startswith(hr_folder.rstrip("/") + "/")):
		cand.append(("mydocs", rest[len(hr_folder.rstrip("/")):].lstrip("/")))
	for s in shares:
		if key == s.file_key or (s.is_dir and key.startswith(s.file_key.rstrip("/") + "/")):
			cand.append(("shared", s.name + key[len(s.file_key.rstrip("/")):]))
	for space, path in cand:
		if not path:
			continue
		try:
			if "read" in _at(ctx, space, path).rights:
				return space, path
		except frappe.PermissionError:
			continue
	return None


@frappe.whitelist(methods=["GET"])
def search(q: str = "", limit: int = 40) -> dict:
	"""Files this person may open that match every word — in the name, the folder, the tags or the text inside.
	→ {results: [{name, space, path, folder, snippet, size_text, type, editable, tags}]}"""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	words = ft.search_words(q)
	if not words:
		return {"results": [], "words": []}
	conds, params = [], [ctx.tenant]
	for w in words:
		like = "%" + core._like(w) + "%"
		conds.append("(i.file_key like %s or i.body like %s or ifnull(m.tags, '') like %s)")
		params += [like, like, like]
	rows = frappe.db.sql(f"""select i.file_key, i.size, i.body, m.tags from `tab{INDEX}` i
		left join `tab{core.META}` m on m.tenant = i.tenant and m.file_key = i.file_key
		where i.tenant = %s and {" and ".join(conds)} order by i.modified desc limit 300""", params, as_dict=True)
	shares = frappe.get_all(core.SHARE, filters={"tenant": ctx.tenant, "user": ctx.user}, fields=["name", "file_key", "is_dir"])
	hr_folder = frappe.db.get_value("QTT HR Folder", {"tenant": ctx.tenant, "user": ctx.user}, "folder") or ""
	out = []
	for r in rows:
		at = _where(ctx, r.file_key, shares, hr_folder)
		if not at:
			continue
		space, path = at
		name = path.rsplit("/", 1)[-1]
		in_name = all(w in r.file_key.lower() or w in (r.tags or "").lower() for w in words)
		out.append({"name": name, "space": space, "path": path, "folder": path.rsplit("/", 1)[0] if "/" in path else "",
					"snippet": "" if in_name else ft.snippet(r.body or "", words), "size_text": rules.human_size(r.size or 0),
					"type": rules.kind_of_file(name), "editable": rules.editable(name), "tags": [t for t in (r.tags or "").split(",") if t]})
		if len(out) >= min(int(limit or 40), 100):
			break
	return {"results": out, "words": words}
