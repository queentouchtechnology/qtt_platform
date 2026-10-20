"""
Office Pulse Whiteboards (PROJ-0016 D3): drawing boards (Excalidraw, MIT) — for planning, layouts, mind maps — that
several people draw on at once. The page is opened with a signed link (the app's web view has no Frappe login, like
the documents editor); drawings from everyone are put together element by element (planning_rules.merge_elements).

  whiteboards / save_whiteboard / delete_whiteboard / open_whiteboard   the list; make, rename, share; a link to draw
  page / scene / push / picture                                        the drawing page and its calls (signed link)

Team whiteboards: everyone in the business draws. Private: who made it (others in the business can't open it).
"""

import base64
import json

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime
from werkzeug.wrappers import Response

from qtt_platform import planning_rules as pr

WB = "QTT Whiteboard"
TTL = 12 * 3600


def _ctx():
	from qtt_platform.api.workplace import _ctx as wctx

	return wctx()


def _sees(ctx, w) -> bool:
	return w.tenant == ctx.tenant and (w.visibility == "team" or w.owner_user == ctx.user)


def _get(ctx, name: str):
	w = frappe.get_doc(WB, name) if name and frappe.db.exists(WB, name) else None
	if not w or not _sees(ctx, w):
		frappe.throw(_("That whiteboard isn't here any more."), frappe.DoesNotExistError)
	return w


def _out(ctx, w, names) -> dict:
	try:
		count = sum(1 for e in json.loads(w.elements or "[]") if not e.get("isDeleted"))
	except Exception:
		count = 0
	return {"name": w.name, "title": w.title, "visibility": w.visibility, "by": names.get(w.owner_user, w.owner_user),
			"changed_by": names.get(w.updated_by or w.owner_user, w.updated_by), "modified": str(w.modified), "shapes": count,
			"mine": w.owner_user == ctx.user, "can_delete": w.owner_user == ctx.user or ctx.admin}


@frappe.whitelist(methods=["GET"])
def whiteboards() -> dict:
	"""The whiteboards this person sees, the newest changed first."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	rows = frappe.get_all(WB, filters={"tenant": ctx.tenant, "archived": 0}, fields=["name"], order_by="modified desc", limit=300, pluck="name")
	names = _names(ctx)
	return {"whiteboards": [_out(ctx, w, names) for w in (frappe.get_doc(WB, n) for n in rows) if _sees(ctx, w)]}


@frappe.whitelist(methods=["POST"])
def save_whiteboard(name: str | None = None, title: str = "", visibility: str = "team") -> dict:
	"""Make a whiteboard, or rename it / change who sees it (who made it, owners and admins)."""
	from qtt_platform.api.team import _names

	ctx = _ctx()
	if name:
		w = _get(ctx, name)
		if w.owner_user != ctx.user and not ctx.admin:
			frappe.throw(_("Only who made this whiteboard can change it."), frappe.PermissionError)
	else:
		w = frappe.get_doc({"doctype": WB, "tenant": ctx.tenant, "owner_user": ctx.user, "elements": "[]"})
	w.title = str(title or "").strip()[:140] or w.title or _("Whiteboard")
	w.visibility = "private" if visibility == "private" else "team"
	w.save(ignore_permissions=True)
	return _out(ctx, w, _names(ctx))


@frappe.whitelist(methods=["POST"])
def delete_whiteboard(name: str) -> dict:
	"""Delete a whiteboard (who made it, owners and admins)."""
	ctx = _ctx()
	w = _get(ctx, name)
	if w.owner_user != ctx.user and not ctx.admin:
		frappe.throw(_("Only who made this whiteboard, or an owner or admin, can delete it."), frappe.PermissionError)
	frappe.delete_doc(WB, w.name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def open_whiteboard(name: str) -> dict:
	"""A link to draw on it (for 12 hours) — in the app's web view on phones, a browser tab elsewhere."""
	from qtt_platform.api import workplace_docs as wd
	from qtt_platform.api.team import _names

	ctx = _ctx()
	w = _get(ctx, name)
	lang = (frappe.db.get_value("User", ctx.user, "language") or "en")[:2]
	t = wd._sign({"wb": w.name, "u": ctx.user, "tn": ctx.tenant, "n": _names(ctx).get(ctx.user, ctx.user), "l": lang}, TTL)
	return {"url": get_url(f"/api/method/qtt_platform.api.whiteboard.page?t={t}"), "title": w.title}


