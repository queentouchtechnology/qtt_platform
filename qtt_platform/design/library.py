"""
The template library in the database (PROJ-0011 C): sync() keeps QTT Post Template in step with design/catalog.py
(after every migrate) and, when the catalogue changed, queues make_thumbnails() — the library pictures, one per template
and business group that has its own sample words, made on the renderer and kept as public files.
"""

import json

import frappe

from qtt_platform.design import catalog

DT = "QTT Post Template"


def _lines(v) -> list[str]:
	return [x.strip() for x in str(v or "").splitlines() if x.strip()]


def queue_checks() -> None:
	"""Daily (hooks): the nightly quality check, on the long queue — one at a time."""
	frappe.enqueue("qtt_platform.design.library.check_templates", queue="long", timeout=3600, job_id="qtt_template_checks", deduplicate=True)


def check_templates() -> dict:
	"""Every enabled template drawn in every size with a sample (its first group's words and photos, its own palette and
	fonts); each gets ok, or problem with what was wrong. {ok, problem}."""
	from frappe.utils import now_datetime

	from qtt_platform.design import post, quality, render

	if not render.ready():
		return {}
	done = {"ok": 0, "problem": 0}
	for name in frappe.get_all(DT, filters={"enabled": 1}, pluck="name", order_by="sort asc"):
		doc = frappe.get_doc(DT, name)
		t = row_dict(doc)
		g = t["groups"][0] if t["groups"] and t["groups"][0] != "any" else "any"
		problems = []
		for fmt, (w, h) in quality.SIZES.items():
			try:
				png = post.render(t["layout"], t["variant"], colors=catalog.PALETTES[t["palette"]], fonts=catalog.FONT_SETS[t["fonts"]], look=t["look"],
								  fmt=fmt, content=catalog.sample_for(t["layout"], g), out_width=w,
								  photos=[] if "showcase" in t["post_types"] else post.kit_photos(catalog.sample_kit(t["layout"], g), 5))
				p = quality.picture_problem(png, w, h)
			except Exception as e:
				frappe.clear_messages()
				p = f"didn't draw ({str(e)[:120]})"
			if p:
				problems.append(f"{fmt}: {p}")
		status = "problem" if problems else "ok"
		done[status] += 1
		doc.db_set({"check_status": status, "check_note": "\n".join(problems)[:1000], "checked_on": now_datetime()}, update_modified=False)
		frappe.db.commit()
	return done


def row_dict(doc) -> dict:
	"""A template row as the catalogue's plain data."""
	return {"key": doc.key, "title": doc.title, "layout": doc.layout, "variant": json.loads(doc.variant or "{}"), "look": doc.look,
			"post_types": _lines(doc.post_types), "groups": _lines(doc.groups), "palette": doc.palette, "fonts": doc.fonts,
			"thumbs": json.loads(doc.thumbs or "{}"), "enabled": int(doc.enabled or 0)}


def sync() -> None:
	"""after_migrate: QTT's templates in, changed ones updated (an admin's on / off is kept), removed ones switched off."""
	if not frappe.db.table_exists(DT):
		return
	keys = set()
	for t in catalog.templates():
		keys.add(t["key"])
		values = {"title": t["title"], "layout": t["layout"], "variant": json.dumps(t["variant"], sort_keys=True), "look": t["look"],
				  "post_types": "\n".join(t["post_types"]), "groups": "\n".join(t["groups"]), "palette": t["palette"], "fonts": t["fonts"],
				  "sort": t["sort"], "source": "QTT"}
		if frappe.db.exists(DT, t["key"]):
			doc = frappe.get_doc(DT, t["key"])
			if any(str(doc.get(k) or "") != str(v) for k, v in values.items()):
				doc.update(values)
				doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": DT, "key": t["key"], "enabled": 1, **values}).insert(ignore_permissions=True)
	for name in frappe.get_all(DT, filters={"source": "QTT", "name": ["not in", list(keys) or [""]]}, pluck="name"):
		frappe.db.set_value(DT, name, "enabled", 0)
	frappe.db.commit()
	if frappe.db.count(DT, {"thumbs_hash": ["!=", catalog.catalog_hash()], "enabled": 1}):
		frappe.enqueue("qtt_platform.design.library.make_thumbnails", queue="long", timeout=3600, job_id="qtt_post_thumbnails",
					   deduplicate=True)


