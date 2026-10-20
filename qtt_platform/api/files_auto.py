"""
Office Pulse Files — automatic rules (PROJ-0016 B2; matching in files_rules.auto_matches): when a file is uploaded (in
the app or through a File Drop link) or tagged, in a space / folder, of some kinds, with some words in its name →
add tags, move it (to a folder that can name the year and month), tell people, share it with people.

  automations / save_automation / delete_automation   owners and admins (HR: rules in HR and Company)
  run                                                  called after an upload or a tag change (never raises)
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from qtt_platform import file_store as store
from qtt_platform import files_core as core
from qtt_platform import files_rules as fr
from qtt_platform import workplace_rules as rules

AUTO = "QTT File Automation"
FIELDS = ("title", "enabled", "event", "space", "folder", "kinds", "name_words", "has_tag", "add_tags", "move_to", "notify", "share_with", "share_permission")

TEMPLATES = [
	{"key": "payslips", "title": "Payslips into a folder for each month", "event": "upload", "space": "hr", "kinds": "pdf",
	 "name_words": "payslip, pay slip, salary slip", "add_tags": "Payslip", "move_to": "Payslips/{year}/{month}"},
	{"key": "letters", "title": "Offer and appointment letters", "event": "upload", "space": "hr", "kinds": "pdf, word",
	 "name_words": "offer, appointment, joining, relieving, experience", "add_tags": "Letter", "move_to": "Letters/{year}"},
	{"key": "ids", "title": "ID proofs", "event": "upload", "space": "hr", "kinds": "pdf, image",
	 "name_words": "aadhaar, aadhar, pan, passport, licence, license, voter", "add_tags": "ID proof", "move_to": "ID proofs"},
	{"key": "invoices", "title": "Invoices to Accounts", "event": "upload", "space": "team", "kinds": "pdf, cell",
	 "name_words": "invoice, bill, receipt", "add_tags": "Invoice", "move_to": "Accounts/Invoices/{year}"},
	{"key": "contracts", "title": "Tell me about new contracts", "event": "upload", "space": "team", "kinds": "",
	 "name_words": "contract, agreement", "add_tags": "Contract", "move_to": ""},
]


def _may(ctx, space: str) -> bool:
	return bool(ctx.admin or (ctx.hr and space in ("hr", "company")))


def _out(a, names: dict) -> dict:
	d = {f: a.get(f) for f in FIELDS}
	d.update({"name": a.name, "runs": a.runs or 0, "enabled": bool(a.enabled),
			  "notify_names": [names.get(u, u) for u in fr._csv(a.notify)],
			  "share_names": [names.get(u, u) for u in fr._csv(a.share_with)]})
	return d


@frappe.whitelist(methods=["GET"])
def automations() -> dict:
	"""The business's automatic rules this person may manage, ready-made ones to start from, the people to tell."""
	from qtt_platform.api.files_share import _pulse_people
	from qtt_platform.api.team import _names
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	if not (ctx.admin or ctx.hr):
		frappe.throw(_("Owners, admins and HR set automatic rules."), frappe.PermissionError)
	names = _names(ctx)
	rows = [a for a in frappe.get_all(AUTO, filters={"tenant": ctx.tenant}, fields=["name", "runs", *FIELDS], order_by="creation asc") if _may(ctx, a.space or "")]
	return {"rules": [_out(a, names) for a in rows], "templates": [t for t in TEMPLATES if _may(ctx, t["space"])],
			"people": [{"user": u, "title": p["name"]} for u, p in sorted(_pulse_people(ctx).items(), key=lambda x: x[1]["name"])],
			"kinds": list(fr.AUTO_KINDS), "spaces": [s for s in ("team", "company", "hr") if _may(ctx, s)]}


@frappe.whitelist(methods=["POST"])
def save_automation(data=None) -> dict:
	"""Make or change a rule. data: {name (to change), title, enabled, event: upload | tag, space, folder, kinds,
	name_words, has_tag, add_tags, move_to, notify, share_with, share_permission}."""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	d = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	space = d.get("space") or ""
	if space not in ("team", "company", "hr") or not _may(ctx, space):
		frappe.throw(_("Choose Team files, Company or HR — HR sets rules in HR and Company."), frappe.PermissionError)
	if not str(d.get("title") or "").strip():
		frappe.throw(_("Give the rule a name."))
	if not any(str(d.get(k) or "").strip() for k in ("add_tags", "move_to", "notify", "share_with")):
		frappe.throw(_("Choose what the rule does: add tags, move the file, tell people or share it."))
	if d.get("event") == "tag" and not str(d.get("has_tag") or "").strip():
		frappe.throw(_("Say which tag starts the rule."))
	doc = frappe.get_doc(AUTO, d["name"]) if d.get("name") else frappe.get_doc({"doctype": AUTO, "tenant": ctx.tenant, "created_by": ctx.user})
	if doc.tenant != ctx.tenant:
		frappe.throw(_("That rule isn't here any more."), frappe.DoesNotExistError)
	for f in FIELDS:
		if f in d:
			v = d[f]
			if isinstance(v, list):
				v = ", ".join(str(x) for x in v)
			doc.set(f, (1 if v else 0) if f == "enabled" else (rules.clean_path(v) if f == "folder" else (str(v or "")[:2000])))
	doc.event = doc.event if doc.event in fr.AUTO_EVENTS else "upload"
	doc.save(ignore_permissions=True)
	return automations()