# ---- the drawing page (signed link) ------------------------------------------------------------------------------------
def _claims(t: str):
	from qtt_platform.api import workplace_docs as wd

	t = t or (frappe.request.args.get("t") if frappe.request else "") or ""
	try:
		c = wd._check(t)
	except frappe.PermissionError:
		return None, None
	w = frappe.get_doc(WB, c["wb"]) if frappe.db.exists(WB, c.get("wb")) else None
	# still in the business, and still allowed to see it
	if not w or w.tenant != c.get("tn") or not frappe.db.exists("QTT Tenant Membership", {"user": c["u"], "tenant": w.tenant, "status": "active"}):
		return None, None
	if w.visibility != "team" and w.owner_user != c["u"]:
		return None, None
	return c, w


def _elements(w) -> list:
	try:
		return json.loads(w.elements or "[]")
	except Exception:
		return []


@frappe.whitelist(allow_guest=True, methods=["GET"])
def page(t: str = ""):
	"""The drawing page."""
	c, w = _claims(t)
	if not c:
		return Response("<h3 style='font-family:sans-serif'>This whiteboard link has ended — open it again from the app.</h3>", status=403, mimetype="text/html")
	start = {"t": t or frappe.request.args.get("t"), "title": w.title, "name": c.get("n"), "lang": c.get("l") or "en",
			 "elements": _elements(w), "modified": str(w.modified)}
	html = _PAGE.replace("__TITLE__", frappe.utils.escape_html(w.title)).replace("__START__", json.dumps(start).replace("</", "<\\/"))
	return Response(html, mimetype="text/html", headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def scene(t: str = "", since: str = ""):
	"""The drawing when it changed since `since` (its modified time), else nothing new."""
	c, w = _claims(t)
	if not c:
		frappe.throw(_("This whiteboard link has ended."), frappe.PermissionError)
	if since and since == str(w.modified):
		return {"modified": since, "elements": None}
	return {"modified": str(w.modified), "elements": _elements(w), "by": frappe.db.get_value("User", w.updated_by, "full_name") if w.updated_by else None}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def push(t: str = "", elements: str = "[]"):
	"""Someone's changed elements, put together with everyone else's."""
	c, _w = _claims(t)
	if not c:
		frappe.throw(_("This whiteboard link has ended."), frappe.PermissionError)
	if len(elements) > 15 * 1024 * 1024:
		frappe.throw(_("That's too much to save at once."))
	try:
		incoming = json.loads(elements)
		assert isinstance(incoming, list)
	except Exception:
		frappe.throw(_("That drawing couldn't be read."))
	saved = frappe.db.sql(f"select elements from `tab{WB}` where name = %s for update", c["wb"])[0][0]
	try:
		merged = pr.merge_elements(json.loads(saved or "[]"), [e for e in incoming if isinstance(e, dict)])
	except ValueError as e:
		frappe.throw(_(str(e)))
	frappe.db.set_value(WB, c["wb"], {"elements": json.dumps(merged, separators=(",", ":")), "updated_by": c["u"]})
	frappe.db.commit()
	return {"ok": True, "modified": str(frappe.db.get_value(WB, c["wb"], "modified"))}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def picture(t: str = "", png: str = ""):
	"""The drawing as a picture, saved to the person's own Files (Whiteboards/<title>.png)."""
	from qtt_platform import files_core as core
	from qtt_platform import workplace_rules as rules

	c, w = _claims(t)
	if not c:
		frappe.throw(_("This whiteboard link has ended."), frappe.PermissionError)
	try:
		data = base64.b64decode(png.split(",", 1)[-1], validate=False)
	except Exception:
		data = b""
	if not data.startswith(b"\x89PNG") or len(data) > 20 * 1024 * 1024:
		frappe.throw(_("That picture couldn't be saved."))
	name = rules.clean_name(f"{w.title}.png") or "whiteboard.png"
	path = f"Whiteboards/{name}"
	key = f"{w.tenant}/people/{rules.person_id(c['u'])}/{path}"
	core.save(w.tenant, key, data, c["u"], "image/png")
	core.log(w.tenant, key, "mine", path, "upload", c["u"])
	frappe.db.commit()
	return {"ok": True, "path": path, "at": str(now_datetime())[:16]}


_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><meta name="robots" content="noindex,nofollow">
<title>__TITLE__ · Whiteboard</title><link rel="icon" href="https://queentouchtech.in/logo.png">
<style>html,body,#app{margin:0;height:100%;width:100%;overflow:hidden;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.qtt-bar{display:flex;gap:6px;align-items:center}.qtt-btn{border:0;border-radius:8px;padding:8px 12px;cursor:pointer;font:600 13px system-ui,sans-serif;
background:linear-gradient(160deg,#2f7bff,#1a55f0);color:#fff;white-space:nowrap}.qtt-st{font-size:12px;color:#64748b;white-space:nowrap}
#gone{display:none;position:fixed;inset:0;background:rgba(5,8,15,.85);color:#fff;align-items:center;justify-content:center;font-size:18px;z-index:99;text-align:center;padding:20px}</style>
<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>
<script>window.EXCALIDRAW_ASSET_PATH = "https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/";</script>
<script src="https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.js"></script>
</head><body><div id="app"></div><div id="gone">This whiteboard link has ended — open it again from the app.</div>
<script>
const START = __START__;
const API = "/api/method/qtt_platform.api.whiteboard.";
const {Excalidraw, exportToBlob} = ExcalidrawLib;
const e = React.createElement;
let api = null, known = {}, lastMod = START.modified, timer = null, busy = false, setStatus = () => {};
for (const el of START.elements) known[el.id] = el.version;

async function call(m, data, get) {
  const body = new URLSearchParams({t: START.t, ...(data || {})});
  const r = await fetch(API + m + (get ? "?" + body : ""), get ? {} : {method: "POST", body, headers: {Accept: "application/json"}});
  if (r.status === 403) { document.getElementById("gone").style.display = "flex"; throw new Error("gone"); }
  if (!r.ok) throw new Error("failed");
  return (await r.json()).message;
}
function changed() {
  if (!api) return [];
  return api.getSceneElementsIncludingDeleted().filter(x => known[x.id] !== x.version);
}
async function push() {
  const els = changed();
  if (!els.length || busy) return;
  busy = true; setStatus("Saving…");
  try {
    await call("push", {elements: JSON.stringify(els)});
    for (const x of els) known[x.id] = x.version;
    setStatus("Saved");
  } catch (err) { setStatus("Not saved — check the internet"); }
  busy = false;
}
async function pull() {
  if (!api || busy) return;
  const st = api.getAppState();
  if (st.draggingElement || st.resizingElement || st.editingElement || st.multiElement) return;  // not while someone is drawing
  try {
    const r = await call("scene", {since: lastMod}, true);
    if (!r.elements) return;
    lastMod = r.modified;
    const local = new Map(api.getSceneElementsIncludingDeleted().map(x => [x.id, x]));
    let any = false;
    for (const x of r.elements) {
      const l = local.get(x.id);
      if (!l || x.version > l.version || (x.version === l.version && x.versionNonce > l.versionNonce)) { local.set(x.id, x); any = true; }
      if (!l || known[x.id] === undefined || x.version >= l.version) known[x.id] = x.version;
    }
    if (any) api.updateScene({elements: [...local.values()]});
  } catch (err) {}
}
async function picture() {
  if (!api) return;
  setStatus("Making the picture…");
  try {
    const blob = await exportToBlob({elements: api.getSceneElements(), appState: {...api.getAppState(), exportBackground: true, exportWithDarkMode: false},
      files: api.getFiles(), mimeType: "image/png", exportPadding: 24});
    const data = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(blob); });
    const r = await call("picture", {png: data});
    setStatus("Saved to your Files › " + r.path);
  } catch (err) { setStatus("The picture couldn't be saved"); }
}
function Top() {
  const [s, set] = React.useState("");
  setStatus = set;
  return e("div", {className: "qtt-bar"}, e("span", {className: "qtt-st"}, s), e("button", {className: "qtt-btn", onClick: picture, title: "Save a picture of it to your Files"}, "Save picture"));
}
function App() {
  return e(Excalidraw, {
    excalidrawAPI: a => { api = a; },
    initialData: {elements: START.elements, appState: {viewBackgroundColor: "#ffffff", currentItemFontFamily: 2}, scrollToContent: true},
    onChange: () => { clearTimeout(timer); timer = setTimeout(push, 700); },
    langCode: START.lang === "ta" ? "ta-IN" : START.lang === "hi" ? "hi-IN" : START.lang === "ar" ? "ar-SA" : "en",
    UIOptions: {tools: {image: false}, canvasActions: {loadScene: false, saveToActiveFile: false}},
    name: START.title,
    renderTopRightUI: () => e(Top),
  });
}
ReactDOM.createRoot(document.getElementById("app")).render(e(App));
setInterval(pull, 3000);
window.addEventListener("beforeunload", push);
</script></body></html>"""