def _groups_with_samples(t: dict) -> list[str]:
	"""The groups this template gets its own picture for: its first group, and any group with its own sample words."""
	own = [g for g in (catalog.SAMPLES.get(t["layout"]) or {}) if g != "any" and (g in t["groups"] or "any" in t["groups"])]
	first = t["groups"][0] if t["groups"] and t["groups"][0] != "any" else "any"
	return list(dict.fromkeys([first, *own]))


def make_thumbnails(force: bool = False) -> int:
	"""The library pictures (540 px) for templates whose catalogue changed. Returns how many were made."""
	from qtt_platform.design import post, render

	if not render.ready():
		return 0
	h = catalog.catalog_hash()
	by_key = {t["key"]: t for t in catalog.templates()}
	made = 0
	for name in frappe.get_all(DT, filters={"enabled": 1}, pluck="name"):
		doc = frappe.get_doc(DT, name)
		if doc.thumbs_hash == h and not force:
			continue
		t = by_key.get(name) or {**row_dict(doc)}
		thumbs = {}
		for g in _groups_with_samples(t):
			try:
				data = post.thumbnail(t, g)
			except Exception:
				frappe.log_error(title=f"Post template picture failed: {name} / {g}")
				continue
			fname = f"post-template-{name}-{g}-{h[:8]}.png"
			old = frappe.db.get_value("File", {"file_name": fname, "attached_to_doctype": DT, "attached_to_name": name}, "file_url")
			thumbs[g] = old or frappe.get_doc({"doctype": "File", "file_name": fname, "content": data, "is_private": 0,
											   "attached_to_doctype": DT, "attached_to_name": name}).insert(ignore_permissions=True).file_url
			made += 1
		doc.db_set({"thumbs": json.dumps(thumbs), "thumbs_hash": h if thumbs else ""}, update_modified=False)
		frappe.db.commit()
	return made


def picture(row: dict, group: str | None) -> str | None:
	"""The best library picture for a group: its own, else the template's first."""
	thumbs = row.get("thumbs") or {}
	return thumbs.get(group or "") or thumbs.get(row["groups"][0] if row.get("groups") else "") or next(iter(thumbs.values()), None)


# ---- occasions (the content library's calendar) ------------------------------------------------------------------------
OCCASION = "QTT Occasion"


def sync_occasions() -> None:
	"""after_migrate: every occasion in design/content.py in QTT Occasion; fixed days get this year's (or next year's)
	date; a moving festival's date is left for Desk and never overwritten."""
	from frappe.utils import getdate, today

	from qtt_platform.design import content

	if not frappe.db.table_exists(OCCASION):
		return
	now = getdate(today())
	for key, (en, ta, fixed) in content.OCCASIONS.items():
		date = None
		if fixed:
			m, d = (int(x) for x in fixed.split("-"))
			date = getdate(f"{now.year}-{m:02d}-{d:02d}")
			if date < now:
				date = getdate(f"{now.year + 1}-{m:02d}-{d:02d}")
		if frappe.db.exists(OCCASION, key):
			if fixed and str(frappe.db.get_value(OCCASION, key, "date") or "") != str(date):
				frappe.db.set_value(OCCASION, key, "date", date)
		else:
			frappe.get_doc({"doctype": OCCASION, "key": key, "label": en, "label_ta": ta, "fixed": fixed or "", "date": date,
							"enabled": 1}).insert(ignore_permissions=True)
	frappe.db.commit()


def upcoming(days: int = 21, tenant: str | None = None) -> list[dict]:
	"""Occasions in the next `days` days (soonest first): [{key, label, date}] — for a business, only the festivals that
	suit it (a church, temple or mosque: its own faith's and the ones for everyone)."""
	from frappe.utils import add_days, today

	rows = frappe.get_all(OCCASION, filters={"enabled": 1, "date": ["between", [today(), add_days(today(), days)]]},
						  fields=["key", "label", "label_ta", "date"], order_by="date asc")
	return [r for r in rows if suits(r.key, tenant)] if tenant else rows


def suits(key: str, tenant: str) -> bool:
	"""Is this festival one to offer this business? (design/content.py occasion_suits, from its Business › Knowledge)"""
	from qtt_platform.design import content

	k = frappe.db.get_value("QTT Business Knowledge", {"tenant": tenant}, ["business_type", "faith"], as_dict=True) or {}
	return content.occasion_suits(key, business_type=k.get("business_type"), faith=k.get("faith"))