@frappe.whitelist(methods=["POST"])
def delete_automation(name: str) -> dict:
	"""Remove a rule (files it already moved or tagged stay as they are)."""
	from qtt_platform.api.workplace import _ctx

	ctx = _ctx()
	a = frappe.db.get_value(AUTO, {"name": name, "tenant": ctx.tenant}, ["name", "space"], as_dict=True)
	if a and _may(ctx, a.space or ""):
		frappe.delete_doc(AUTO, a.name, ignore_permissions=True, force=True)
	return automations()


# ---- running -----------------------------------------------------------------------------------------------------------
def _members(tenant: str, users: list[str]) -> list[str]:
	return [u for u in users if frappe.db.exists("QTT Tenant Membership", {"tenant": tenant, "user": u, "status": "active"})]


def run(tenant: str, event: str, space: str, path: str, key: str, by: str) -> str:
	"""Apply the business's rules to a file that was just uploaded or tagged. → its key afterwards (a rule may move
	it). Never raises: a rule that can't act is logged."""
	try:
		rows = frappe.get_all(AUTO, filters={"tenant": tenant, "enabled": 1, "event": event}, fields=["name", "runs", *FIELDS], order_by="creation asc")
		if not rows:
			return key
		meta = frappe.db.get_value(core.META, {"tenant": tenant, "file_key": key}, ["name", "tags"], as_dict=True)
		tags = [t for t in ((meta.tags if meta else "") or "").split(",") if t]
		kind = rules.kind_of_file(path.rsplit("/", 1)[-1])
		hits = [a for a in rows if fr.auto_matches(a, event=event, space=space, path=path, kind=kind, tags=tags)]
		for a in hits:
			key, path = _act(tenant, a, space, path, key, by, tags)
			frappe.db.set_value(AUTO, a.name, "runs", (a.runs or 0) + 1, update_modified=False)
		return key
	except Exception:
		frappe.log_error(title="Files: an automatic rule couldn't act")
		return key


def _act(tenant: str, a, space: str, path: str, key: str, by: str, tags: list[str]) -> tuple[str, str]:
	done = []
	new_tags = fr.auto_tags(a.add_tags)
	if new_tags:
		name = frappe.db.get_value(core.META, {"tenant": tenant, "file_key": key})
		m = frappe.get_doc(core.META, name) if name else frappe.get_doc({"doctype": core.META, "tenant": tenant, "file_key": key})
		merged = sorted(set(tags) | set(new_tags))[:12]
		m.tags = ",".join(merged)
		m.save(ignore_permissions=True)
		tags[:] = merged
		done.append("tags " + ", ".join(new_tags))
	folder = fr.auto_folder(a.move_to, now_datetime())
	if folder:
		prefix = key[: len(key) - len(path)]  # the space's start in the store
		name = path.rsplit("/", 1)[-1]
		stem, dot, ext = name.rpartition(".") if "." in name else (name, "", "")
		target_path, n = f"{folder}/{name}", 1
		while store.head(prefix + target_path) and prefix + target_path != key:
			n += 1
			target_path = f"{folder}/{stem} ({n}).{ext}" if dot else f"{folder}/{name} ({n})"
		if prefix + target_path != key:
			store.mkdir(prefix + folder)
			store.copy(key, prefix + target_path)
			store.remove([key])
			core.rekey(tenant, key, prefix + target_path, False)
			key, path = prefix + target_path, target_path
			done.append("moved to " + folder)
	share = _members(tenant, fr._csv(a.share_with))
	for u in share:
		if u != by and not frappe.db.exists(core.SHARE, {"tenant": tenant, "user": u, "file_key": key}):
			frappe.get_doc({"doctype": core.SHARE, "tenant": tenant, "space": space, "path": path, "file_key": key, "is_dir": 0, "user": u,
							"permission": a.share_permission or "view", "shared_by": by}).insert(ignore_permissions=True)
	if share:
		done.append("shared")
	tell = sorted(set(_members(tenant, fr._csv(a.notify))) | set(share)) if (a.notify or share) else []
	if tell:
		try:
			from qtt_platform.push import notify

			notify(tell, title=_("New file: {0}").format(path.rsplit("/", 1)[-1]), body=_("{0} — by the rule “{1}”").format(path, a.title),
				   data={"kind": "files", "tenant": tenant, "space": space, "path": path.rsplit("/", 1)[0] if "/" in path else ""})
		except Exception:
			pass
		done.append("told " + str(len(tell)))
	core.log(tenant, key, space, path, "auto", by, detail=f"{a.title}: {'; '.join(done)}")
	return key, path
