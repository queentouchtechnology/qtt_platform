/* QTT OS App Map viewer — draws app_map.json (tool/app_map.py) as a tree that grows to the right, like an
   infographic: tap a box to open its branch, the panel shows what it is, where it lives and who uses it.
   Used by /app-map (staff) and by an Office Pulse share link to "QTT App Map.qttmap" (files_page.py).
   QttAppMap.render(element, data). No libraries; everything escaped. */
(function () {
  "use strict";
  const COL = 236, W = 204, H = 46, GAP = 8;
  const STATE = {
    ok: ["#16A34A", "Used"], unused: ["#94A3B8", "Not used by anything"], undescribed: ["#F59E0B", "Not described yet"],
    private: ["#7C3AED", "Private"], generated: ["#0891B2", "Generated"], reserved: ["#2563EB", "Reserved"], active: ["#16A34A", "Active"],
  };
  const ICON = {root: "◉", product: "▣", group: "▤", area: "◫", endpoint: "⇄", screen: "▭", doctype: "▦", job: "⏱", folder: "▸"};
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  const CSS = `
.qam{--bg:#F4F6FA;--card:#fff;--ink:#0F172A;--muted:#64748B;--line:#CBD5E1;--navy:#0D1524;--blue:#1A55F0;
  font:14px/1.45 "Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);display:flex;flex-direction:column;height:100%;min-height:100vh}
@media (prefers-color-scheme:dark){.qam{--bg:#070B12;--card:#101826;--ink:#E7EAF0;--muted:#94A3B8;--line:#334155}}
.qam *{box-sizing:border-box}
.qam-top{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:12px 16px;background:var(--navy);color:#fff;border-bottom:3px solid var(--blue)}
.qam-top h1{font-size:18px;margin:0 8px 0 0;font-weight:700}
.qam-chip{background:rgba(255,255,255,.1);border-radius:999px;padding:3px 10px;font-size:12px;white-space:nowrap}
.qam-search{flex:1;min-width:180px;max-width:420px;border:0;border-radius:10px;padding:9px 12px;font:inherit}
.qam-btn{border:1px solid rgba(255,255,255,.3);background:transparent;color:#fff;border-radius:10px;padding:7px 11px;cursor:pointer;font:inherit}
.qam-legend{display:flex;flex-wrap:wrap;gap:12px;padding:8px 16px;font-size:12px;color:var(--muted);border-bottom:1px solid var(--line)}
.qam-legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.qam-body{flex:1;display:flex;min-height:0;position:relative}
.qam-canvas{flex:1;overflow:auto;position:relative}
.qam-stage{position:relative;transform-origin:0 0;margin:24px}
.qam-node{position:absolute;width:${W}px;height:${H - GAP}px;background:var(--card);border:1.5px solid var(--c,#94A3B8);border-left-width:5px;border-radius:10px;
  display:flex;align-items:center;gap:7px;padding:0 8px;cursor:pointer;box-shadow:0 1px 2px rgba(15,23,42,.06);transition:box-shadow .15s}
.qam-node:hover{box-shadow:0 4px 14px rgba(15,23,42,.14)}
.qam-node.sel{outline:3px solid var(--blue);outline-offset:1px}
.qam-node.hit{background:#FEF9C3;color:#0F172A}
.qam-node .ic{color:var(--c);font-size:15px;width:16px;text-align:center}
.qam-node .t{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:13px;font-weight:600}
.qam-node .d{width:8px;height:8px;border-radius:50%;flex:none}
.qam-node .n{font-size:11px;color:var(--muted);flex:none}
.qam-node.root,.qam-node.product{color:#fff;background:var(--c);border-color:var(--c)}
.qam-node.root .ic,.qam-node.product .ic,.qam-node.root .n,.qam-node.product .n{color:#fff}
.qam svg{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.qam-panel{width:360px;max-width:100%;border-left:1px solid var(--line);background:var(--card);overflow:auto;padding:18px}
.qam-panel h2{margin:0 0 4px;font-size:17px}.qam-panel .k{color:var(--muted);font-size:12px;margin-top:12px;text-transform:uppercase;letter-spacing:.3px}
.qam-panel .v{white-space:pre-wrap;word-break:break-word;font-size:13.5px}
.qam-panel .crumb{color:var(--muted);font-size:12px}.qam-panel .pill{display:inline-block;border-radius:999px;padding:2px 9px;font-size:12px;color:#fff;margin-top:6px}
.qam-results{position:absolute;z-index:5;left:16px;top:8px;max-width:520px;max-height:60vh;overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.18)}
.qam-results div{padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--line);font-size:13px}.qam-results div:hover{background:var(--bg)}
.qam-results small{color:var(--muted)}
@media (max-width:760px){.qam-panel{position:absolute;right:0;top:0;bottom:0;width:92%;box-shadow:-10px 0 30px rgba(0,0,0,.2);display:none}.qam-panel.open{display:block}}
@media (max-width:760px){.qam-chip{display:none}.qam-top h1{font-size:16px}.qam-legend span:last-child{display:none}}
.qam-x{float:right;border:0;background:none;font-size:20px;cursor:pointer;color:var(--muted)}`;

  function render(el, data) {
    if (!document.getElementById("qam-css")) {
      const s = document.createElement("style"); s.id = "qam-css"; s.textContent = CSS; document.head.appendChild(s);
    }
    const root = data.tree, open = new Set(["root"]); // first: QTT OS and its products — tap one to open it
    const parent = new Map(), all = [];
    (function index(n, p, color) {
      n._c = n.color || color; parent.set(n, p); all.push(n);
      (n.children || []).forEach((c) => index(c, n, n.kind === "root" ? null : n._c));
    })(root, null, "#1A55F0");
    let selected = null, hits = new Set(), zoom = 1;

    const t = data.totals || {};
    el.innerHTML = `<div class="qam">
  <div class="qam-top"><h1>QTT OS · App Map</h1>
    ${Object.entries(t).map(([k, v]) => `<span class="qam-chip">${esc(v)} ${esc(k)}</span>`).join("")}
    <input class="qam-search" placeholder="Search a screen, endpoint, table, folder…" aria-label="Search">
    <button class="qam-btn" data-a="out" title="Smaller">−</button><button class="qam-btn" data-a="in" title="Bigger">+</button>
    <button class="qam-btn" data-a="fold">Fold all</button></div>
  <div class="qam-legend">${Object.entries(STATE).filter(([k]) => k !== "active").map(([, [c, l]]) => `<span><i style="background:${c}"></i>${esc(l)}</span>`).join("")}
    <span>Tap a box to open it · tap again to fold · details on the right</span></div>
  <div class="qam-body"><div class="qam-canvas"><div class="qam-stage"><svg></svg></div></div><div class="qam-panel"></div></div></div>`;
    const stage = el.querySelector(".qam-stage"), svg = el.querySelector("svg"), panel = el.querySelector(".qam-panel"),
      canvas = el.querySelector(".qam-canvas"), search = el.querySelector(".qam-search");

    function layout() {
      let row = 0; const placed = [];
      (function place(n, depth) {
        const kids = open.has(n.id) ? n.children || [] : [];
        if (!kids.length) { n._y = row++ * H; } else {
          kids.forEach((c) => place(c, depth + 1));
          n._y = (kids[0]._y + kids[kids.length - 1]._y) / 2;
        }
        n._x = depth * COL; placed.push(n);
      })(root, 0);
      return {placed, rows: row};
    }

    function draw() {
      const {placed, rows} = layout();
      const width = Math.max(...placed.map((n) => n._x)) + W + 20, height = rows * H + 10;
      stage.style.width = width + "px"; stage.style.height = height + "px"; stage.style.transform = `scale(${zoom})`;
      svg.setAttribute("width", width); svg.setAttribute("height", height);
      let paths = "";
      placed.forEach((n) => (open.has(n.id) ? n.children || [] : []).forEach((c) => {
        const x1 = n._x + W, y1 = n._y + (H - GAP) / 2, x2 = c._x, y2 = c._y + (H - GAP) / 2, mx = x1 + (x2 - x1) / 2;
        paths += `<path d="M${x1} ${y1} H${mx} V${y2} H${x2}" fill="none" stroke="${c._c || "#94A3B8"}" stroke-opacity=".55" stroke-width="1.6"/>` +
          `<circle cx="${mx}" cy="${y2}" r="3" fill="${c._c || "#94A3B8"}"/>`;
      }));
      svg.innerHTML = paths;
      stage.querySelectorAll(".qam-node").forEach((e) => e.remove());
      const frag = document.createDocumentFragment();
      placed.forEach((n) => {
        const d = document.createElement("div"), kids = (n.children || []).length, st = STATE[n.status];
        d.className = `qam-node ${n.kind}${n === selected ? " sel" : ""}${hits.has(n) ? " hit" : ""}`;
        d.style.cssText = `left:${n._x}px;top:${n._y}px;--c:${n._c || "#94A3B8"}`;
        d.title = n.label;
        d.innerHTML = `<span class="ic">${ICON[n.kind] || "•"}</span><span class="t">${esc(n.label)}</span>` +
          (st && n.status !== "ok" && n.status !== "active" ? `<span class="d" style="background:${st[0]}" title="${esc(st[1])}"></span>` : "") +
          (kids ? `<span class="n">${open.has(n.id) ? "‹" : kids + " ›"}</span>` : "");
        d.onclick = () => { if (kids) open.has(n.id) ? open.delete(n.id) : open.add(n.id); select(n); };
        frag.appendChild(d);
      });
      stage.appendChild(frag);
    }

    function crumbs(n) { const out = []; for (let p = parent.get(n); p; p = parent.get(p)) out.unshift(p.label); return out.join(" › "); }

    function select(n, show = true) {
      selected = n; draw();
      const st = STATE[n.status];
      panel.innerHTML = `<button class="qam-x" aria-label="Close">×</button><div class="crumb">${esc(crumbs(n))}</div><h2>${esc(n.label)}</h2>` +
        (st ? `<span class="pill" style="background:${st[0]}">${esc(st[1])}</span>` : "") +
        Object.entries(n.info || {}).map(([k, v]) => `<div class="k">${esc(k)}</div><div class="v">${esc(v)}</div>`).join("") +
        ((n.children || []).length ? `<div class="k">Inside</div><div class="v">${n.children.length} — ${esc(n.children.slice(0, 8).map((c) => c.label).join(", "))}${n.children.length > 8 ? "…" : ""}</div>` : "");
      if (show) panel.classList.add("open"); // a phone: the panel slides over the map only after a tap
      panel.querySelector(".qam-x").onclick = () => panel.classList.remove("open");
    }

    function reveal(n) {
      for (let p = parent.get(n); p; p = parent.get(p)) open.add(p.id);
      hits = new Set([n]); select(n);
      requestAnimationFrame(() => canvas.scrollTo({left: Math.max(0, n._x * zoom - 80), top: Math.max(0, n._y * zoom - canvas.clientHeight / 3), behavior: "smooth"}));
    }

    let box = null;
    search.oninput = () => {
      const q = search.value.trim().toLowerCase();
      if (box) { box.remove(); box = null; }
      if (q.length < 2) { hits = new Set(); draw(); return; }
      const words = q.split(/\s+/);
      const found = all.filter((n) => { const hay = (n.label + " " + n.id + " " + Object.values(n.info || {}).join(" ")).toLowerCase(); return words.every((w) => hay.includes(w)); }).slice(0, 60);
      hits = new Set(found); draw();
      box = document.createElement("div"); box.className = "qam-results";
      box.innerHTML = found.length ? found.map((n, i) => `<div data-i="${i}"><b>${esc(n.label)}</b><br><small>${esc(crumbs(n))}</small></div>`).join("") : `<div><small>Nothing matches.</small></div>`;
      box.onclick = (e) => { const r = e.target.closest("[data-i]"); if (r) { reveal(found[+r.dataset.i]); box.remove(); box = null; } };
      el.querySelector(".qam-body").appendChild(box);
    };
    el.querySelector(".qam-top").onclick = (e) => {
      const a = e.target.dataset && e.target.dataset.a;
      if (a === "in") zoom = Math.min(1.6, zoom + 0.15);
      if (a === "out") zoom = Math.max(0.4, zoom - 0.15);
      if (a === "fold") { open.clear(); open.add("root"); }
      if (a) draw();
    };
    draw(); select(root, false);
  }

  window.QttAppMap = {render};
})();
