"""
The page someone outside the app opens from an Office Pulse Files share link (api/files_links.page) — in the QTT OS
brand (the launcher icon's navy and electric blue). Steps: the key (when it was sent separately) → password → email
code → waiting for approval → the file (shown, or in the viewer), the folder, or the upload box (File Drop).
"""

import json

_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Shared with you · QTT OS</title><link rel="icon" href="https://queentouchtech.in/logo.png">
<style>
:root{--night:#05080f;--panel:#0f1828;--line:rgba(238,242,248,.12);--ink:#eef2f8;--muted:#a3afc4;--beam:#5ca8ff;--blue:#2f7bff;--blue2:#1a55f0;--bad:#ff8a8a}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(1200px 600px at 80% -10%,rgba(69,156,255,.18),transparent 60%),var(--night);
color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.top{display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line)}
.top img{width:30px;height:30px;border-radius:8px}.top b{font-weight:800;letter-spacing:-.01em}.top b span{color:var(--beam)}
main{max-width:860px;margin:0 auto;padding:28px 16px 60px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:24px}
h1{font-size:24px;margin:0 0 6px;letter-spacing:-.01em;word-break:break-word}.muted{color:var(--muted)}.small{font-size:13px}
label{display:block;font-weight:600;margin:16px 0 6px}
input,textarea{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:#0a1120;color:var(--ink);font:inherit}
input:focus,textarea:focus{outline:2px solid var(--beam);outline-offset:1px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;margin-top:16px;padding:12px 22px;border:0;border-radius:999px;cursor:pointer;
background:linear-gradient(160deg,var(--blue),var(--blue2));color:#fff;font:600 15px system-ui,sans-serif;text-decoration:none}
.btn.ghost{background:transparent;box-shadow:inset 0 0 0 1.5px var(--line);color:var(--ink)}.btn[disabled]{opacity:.6;cursor:default}
.err{color:var(--bad);margin-top:10px}.ok{color:#7ee2a8}
.list{margin-top:18px;border-top:1px solid var(--line)}.row{display:flex;align-items:center;gap:12px;padding:12px 4px;border-bottom:1px solid var(--line);cursor:pointer}
.row:hover{background:rgba(92,168,255,.06)}.ico{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:rgba(92,168,255,.12);color:var(--beam);flex:none;font-size:15px}
.row .n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.crumbs{margin-top:8px;font-size:14px}.crumbs a{color:var(--beam);cursor:pointer;text-decoration:none}
.view{margin-top:18px;border-radius:14px;overflow:hidden;background:#000;border:1px solid var(--line)}.view img,.view video{display:block;max-width:100%;margin:0 auto;max-height:75vh}
.view iframe{display:block;width:100%;height:78vh;border:0;background:#fff}
.drop{margin-top:18px;border:2px dashed rgba(92,168,255,.45);border-radius:16px;padding:34px 16px;text-align:center;cursor:pointer}
.drop.on{background:rgba(92,168,255,.08)}.note{margin-top:14px;padding:10px 14px;border-radius:12px;background:rgba(92,168,255,.08);font-size:14px;color:var(--muted)}
footer{text-align:center;color:var(--muted);font-size:13px;margin-top:28px}footer a{color:var(--beam)}
</style></head><body>
<div class="top"><img src="https://queentouchtech.in/logo.png" alt=""><b>QTT <span>OS</span></b><span class="muted small" id="biz"></span></div>
<main><div class="card" id="app"><p class="muted">Opening…</p></div>
<footer>Shared with QTT OS · <a href="https://queentouchtech.in" rel="noopener">queentouchtech.in</a></footer></main>
<script>
const START = __START__;
const API = "/api/method/qtt_platform.api.";
const S = {k: START.k || "", id: START.id || "", key: "", password: "", email: "", token: "", name: "", note: "", ticket: "", info: null, path: ""};
const $ = (h) => { document.getElementById("app").innerHTML = h; };
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function call(method, data, get) {
  const body = new URLSearchParams(data || {});
  const r = await fetch(API + method + (get ? "?" + body : ""), get ? {} : {method: "POST", body, headers: {"Accept": "application/json"}});
  if (r.status === 429) throw new Error("Too many tries — wait a few minutes and try again.");
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((j._server_messages && JSON.parse(JSON.parse(j._server_messages)[0]).message) || "Something went wrong. Try again.");
  return j.message;
}
const ENDED = {gone: "This link doesn't work any more.", revoked: "This link was stopped by the person who shared it.", expired: "This link has ended.",
  used_up: "This link has been used as many times as it allows.", not_allowed: "This link isn't for your email address.", declined: "Your request to open this was declined.",
  bad_key: "That key isn't right. Check it and try again.", no: "This link can't do that."};
function ended(st) { $(`<h1>${esc(ENDED[st] || ENDED.gone)}</h1><p class="muted">Ask the person who shared it to send you a new link.</p>`); }
async function open_() {
  let r;
  try { r = await call("files_links.open", {k: S.k, id: S.id, key: S.key, password: S.password, email: S.email, token: S.token, name: S.name, note: S.note}); }
  catch (e) { return $(`<h1>Couldn't open the link</h1><p class="err">${esc(e.message)}</p><button class="btn" onclick="open_()">Try again</button>`); }
  if (r.state) return ended(r.state);
  if (r.need === "key") return form("Enter the key", "The person who shared this sent you a key separately.", `<label>Key</label><input id="f" autocomplete="off" autofocus>`,
      () => { S.key = val("f"); open_(); }, r.wrong);
  if (r.need === "password") return form("This link has a password", "", `<label>Password</label><input id="f" type="password" autofocus>`,
      () => { S.password = val("f"); open_(); }, r.wrong && "That password isn't right.");
  if (r.need === "email") return emailStep(r);
  if (r.need === "approval") return $(`<h1>Waiting for approval</h1><p class="muted">${r.sent ? "We asked the person who shared this." : "Your request is waiting."}
      You'll get an email when they decide — then open the link again.</p>`);
  S.ticket = r.ticket; S.info = r.info; document.getElementById("biz").textContent = r.info.business ? "· " + r.info.business : "";
  show();
}
const val = (id) => document.getElementById(id).value.trim();
function form(title, sub, fields, go, err) {
  $(`<h1>${esc(title)}</h1>${sub ? `<p class="muted">${esc(sub)}</p>` : ""}${fields}${err ? `<p class="err">${esc(err)}</p>` : ""}<button class="btn" id="go">Continue</button>`);
  document.getElementById("go").onclick = go;
  document.querySelectorAll("input").forEach(i => i.onkeydown = (e) => { if (e.key === "Enter") go(); });
}
function emailStep(r, err) {
  form(r.approval ? "Ask to open this" : "Confirm your email", r.approval ? "The person who shared it will approve or decline." : "This link is only for some email addresses.",
    `<label>Your email</label><input id="em" type="email" value="${esc(S.email)}" autofocus>` +
    (r.approval ? `<label>Your name</label><input id="nm" value="${esc(S.name)}"><label>Note (optional)</label><textarea id="nt" rows="2">${esc(S.note)}</textarea>` : ""),
    async () => {
      S.email = val("em").toLowerCase(); if (r.approval) { S.name = val("nm"); S.note = val("nt"); }
      try { const s = await call("verify.send_code", {channel: "email", target: S.email, purpose: "file_link"});
        if (!s.success) return emailStep(r, s.error && s.error.message); codeStep(r); } catch (e) { emailStep(r, e.message); }
    }, err);
}
function codeStep(r, err) {
  form("Enter the code", `We sent a 6-digit code to ${S.email}.`, `<label>Code</label><input id="cd" inputmode="numeric" maxlength="6" autofocus>`, async () => {
    try { const v = await call("verify.verify_code", {channel: "email", target: S.email, code: val("cd"), purpose: "file_link"});
      if (!v.success) return codeStep(r, v.error && v.error.message); S.token = v.data.token; open_(); } catch (e) { codeStep(r, e.message); }
  }, err);
}
const ICONS = {folder: "📁", image: "🖼", video: "🎬", audio: "🎵", word: "📄", cell: "📊", slide: "📽", pdf: "📕", archive: "🗜", file: "📄"};
function head() {
  const i = S.info;
  return `<h1>${esc(i.label || i.title)}</h1><p class="muted small">${i.is_dir ? "Folder" : esc(i.size_text || "")}${i.expires_at ? " · until " + esc(i.expires_at) : ""}</p>` +
    (i.mode === "preview" ? `<div class="note">Preview only — downloading is turned off for this link. (Nothing can stop a screenshot.)</div>` : "");
}
async function show() {
  const i = S.info;
  if (i.mode === "upload") return dropBox();
  if (!i.is_dir) return fileView("", i.title, i.type, i.office);
  let r; try { r = await call("files_links.items", {ticket: S.ticket, path: S.path}, true); } catch (e) { return $(`<p class="err">${esc(e.message)}</p>`); }
  if (r.state) return ended(r.state);
  const parts = S.path ? S.path.split("/") : [];
  const crumbs = `<div class="crumbs"><a onclick="go('')">${esc(i.title)}</a>${parts.map((p, n) => ` / <a onclick="go('${esc(parts.slice(0, n + 1).join("/"))}')">${esc(p)}</a>`).join("")}</div>`;
  $(head() + crumbs + `<div class="list">${r.items.length ? r.items.map(it => `<div class="row" data-p="${esc(it.path)}" data-d="${it.is_dir ? 1 : 0}" data-t="${esc(it.type)}" data-o="${it.office ? 1 : 0}" data-n="${esc(it.name)}">
    <div class="ico">${ICONS[it.type] || "📄"}</div><div class="n">${esc(it.name)}</div><div class="muted small">${esc(it.size_text)}</div></div>`).join("") :
    `<p class="muted">This folder is empty.</p>`}</div>`);
  document.querySelectorAll(".row").forEach(el => el.onclick = () => el.dataset.d === "1" ? go(el.dataset.p) : fileView(el.dataset.p, el.dataset.n, el.dataset.t, el.dataset.o === "1"));
}
function go(p) { S.path = p; show(); }
async function fileView(path, name, type, office) {
  const i = S.info, q = new URLSearchParams({ticket: S.ticket, path});
  const back = i.is_dir ? `<button class="btn ghost" onclick="show()">← Back</button> ` : "";
  const dl = i.can_download ? `<a class="btn" href="${API}files_links.get?${q}&dl=1">Download</a>` : "";
  let body = "";
  if (office) {
    $(head() + `<p class="muted">Opening ${esc(name)}…</p>`);
    try { const v = await call("files_links.view", {ticket: S.ticket, path}); if (v.state) return ended(v.state); body = `<div class="view"><iframe src="${esc(v.url)}" allowfullscreen></iframe></div>`; }
    catch (e) { body = `<p class="err">${esc(e.message)}</p>`; }
  } else if (type === "image") body = `<div class="view"><img src="${API}files_links.get?${q}" alt="${esc(name)}"></div>`;
  else if (type === "video" || type === "audio") body = `<div class="view"><video controls ${i.can_download ? "" : 'controlslist="nodownload" oncontextmenu="return false"'} src="${API}files_links.get?${q}"></video></div>`;
  else body = `<p class="muted">${i.can_download ? "This kind of file can't be shown here — download it." : "This kind of file can't be shown here."}</p>`;
  $(head() + `<p><b>${esc(name)}</b></p>` + body + `<div>${back}${dl}</div>`);
}
function dropBox() {
  $(head() + `<p class="muted">Upload files for ${esc(S.info.business || "them")} — you can't see what's already there.</p>
    <div class="drop" id="dz"><b>Choose files</b> or drop them here<br><span class="muted small">Up to 100 MB each</span><input id="fi" type="file" multiple hidden></div><div id="done" class="list"></div>`);
  const dz = document.getElementById("dz"), fi = document.getElementById("fi");
  dz.onclick = () => fi.click(); fi.onchange = () => send(fi.files);
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("on"); }; dz.ondragleave = () => dz.classList.remove("on");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("on"); send(e.dataTransfer.files); };
}
async function send(files) {
  const done = document.getElementById("done");
  for (const f of files) {
    const row = document.createElement("div"); row.className = "row"; row.innerHTML = `<div class="ico">⬆</div><div class="n">${esc(f.name)}</div><div class="muted small">Uploading…</div>`;
    done.prepend(row);
    const fd = new FormData(); fd.append("ticket", S.ticket); fd.append("file", f);
    try { const r = await fetch(API + "files_links.drop", {method: "POST", body: fd}); const j = (await r.json()).message || {};
      row.lastChild.textContent = j.state === "ok" ? "Sent ✓" : ({too_big: "Too big (100 MB at most)", full: "Their space is full", gone: "This link has ended"}[j.state] || "Couldn't send");
      row.lastChild.className = j.state === "ok" ? "ok small" : "err small";
    } catch (e) { row.lastChild.textContent = "Couldn't send"; row.lastChild.className = "err small"; }
  }
}
open_();
</script></body></html>"""


def html(*, k: str = "", id: str = "") -> str:
	start = json.dumps({"k": str(k or "")[:100], "id": str(id or "")[:40]}).replace("</", "<\\/")
	return _PAGE.replace("__START__", start)
