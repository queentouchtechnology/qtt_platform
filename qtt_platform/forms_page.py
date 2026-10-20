"""
The page someone opens from an Office Pulse Forms link (api/forms.page, app.queentouchtech.in/f/<key>) — in the QTT
OS brand (the launcher icon's navy and electric blue). The questions come from api/forms.public_form; the answer goes
to api/forms.submit, which checks it again.
"""

import json

_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Form · QTT OS</title><link rel="icon" href="https://queentouchtech.in/logo.png">
<style>
:root{--night:#05080f;--panel:#0f1828;--line:rgba(238,242,248,.12);--ink:#eef2f8;--muted:#a3afc4;--beam:#5ca8ff;--blue:#2f7bff;--blue2:#1a55f0;--bad:#ff8a8a}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(1200px 600px at 80% -10%,rgba(69,156,255,.18),transparent 60%),var(--night);
color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.top{display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line)}
.top img{width:30px;height:30px;border-radius:8px}.top b{font-weight:800}.top b span{color:var(--beam)}
main{max-width:720px;margin:0 auto;padding:28px 16px 60px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:24px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.01em;word-break:break-word}.muted{color:var(--muted)}.small{font-size:13px}
.q{margin-top:22px}.q>label{display:block;font-weight:600;margin-bottom:6px}.q .req{color:var(--beam)}.help{font-size:13px;color:var(--muted);margin:-2px 0 8px}
input[type=text],input[type=email],input[type=tel],input[type=number],input[type=date],textarea,select{width:100%;padding:12px 14px;border-radius:12px;
border:1px solid var(--line);background:#0a1120;color:var(--ink);font:inherit}
textarea{min-height:110px;resize:vertical}input:focus,textarea:focus,select:focus{outline:2px solid var(--beam);outline-offset:1px}
.opt{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;margin-top:8px;cursor:pointer}
.opt input{width:18px;height:18px;accent-color:var(--blue)}.stars{display:flex;gap:8px}.stars button{flex:1;padding:12px 0;border-radius:12px;border:1px solid var(--line);
background:#0a1120;color:var(--ink);font:600 16px system-ui;cursor:pointer}.stars button.on{background:linear-gradient(160deg,var(--blue),var(--blue2));border-color:transparent}
.err{color:var(--bad);font-size:14px;margin-top:6px}.trap{position:absolute;left:-5000px}
.btn{display:inline-flex;align-items:center;justify-content:center;margin-top:26px;padding:13px 26px;border:0;border-radius:999px;cursor:pointer;
background:linear-gradient(160deg,var(--blue),var(--blue2));color:#fff;font:600 16px system-ui,sans-serif;width:100%}.btn[disabled]{opacity:.6}
footer{text-align:center;color:var(--muted);font-size:13px;margin-top:28px}footer a{color:var(--beam)}
</style></head><body>
<div class="top"><img src="https://queentouchtech.in/logo.png" alt=""><b>QTT <span>OS</span></b><span class="muted small" id="biz"></span></div>
<main><div class="card" id="app"><p class="muted">Opening…</p></div>
<footer>Made with QTT OS · <a href="https://queentouchtech.in" rel="noopener">queentouchtech.in</a></footer></main>
<script>
const K = __K__;
const API = "/api/method/qtt_platform.api.forms.";
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const $ = (h) => { document.getElementById("app").innerHTML = h; };
let F = null; const A = {};
function field(q) {
  const id = "q_" + q.id, req = q.required ? ' <span class="req">*</span>' : "";
  let inner = "";
  if (q.type === "long") inner = `<textarea id="${id}"></textarea>`;
  else if (q.type === "choice" || q.type === "checkboxes") {
    const t = q.type === "choice" ? "radio" : "checkbox";
    inner = q.options.map((o, i) => `<label class="opt"><input type="${t}" name="${id}" value="${esc(o)}"> ${esc(o)}</label>`).join("");
  } else if (q.type === "dropdown") inner = `<select id="${id}"><option value="">Choose…</option>${q.options.map(o => `<option>${esc(o)}</option>`).join("")}</select>`;
  else if (q.type === "yesno") inner = ["Yes", "No"].map(o => `<label class="opt"><input type="radio" name="${id}" value="${o.toLowerCase()}"> ${o}</label>`).join("");
  else if (q.type === "rating") inner = `<div class="stars" id="${id}">${[1,2,3,4,5].map(n => `<button type="button" data-n="${n}">${n} ★</button>`).join("")}</div>`;
  else {
    const t = {email: "email", phone: "tel", number: "number", date: "date"}[q.type] || "text";
    inner = `<input type="${t}" id="${id}" ${q.type === "number" ? 'step="any" inputmode="decimal"' : ""}>`;
  }
  return `<div class="q"><label for="${id}">${esc(q.label)}${req}</label>${q.help ? `<div class="help">${esc(q.help)}</div>` : ""}${inner}<div class="err" id="e_${q.id}"></div></div>`;
}
function value(q) {
  const id = "q_" + q.id;
  if (q.type === "choice" || q.type === "yesno") { const c = document.querySelector(`input[name="${id}"]:checked`); return c ? c.value : ""; }
  if (q.type === "checkboxes") return [...document.querySelectorAll(`input[name="${id}"]:checked`)].map(c => c.value);
  if (q.type === "rating") return A[q.id] || "";
  return document.getElementById(id).value;
}
function render() {
  document.getElementById("biz").textContent = F.business ? "· " + F.business : "";
  document.title = F.title + " · " + (F.business || "QTT OS");
  if (F.closed) { $(`<h1>${esc(F.title || "")}</h1><p class="muted">${esc(F.message)}</p>`); return; }
  $(`<h1>${esc(F.title)}</h1>${F.description ? `<p class="muted">${esc(F.description).replace(/\n/g, "<br>")}</p>` : ""}
    <form id="f" novalidate>${F.questions.map(field).join("")}
    <input class="trap" name="website" id="website" tabindex="-1" autocomplete="off" aria-hidden="true">
    <button class="btn" id="send">Send</button><div class="err" id="e_all"></div></form>`);
  document.querySelectorAll(".stars").forEach(s => s.addEventListener("click", ev => {
    const b = ev.target.closest("button"); if (!b) return;
    A[s.id.slice(2)] = +b.dataset.n; s.querySelectorAll("button").forEach(x => x.classList.toggle("on", +x.dataset.n <= +b.dataset.n));
  }));
  document.getElementById("f").addEventListener("submit", send);
}
async function send(ev) {
  ev.preventDefault();
  const answers = {}; for (const q of F.questions) answers[q.id] = value(q);
  document.querySelectorAll(".err").forEach(e => e.textContent = "");
  const missing = F.questions.filter(q => q.required && (answers[q.id] === "" || (Array.isArray(answers[q.id]) && !answers[q.id].length)));
  if (missing.length) { missing.forEach(q => document.getElementById("e_" + q.id).textContent = "Please answer this."); document.getElementById("q_" + missing[0].id)?.scrollIntoView({block: "center"}); return; }
  const b = document.getElementById("send"); b.disabled = true; b.textContent = "Sending…";
  try {
    const body = new URLSearchParams({k: K, answers: JSON.stringify(answers), website: document.getElementById("website").value});
    const r = await fetch(API + "submit", {method: "POST", body, headers: {Accept: "application/json"}});
    if (r.status === 429) throw new Error("Too many tries — wait a few minutes and try again.");
    const m = (await r.json()).message || {};
    if (m.errors) { for (const [k, v] of Object.entries(m.errors)) { const e = document.getElementById("e_" + k); if (e) e.textContent = v; } throw new Error("Check the answers marked."); }
    if (m.closed) { $(`<h1>${esc(F.title)}</h1><p class="muted">${esc(m.message)}</p>`); return; }
    $(`<h1>✓ ${esc(m.thanks)}</h1><p class="muted">${esc(F.business || "")}</p>`);
  } catch (err) { document.getElementById("e_all").textContent = err.message || "Something went wrong. Try again."; b.disabled = false; b.textContent = "Send"; }
}
(async () => {
  try { const r = await fetch(API + "public_form?k=" + encodeURIComponent(K)); F = (await r.json()).message; render(); }
  catch (err) { $(`<p class="muted">This form couldn't be opened. Check your internet and try again.</p>`); }
})();
</script></body></html>"""


def html(k: str) -> str:
	return _PAGE.replace("__K__", json.dumps(str(k or "")[:60]).replace("</", "<\\/"))
