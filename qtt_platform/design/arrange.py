"""
QTT Studio › the editor (PROJ-0012 S2, a full editor since 24 Oct 2026): a design's pieces — every line of words, the button,
the badge, the logo, each photo and each decoration — dragged, made bigger or smaller, turned, their words, font, size,
colour and effect changed, photos replaced, cropped, filtered, framed, flipped, put in front or behind, hidden or locked;
new words, badges, shapes, icons and photos added; the background changed. The editor is the design's own page in the app
(Moveable, MIT, for the touch handles); what's saved is a small list of changes per size, which the renderer applies to the
same page with the same script — so the picture is exactly what was made.

  PIECES_JS     numbers the pieces in page order (the same in the editor and the renderer) and applies saved changes
  clean_edits   the app's changes checked (untrusted): known sizes; numbered pieces with a transform of only translate /
                rotate / scale / matrix, words up to 300 characters, a style from fixed choices, a photo of this business;
                up to 40 added pieces (words, badge, shape, icon, photo); a background colour
  sources       the photos the changes use (photo:<Business photo>, cut:<its cut-out>, item:<Business Library picture>,
                logo:main)
  script_for    the changes for one size as a <script> for the page (and the fonts they use)
  editor_page   the page for the app's editor: pictures inlined, Moveable and the editor wired to the app (a web view on
                the phone, an iframe in the web app)

Pure (no Frappe); tests/test_arrange.py.
"""

import base64
import io
import json
import re

FORMATS = ("square", "portrait", "story", "wide", "landscape")  # wide sizes: showcase designs only (studio checks)
MOVEABLE = "https://cdn.jsdelivr.net/npm/moveable@0.53.0/dist/moveable.min.js"
MAX_PIECES = 400
MAX_TEXT = 300
MAX_ADDS = 40
_NUM = r"[-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?(?:px|deg|rad|turn|%)?"
_TF = re.compile(r"^(?:\s*(?:translate|translateX|translateY|rotate|scale|matrix)\(\s*" + _NUM + r"(?:\s*,\s*" + _NUM + r"){0,5}\s*\)\s*)*$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_CLIP = re.compile(r"^inset\(\s*(?:-?[0-9.]+(?:px|%)?\s*){1,4}\)$")
_SRC = re.compile(r"^(?:photo|cut|item|logo):[A-Za-z0-9_.\-]{1,80}$")
_ID = re.compile(r"^[a-z0-9]{1,12}$")

FX = ("none", "shadow", "lift", "glow", "outline", "box")
FILTERS = ("none", "warm", "cool", "bw", "bright", "moody", "vintage")
FRAMES = ("none", "rounded", "circle", "arch", "blob")
ADD_KINDS = ("text", "badge", "shape", "icon", "photo")
SHAPES = ("rect", "rounded", "circle", "ring", "triangle", "star", "line", "arrow", "blob")
BADGES = ("circle", "pill", "tag", "burst", "ribbon")
ICONS = ("star", "heart", "check", "phone", "pin", "clock", "gift", "cake", "lamp", "arrow", "sparkle", "tag", "cart", "truck",
		 "percent", "like")

# The changes, in the page (the same script in the editor and the renderer). Pieces: walking the post, the first element
# that has its own words, or is a picture / drawing / decoration (or is marked data-piece — a device with its screenshot
# moves as one), is a piece (its insides aren't). Anything covering most of the post (the background) isn't, nor anything
# added (data-qtt-add). Then the saved changes: words, styles, photos, added pieces and the background before the text is
# fitted, the moves after — window.qttEdits = {"3": {t, tf, text, hide, s, src}, "_add": [...], "_bg": "#…"}.
PIECES_JS = r"""<script>
window.qttPieces=function(){
  if(window.__qttP)return window.__qttP;
  const post=document.querySelector('.post');if(!post)return [];
  const pr=post.getBoundingClientRect(),area=pr.width*pr.height,out=[];
  const walk=el=>{for(const c of el.children){
    const tag=c.tagName.toLowerCase();if(tag==='script'||tag==='style'||(c.dataset&&c.dataset.qttAdd!==undefined))continue;
    const r=c.getBoundingClientRect(),cs=getComputedStyle(c);
    const words=[...c.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
    const media=tag==='img'||tag==='svg'||c.hasAttribute('data-piece')||c.classList.contains('ph')||(cs.backgroundImage!=='none'&&!c.children.length);
    if((words||media)&&r.width>3&&r.height>3&&r.width*r.height<area*.85){out.push(c);continue}
    if(tag!=='svg')walk(c);
  }};
  walk(post);window.__qttP=out;return out;
};
window.qttText=function(el){
  return el.innerHTML.replace(/<em[^>]*>(.*?)<\/em>/gi,'*$1*').replace(/<br\s*\/?>/gi,'\n').replace(/<[^>]+>/g,'')
    .replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&nbsp;/g,' ').replace(/&amp;/g,'&');
};
window.qttSetText=function(el,t){
  const e=String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  el.innerHTML=e.replace(/\*([^*]+)\*/g,'<em>$1</em>').replace(/\n/g,'<br>');
};
window.qttFit=function(el){if(!el.hasAttribute('data-fit'))return;el.style.fontSize='';const cs=getComputedStyle(el);
  let s=parseFloat(cs.fontSize),m=el.dataset.min?parseFloat(el.dataset.min):s*.42;const mh=cs.maxHeight==='none'?el.clientHeight:parseFloat(cs.maxHeight);
  while((el.scrollHeight>mh+6||el.scrollWidth>el.clientWidth+2)&&s>m){s-=1.5;el.style.fontSize=s+'px'}
};
// a piece brought forward: it, and every layer around it that has a stacking order of its own
window.qttFront=function(el,z){
  for(let a=el;a&&!(a.classList&&a.classList.contains('post'));a=a.parentElement){const cs=getComputedStyle(a);
    if(a===el||cs.position!=='static'||cs.transform!=='none'||cs.zIndex!=='auto'||parseFloat(cs.opacity)<1){
      if(cs.position==='static')a.style.position='relative';a.style.zIndex=String(z===undefined?60:z)}}
};
window.qttSrcUrl=function(ref){return (window.qttSrc||{})[ref]||''};
const ICON={star:'M12 2l3 7h7l-5.5 4.5 2 7.5-6.5-4.5-6.5 4.5 2-7.5L2 9h7z',heart:'M12 21s-8-5.2-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.8-8 11-8 11z',
  check:'M4 12l5 5L20 6',phone:'M5 3h4l2 5-3 2a12 12 0 0 0 6 6l2-3 5 2v4a2 2 0 0 1-2 2A18 18 0 0 1 3 5a2 2 0 0 1 2-2z',
  pin:'M12 22s7-7.5 7-13a7 7 0 0 0-14 0c0 5.5 7 13 7 13zM12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',clock:'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2',
  gift:'M3 9h18v4H3zM5 13h14v8H5zM12 9v12M12 9C10 4 6 5 7.5 8M12 9c2-5 6-4 4.5-1',cake:'M4 21h16v-8H4zM4 16c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 4 0M8 13V9M12 13V9M16 13V9',
  lamp:'M3 13c0 4 4 6 9 6s9-2 9-6zM12 11c-2-2-1.5-5 0-8 1.5 3 2 6 0 8z',arrow:'M3 12h16M13 6l6 6-6 6',sparkle:'M12 2l2 7 7 3-7 3-2 7-2-7-7-3 7-3z',
  tag:'M3 12V3h9l9 9-9 9zM7.5 7.5h.01',cart:'M3 4h3l2.5 11h11L22 7H7M10 20h.01M18 20h.01',truck:'M2 6h12v10H2zM14 10h4l4 4v2h-8zM6 19h.01M18 19h.01',
  percent:'M19 5L5 19M7 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',like:'M7 22V11M2 13v7a2 2 0 0 0 2 2h12.5a2 2 0 0 0 2-1.6l1.4-7A2 2 0 0 0 18 11h-5V6a3 3 0 0 0-3-3l-3 8'};
const FILLED={star:1,heart:1,sparkle:1,lamp:1};
const SHAPE={rect:'<rect width="100" height="100"/>',rounded:'<rect width="100" height="100" rx="18"/>',circle:'<ellipse cx="50" cy="50" rx="50" ry="50"/>',
  ring:'<ellipse cx="50" cy="50" rx="46" ry="46" fill="none" stroke="C" stroke-width="8"/>',triangle:'<polygon points="50,0 100,100 0,100"/>',
  star:'<polygon points="50,0 61,35 98,35 68,57 79,91 50,70 21,91 32,57 2,35 39,35"/>',line:'<rect y="44" width="100" height="12"/>',
  arrow:'<polygon points="0,38 66,38 66,15 100,50 66,85 66,62 0,62"/>',blob:'<path d="M50 2C78 2 98 22 96 50s-22 48-48 46S2 76 4 48 22 2 50 2z"/>'};
const BADGE={circle:'border-radius:50%',pill:'border-radius:999px',tag:'border-radius:14px',
  burst:'clip-path:polygon(50% 0,61% 13%,75% 7%,79% 22%,93% 25%,88% 39%,100% 50%,88% 61%,93% 75%,79% 78%,75% 93%,61% 87%,50% 100%,39% 87%,25% 93%,21% 78%,7% 75%,12% 61%,0 50%,12% 39%,7% 25%,21% 22%,25% 7%,39% 13%)',
  ribbon:'clip-path:polygon(0 0,100% 0,92% 50%,100% 100%,0 100%,8% 50%)'};
const FLT={warm:'sepia(.25) saturate(1.25) hue-rotate(-8deg)',cool:'saturate(1.05) hue-rotate(12deg) brightness(1.03)',bw:'grayscale(1)',
  bright:'brightness(1.15) contrast(1.05) saturate(1.15)',moody:'brightness(.88) contrast(1.2) saturate(.85)',vintage:'sepia(.45) contrast(.95) brightness(1.05)'};
const FRAME={rounded:'28px',circle:'50%',arch:'50% 50% 24px 24px / 34% 34% 24px 24px',blob:'62% 38% 46% 54% / 48% 56% 44% 52%'};
window.qttIconSvg=function(name,c){const d=ICON[name]||ICON.star;const f=FILLED[name];
  return '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="'+(f?c:'none')+'" stroke="'+c+'" stroke-width="'+(f?0:2)+'" stroke-linecap="round" stroke-linejoin="round"><path d="'+d+'"/></svg>'};
window.qttShapeSvg=function(name,c){return '<svg viewBox="0 0 100 100" width="100%" height="100%" preserveAspectRatio="none" fill="'+c+'">'+(SHAPE[name]||SHAPE.rect).replace('stroke="C"','stroke="'+c+'"')+'</svg>'};
// one piece's (or added piece's) look
window.qttStyle=function(el,s){if(!s)return;const st=el.style;
  if(s.f){st.fontFamily='"'+s.f+'", sans-serif'}
  if(s.fs){st.fontSize=s.fs+'px';el.removeAttribute('data-fit');st.maxHeight='none';st.overflow='visible'}
  if(s.fw)st.fontWeight=String(s.fw);
  if(s.it!==undefined)st.fontStyle=s.it?'italic':'normal';
  if(s.al)st.textAlign=s.al;
  if(s.c&&el.dataset.qttKind!=='shape'&&el.dataset.qttKind!=='icon'){st.color=s.c;st.webkitTextFillColor=s.c}
  if(s.fx){const c=s.c||'#ffffff';
    if(s.fx==='shadow')st.textShadow='0 6px 18px rgba(0,0,0,.45)';
    else if(s.fx==='lift')st.textShadow='0 12px 34px rgba(0,0,0,.35)';
    else if(s.fx==='glow')st.textShadow='0 0 18px '+c+', 0 0 40px '+c;
    else if(s.fx==='outline'){st.webkitTextStroke='3px '+c;st.webkitTextFillColor='transparent';st.color='transparent'}
    else if(s.fx==='box'){st.background=s.bg||'#111111';st.padding='.12em .4em';st.borderRadius='.25em';st.boxDecorationBreak='clone';st.webkitBoxDecorationBreak='clone'}
    else if(s.fx==='none'){st.textShadow='none';st.webkitTextStroke='0'}}
  if(s.op!==undefined)st.opacity=String(s.op);
  if(s.fl)st.scale='-1 1';
  let f=s.flt&&FLT[s.flt]?FLT[s.flt]:'';
  if(s.br!==undefined)f+=' brightness('+s.br/100+')';if(s.ct!==undefined)f+=' contrast('+s.ct/100+')';
  if(s.sa!==undefined)f+=' saturate('+s.sa/100+')';if(s.bl)f+=' blur('+s.bl+'px)';
  if(f.trim())st.filter=f.trim();
  if(s.fr&&FRAME[s.fr]){st.borderRadius=FRAME[s.fr];st.overflow='hidden'}
  if(s.clip)st.clipPath=s.clip;
  if(s.z!==undefined)qttFront(el,40+s.z);
};
window.qttSetSrc=function(el,ref){const u=qttSrcUrl(ref);if(!u)return;
  if(el.tagName==='IMG'){el.src=u;el.removeAttribute('srcset')}else{el.style.backgroundImage='url("'+u+'")';el.style.backgroundSize='cover';el.style.backgroundPosition='center'}};
window.qttAdd=function(a){const post=document.querySelector('.post');if(!post)return null;const s=a.s||{};let el;
  const brand=getComputedStyle(post).getPropertyValue('--primary').trim()||'#2a3b8f';
  if(a.k==='photo'){el=document.createElement('img');el.src=qttSrcUrl(a.src);el.style.objectFit='cover';el.draggable=false}
  else{el=document.createElement('div');
    if(a.k==='text'){qttSetText(el,a.text||'');el.style.cssText='white-space:pre-wrap;line-height:1.15;font-family:var(--font-heading),sans-serif;font-weight:700;font-size:64px;color:#111111'}
    else if(a.k==='badge'){qttSetText(el,a.text||'NEW');el.style.cssText='display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.05;font-family:var(--font-heading),sans-serif;font-weight:800;font-size:44px;padding:8px;color:#ffffff;background:'+(s.bg||brand)+';'+(BADGE[a.shape]||BADGE.circle)}
    else if(a.k==='shape'){el.innerHTML=qttShapeSvg(a.shape,s.bg||s.c||brand)}
    else if(a.k==='icon'){el.innerHTML=qttIconSvg(a.icon,s.c||brand)}}
  el.dataset.qttAdd=a.id;el.dataset.qttKind=a.k;
  Object.assign(el.style,{position:'absolute',left:a.x+'px',top:a.y+'px',width:a.w+'px',boxSizing:'border-box',margin:'0'});
  if(a.k!=='text')el.style.height=a.h+'px';
  if(a.tf)el.style.transform=a.tf;
  el.style.zIndex='70';qttStyle(el,s);
  if(a.hide)el.style.visibility='hidden';
  post.appendChild(el);return el;
};
// a new background: a plain colour behind everything; the design's own background layers (no words, no photos) step aside
window.qttBg=function(c){if(!c)return;const post=document.querySelector('.post');if(!post)return;
  const pr=post.getBoundingClientRect(),area=pr.width*pr.height;
  for(const ch of [...post.children]){if(ch.dataset.qttAdd!==undefined||ch.tagName==='SCRIPT'||ch.tagName==='STYLE')continue;
    const r=ch.getBoundingClientRect();if(r.width*r.height<area*.85)continue;
    if(!ch.innerText.trim()&&!ch.querySelector('img'))ch.style.visibility='hidden';else{ch.style.background='transparent'}}
  const b=document.createElement('div');b.dataset.qttAdd='bg';b.style.cssText='position:absolute;inset:0;z-index:-1;background:'+c;post.prepend(b);post.style.background=c};
window.qttWords=function(edits){const p=qttPieces();edits=edits||{};
  for(const k in edits){const e=edits[k],el=p[+k];if(k[0]==='_'||!el||el.tagName!==e.t)continue;
    if(typeof e.text==='string')qttSetText(el,e.text);
    if(e.src)qttSetSrc(el,e.src);
    if(e.s)qttStyle(el,e.s);}
  if(edits._bg)qttBg(edits._bg);
  for(const a of (edits._add||[]))qttAdd(a);
};
window.qttMoves=function(edits){const p=qttPieces();
  for(const k in (edits||{})){const e=edits[k],el=p[+k];if(k[0]==='_'||!el||el.tagName!==e.t)continue;
    if(e.tf){el.style.transform=e.tf;if(!(e.s&&e.s.z!==undefined))qttFront(el)}if(e.hide)el.style.visibility='hidden';}
};
</script>"""


def _num(v, lo, hi, *, integer=True):
	try:
		n = float(v)
	except (TypeError, ValueError):
		return None
	if n != n or n < lo or n > hi:
		return None
	return int(round(n)) if integer else round(n, 3)


def _fonts() -> tuple:
	from qtt_platform.design import base

	return tuple(base.FONTS)


def clean_style(raw) -> dict:
	"""A piece's look, only from fixed choices (colours as #rrggbb, numbers in range, names from the lists)."""
	if not isinstance(raw, dict):
		return {}
	s = {}
	for k in ("c", "bg"):
		if isinstance(raw.get(k), str) and _COLOR.match(raw[k]):
			s[k] = raw[k].lower()
	if raw.get("f") in _fonts():
		s["f"] = raw["f"]
	for k, lo, hi in (("fs", 8, 400), ("z", -20, 99), ("br", 30, 200), ("ct", 30, 200), ("sa", 0, 250), ("bl", 0, 30)):
		n = _num(raw.get(k), lo, hi)
		if n is not None:
			s[k] = n
	if raw.get("fw") in (400, 700, 800, "400", "700", "800"):
		s["fw"] = int(raw["fw"])
	for k in ("it", "fl"):
		if raw.get(k) in (True, 1, "1", "true"):
			s[k] = 1
		elif k == "it" and raw.get(k) in (False, 0, "0", "false"):
			s[k] = 0
	if raw.get("al") in ("left", "center", "right"):
		s["al"] = raw["al"]
	for k, allowed in (("fx", FX), ("flt", FILTERS), ("fr", FRAMES)):
		if raw.get(k) in allowed:
			s[k] = raw[k]
	op = _num(raw.get("op"), 0.05, 1, integer=False)
	if op is not None:
		s["op"] = op
	if isinstance(raw.get("clip"), str) and len(raw["clip"]) <= 80 and _CLIP.match(raw["clip"].strip()):
		s["clip"] = raw["clip"].strip()
	return s


def _clean_add(a) -> dict | None:
	if not isinstance(a, dict) or a.get("k") not in ADD_KINDS or not _ID.match(str(a.get("id") or "")):
		return None
	out = {"id": str(a["id"]), "k": a["k"]}
	for k, lo, hi in (("x", -3000, 5000), ("y", -3000, 5000), ("w", 8, 5000), ("h", 8, 5000)):
		n = _num(a.get(k), lo, hi, integer=False)
		if n is None:
			if k in ("x", "y", "w") or a["k"] != "text":
				return None
			continue
		out[k] = n
	tf = str(a.get("tf") or "").strip()
	if tf and len(tf) <= 300 and _TF.match(tf):
		out["tf"] = tf
	if a["k"] in ("text", "badge"):
		if not isinstance(a.get("text"), str):
			return None
		out["text"] = a["text"][:MAX_TEXT]
	if a["k"] == "badge":
		out["shape"] = a.get("shape") if a.get("shape") in BADGES else "circle"
	if a["k"] == "shape":
		out["shape"] = a.get("shape") if a.get("shape") in SHAPES else "rect"
	if a["k"] == "icon":
		out["icon"] = a.get("icon") if a.get("icon") in ICONS else "star"
	if a["k"] == "photo":
		if not (isinstance(a.get("src"), str) and _SRC.match(a["src"])):
			return None
		out["src"] = a["src"]
	s = clean_style(a.get("s"))
	if s:
		out["s"] = s
	for k in ("hide", "lock"):
		if a.get(k) in (True, 1, "1", "true"):
			out[k] = 1
	return out


def clean_edits(raw) -> dict:
	"""{format: {piece: {t, tf?, text?, hide?, s?, src?, lock?}, "_add": [...], "_bg": "#…"}} — only what's valid."""
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return {}
	out = {}
	if not isinstance(raw, dict):
		return out
	for fmt, pieces in raw.items():
		if fmt not in FORMATS or not isinstance(pieces, dict):
			continue
		got = {}
		for k, e in list(pieces.items())[:MAX_PIECES + 2]:
			if k == "_bg":
				if isinstance(e, str) and _COLOR.match(e):
					got["_bg"] = e.lower()
				continue
			if k == "_add":
				adds, seen = [], set()
				for a in (e if isinstance(e, list) else [])[:MAX_ADDS]:
					c = _clean_add(a)
					if c and c["id"] not in seen and c["id"] != "bg":
						seen.add(c["id"])
						adds.append(c)
				if adds:
					got["_add"] = adds
				continue
			if not str(k).isdigit() or int(k) >= MAX_PIECES or not isinstance(e, dict):
				continue
			t = str(e.get("t") or "")
			if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,9}", t):
				continue
			one = {"t": t.upper() if t.lower() != "svg" else "svg"}
			tf = str(e.get("tf") or "").strip()
			if tf and len(tf) <= 300 and _TF.match(tf):
				one["tf"] = tf
			if isinstance(e.get("text"), str):
				one["text"] = e["text"][:MAX_TEXT]
			for flag in ("hide", "lock"):
				if e.get(flag) in (True, 1, "1", "true"):
					one[flag] = 1
			s = clean_style(e.get("s"))
			if s:
				one["s"] = s
			if isinstance(e.get("src"), str) and _SRC.match(e["src"]):
				one["src"] = e["src"]
			if len(one) > 1 and not (len(one) == 2 and "lock" in one):
				got[str(int(k))] = one
		if got:
			out[fmt] = got
	return out


def without_text(edits: dict) -> dict:
	"""The same changes without words typed on the design's own pieces (the design's words were changed another way);
	added pieces and the background stay."""
	out = {}
	for fmt, pieces in (edits or {}).items():
		kept = {}
		for k, e in pieces.items():
			if k.startswith("_"):
				kept[k] = e
				continue
			e = {x: v for x, v in e.items() if x != "text"}
			if len(e) > 1:
				kept[k] = e
		if kept:
			out[fmt] = kept
	return out


def sources(edits: dict | None, fmt: str | None = None) -> list[str]:
	"""The photos the changes use (for one size, or every size), each once."""
	refs = []
	for f, pieces in (edits or {}).items():
		if fmt and f != fmt:
			continue
		for k, e in (pieces or {}).items():
			if k == "_add":
				refs += [a["src"] for a in e if a.get("src")]
			elif isinstance(e, dict) and e.get("src"):
				refs.append(e["src"])
	return list(dict.fromkeys(r for r in refs if _SRC.match(r)))


def src_name(ref: str, ext: str = "jpg") -> str:
	"""The file name a photo travels under beside the page."""
	return "src-" + re.sub(r"[^A-Za-z0-9]", "-", ref)[:90] + "." + ext


def _json(v) -> str:
	return json.dumps(v, ensure_ascii=False).replace("<", "\\u003c")


def _font_loader(families: list[str]) -> str:
	"""Fonts the changes use beyond the design's own: loaded before the words are fitted (layouts.FIT_SCRIPT waits)."""
	from qtt_platform.design import base

	urls = {f: base.font_url(f) for f in families if f in _fonts()}
	if not urls:
		return ""
	return ("<script>window.qttLinks=Promise.all(Object.entries(" + _json(urls) + ").map(([f,u])=>new Promise(r=>{"
			"const l=document.createElement('link');l.rel='stylesheet';l.href=u;setTimeout(r,5000);l.onerror=r;"
			"l.onload=()=>Promise.all(['400','700'].map(w=>document.fonts.load(w+' 40px \"'+f+'\"'))).then(r,r);"
			"document.head.appendChild(l)})))</script>")


def _families(one: dict) -> list[str]:
	out = [e["s"]["f"] for k, e in one.items() if k[:1] != "_" and isinstance(e, dict) and (e.get("s") or {}).get("f")]
	out += [a["s"]["f"] for a in one.get("_add") or [] if (a.get("s") or {}).get("f")]
	return list(dict.fromkeys(out))


def script_for(edits: dict | None, fmt: str, srcs: dict | None = None) -> str:
	"""The page's saved changes for one size (an empty string when there are none). srcs: {photo ref: file name}."""
	one = (edits or {}).get(fmt) or {}
	if not one:
		return ""
	src = f"<script>window.qttSrc={_json(srcs)}</script>" if srcs else ""
	return f"{_font_loader(_families(one))}{src}<script>window.qttEdits={_json(one)}</script>"


def _data_uri(name: str, data: bytes) -> str:
	"""A picture as a data: address for the editor (photos brought down to 1200 px so the page stays light)."""
	ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
	if ext in ("jpg", "jpeg", "webp", "png") and len(data) > 250_000:
		try:
			from PIL import Image

			im = Image.open(io.BytesIO(data))
			im.thumbnail((1200, 1200))
			buf = io.BytesIO()
			if im.mode in ("RGBA", "LA", "P") and ext == "png":
				im.save(buf, "PNG", optimize=True)
			else:
				im.convert("RGB").save(buf, "JPEG", quality=82)
				ext = "jpg"
			data = buf.getvalue()
		except Exception:
			pass
	mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml"}.get(ext, "image/png")
	return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def data_uri(name: str, data: bytes) -> str:
	return _data_uri(name, data)


def inline_files(page: str, files: dict[str, bytes]) -> str:
	"""The page's pictures (referenced by file name) put inside it, for a page with no file server behind it."""
	for name, data in files.items():
		uri = _data_uri(name, data)
		page = re.sub(r"(?<=[\"'(])" + re.escape(name) + r"(?=[\"')])", uri, page)
	return page


# The editor in the app. Messages to the app: a web view's QttEditor channel on the phone, the parent window in the web
# app (an iframe). Calls from the app: qttEditor.call(name, …args) on the phone, a {qttCall, args} message in the web app.
# Every change is kept as the same list the renderer reads; undo / redo put the page back as it was and apply the list.
EDITOR_JS = r"""<script>
(function(){
  const send=m=>{const j=JSON.stringify(m);try{QttEditor.postMessage(j);return}catch(e){}try{parent.postMessage({qttEditor:j},'*')}catch(e){}};
  let edits=JSON.parse(JSON.stringify(window.qttSaved||{}));let mv=null,sel=null,pristine='',undo=[],redo=[],cropping=false;
  const post=()=>document.querySelector('.post');
  const isAdd=k=>typeof k==='string'&&k.startsWith('a:');
  const addOf=k=>(edits._add||[]).find(a=>a.id===k.slice(2));
  const elOf=k=>k===null?null:isAdd(k)?post().querySelector('[data-qtt-add="'+k.slice(2)+'"]'):qttPieces()[+k.slice(1)];
  const kindOf=(k,el)=>{if(isAdd(k)){const a=addOf(k);return a?a.k:'text'}
    if([...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))return 'text';
    const t=el.tagName.toLowerCase();return t==='img'||el.classList.contains('ph')||getComputedStyle(el).backgroundImage!=='none'?'picture':'graphic'};
  const entry=k=>{if(isAdd(k))return addOf(k);const i=k.slice(1),el=elOf(k);return edits[i]||(edits[i]={t:el.tagName})};
  const tidy=()=>{for(const k in edits){if(k[0]==='_')continue;const e=edits[k];if(e.s&&!Object.keys(e.s).length)delete e.s;if(Object.keys(e).length<2)delete edits[k]}
    if(edits._add&&!edits._add.length)delete edits._add};
  const snap=()=>JSON.stringify(edits);
  const status=()=>send({type:'changed',canUndo:undo.length>0,canRedo:redo.length>0});
  const commit=before=>{tidy();if(before!==snap()){undo.push(before);if(undo.length>60)undo.shift();redo=[]}status()};
  function render(){
    if(mv){mv.destroy();mv=null}
    const p=post();p.innerHTML=pristine;p.setAttribute('style',p.dataset.qttBase||'');scale();window.__qttP=null;
    const pieces=qttPieces();
    pieces.forEach((el,i)=>{el.style.cursor='pointer'});
    qttWords(edits);
    for(const k in edits)if(k[0]!=='_'&&(typeof edits[k].text==='string'||(edits[k].s&&edits[k].s.f))&&pieces[+k])qttFit(pieces[+k]);
    qttMoves(edits);
    for(const k in edits)if(k[0]!=='_'&&edits[k].hide&&pieces[+k]){pieces[+k].style.visibility='visible';pieces[+k].style.opacity='.3'}
    for(const a of (edits._add||[]))if(a.hide){const el=elOf('a:'+a.id);if(el){el.style.visibility='visible';el.style.opacity='.3'}}
  }
  function tell(){
    if(sel===null){send({type:'select',key:null});return}
    const el=elOf(sel);if(!el){sel=null;send({type:'select',key:null});return}
    const e=isAdd(sel)?addOf(sel):(edits[sel.slice(1)]||{});const kind=kindOf(sel,el);
    const cs=getComputedStyle(el);
    send({type:'select',key:sel,kind:kind,add:isAdd(sel),text:(kind==='text'||kind==='badge')?(isAdd(sel)?(e.text||''):qttText(el)):'',
      s:e.s||{},hidden:!!e.hide,locked:!!e.lock,src:e.src||'',shape:e.shape||e.icon||'',
      font:(cs.fontFamily||'').split(',')[0].replace(/["']/g,'').trim(),size:Math.round(parseFloat(cs.fontSize)||0),color:cs.color});
  }
  function select(k){
    if(mv){mv.destroy();mv=null}
    sel=k;const el=elOf(k);if(!el){sel=null;tell();return}
    const e=isAdd(k)?addOf(k):(edits[k.slice(1)]||{});
    if(!e.lock){
      if(cropping){
        mv=new Moveable(document.body,{target:el,clippable:true,clipRelative:false,clipArea:true,dragWithClip:false,defaultClipPath:'inset',origin:false});
        mv.on('clip',ev=>{ev.target.style.clipPath=ev.clipStyle}).on('clipEnd',ev=>{const b=snap();const en=entry(k);en.s=Object.assign(en.s||{},{clip:el.style.clipPath});commit(b)});
      }else{
        mv=new Moveable(document.body,{target:el,draggable:true,scalable:true,keepRatio:true,rotatable:true,origin:false,
          throttleScale:0.01,renderDirections:['nw','ne','sw','se'],pinchable:true,snappable:true,snapCenter:true,
          elementGuidelines:[post()],snapThreshold:6});
        const keep=()=>{const b=snap();const en=entry(k);en.tf=el.style.transform;if(!isAdd(k)&&!(en.s&&en.s.z!==undefined))qttFront(el);commit(b)};
        mv.on('drag',ev=>{ev.target.style.transform=ev.transform}).on('scale',ev=>{ev.target.style.transform=ev.transform})
          .on('rotate',ev=>{ev.target.style.transform=ev.transform}).on('dragEnd',keep).on('scaleEnd',keep).on('rotateEnd',keep);
      }
    }
    tell();
  }
  function change(fn,rerender){const b=snap();const k=sel;fn();commit(b);if(rerender!==false){render();if(k!==null&&elOf(k))select(k);else{sel=null;tell()}}}
  const center=(w,h)=>{const p=post();const W=1080,H=p.offsetHeight||1080;return {x:Math.round((W-w)/2),y:Math.round((H-h)/2)}};
  const newId=()=>Math.random().toString(36).slice(2,10);
  function layers(){
    const items=[];
    qttPieces().forEach((el,i)=>{const e=edits[i]||{};const kind=kindOf('p'+i,el);
      items.push({key:'p'+i,kind:kind,name:kind==='text'?qttText(el).replace(/\n/g,' ').slice(0,40):(kind==='picture'?'Photo':'Decoration'),hidden:!!e.hide,locked:!!e.lock,
        z:(e.s&&e.s.z!==undefined)?e.s.z:null})});
    (edits._add||[]).forEach(a=>items.push({key:'a:'+a.id,kind:a.k,name:a.text?a.text.replace(/\n/g,' ').slice(0,40):(a.shape||a.icon||a.k),hidden:!!a.hide,locked:!!a.lock,
      z:(a.s&&a.s.z!==undefined)?a.s.z:null,add:true}));
    send({type:'layers',items:items});
  }
  const api={
    select:k=>select(k),
    none:()=>{if(mv)mv.destroy();mv=null;sel=null;cropping=false;tell()},
    text:t=>{if(sel===null)return;change(()=>{const e=entry(sel);e.text=String(t).slice(0,300)})},
    style:o=>{if(sel===null)return;change(()=>{const e=entry(sel);const s=Object.assign({},e.s||{});
      for(const k in o){if(o[k]===null||o[k]===undefined)delete s[k];else s[k]=o[k]}e.s=s})},
    clearStyle:keys=>{if(sel===null)return;change(()=>{const e=entry(sel);if(e.s)for(const k of keys)delete e.s[k]})},
    add:o=>{const b=snap();const w=o.w||(o.k==='text'?700:o.k==='photo'?520:260),h=o.h||(o.k==='text'?0:o.k==='photo'?520:(o.k==='shape'&&o.shape==='line'?40:260));
      const c=center(w,h||120);const a=Object.assign({id:newId(),x:c.x,y:c.y,w:w},o);if(o.k!=='text')a.h=h;delete a.url;
      if(o.url){window.qttSrc=Object.assign(window.qttSrc||{},{[o.src]:o.url})}
      (edits._add||(edits._add=[])).push(a);commit(b);render();select('a:'+a.id)},
    dup:()=>{if(sel===null)return;const b=snap();let a;
      if(isAdd(sel)){a=JSON.parse(JSON.stringify(addOf(sel)));a.id=newId();a.x+=40;a.y+=40;delete a.lock}
      else{const el=elOf(sel);if(kindOf(sel,el)!=='text')return;const cs=getComputedStyle(el),pr=post().getBoundingClientRect(),r=el.getBoundingClientRect(),k=1080/pr.width;
        a={id:newId(),k:'text',text:qttText(el),x:Math.round((r.left-pr.left)*k)+40,y:Math.round((r.top-pr.top)*k)+40,w:Math.round(r.width*k)+20,
          s:{fs:Math.round(parseFloat(cs.fontSize)),c:'#'+(cs.color.match(/\d+/g)||[0,0,0]).slice(0,3).map(n=>(+n).toString(16).padStart(2,'0')).join(''),fw:+cs.fontWeight>=700?700:400}}}
      (edits._add||(edits._add=[])).push(a);commit(b);render();select('a:'+a.id)},
    del:()=>{if(sel===null)return;const k=sel;change(()=>{if(isAdd(k))edits._add=(edits._add||[]).filter(a=>'a:'+a.id!==k);else entry(k).hide=1});sel=null;if(mv){mv.destroy();mv=null}tell()},
    hide:k=>{const key=k||sel;if(key===null)return;const b=snap();const e=entry(key);if(e.hide)delete e.hide;else e.hide=1;commit(b);render();if(sel!==null&&elOf(sel))select(sel);layers()},
    lock:k=>{const key=k||sel;if(key===null)return;const b=snap();const e=entry(key);if(e.lock)delete e.lock;else e.lock=1;commit(b);render();if(sel!==null&&elOf(sel))select(sel);layers()},
    order:keys=>{const b=snap();const n=keys.length;keys.forEach((k,i)=>{const e=entry(k);if(!e)return;e.s=Object.assign(e.s||{},{z:Math.max(-20,Math.min(99,n-i))})});
      commit(b);render();if(sel!==null&&elOf(sel))select(sel);layers()},
    forward:()=>{if(sel===null)return;change(()=>{const e=entry(sel);e.s=Object.assign(e.s||{},{z:Math.min(99,((e.s&&e.s.z)||0)+5)})})},
    backward:()=>{if(sel===null)return;change(()=>{const e=entry(sel);e.s=Object.assign(e.s||{},{z:Math.max(-20,((e.s&&e.s.z)||0)-5)})})},
    replace:(src,url)=>{if(sel===null)return;window.qttSrc=Object.assign(window.qttSrc||{},{[src]:url});change(()=>{entry(sel).src=src})},
    crop:on=>{cropping=!!on;if(sel!==null)select(sel)},
    uncrop:()=>{if(sel===null)return;cropping=false;change(()=>{const e=entry(sel);if(e.s)delete e.s.clip})},
    bg:c=>{change(()=>{if(c)edits._bg=c;else delete edits._bg})},
    undo:()=>{if(!undo.length)return;redo.push(snap());edits=JSON.parse(undo.pop());render();sel=null;tell();status()},
    redo:()=>{if(!redo.length)return;undo.push(snap());edits=JSON.parse(redo.pop());render();sel=null;tell();status()},
    layers:layers,
    sendEdits:()=>{tidy();send({type:'edits',json:JSON.stringify(edits)})},
    resetAll:()=>{const b=snap();edits={};commit(b);render();sel=null;tell()},
  };
  window.qttEditor=Object.assign(api,{edits:()=>{tidy();return JSON.stringify(edits)},call:(n,...a)=>api[n]&&api[n](...a),
    size:f=>{if(sel===null)return;const el=elOf(sel);el.style.transform=(el.style.transform||'')+' scale('+f+')';const b=snap();entry(sel).tf=el.style.transform.trim();commit(b);if(mv)mv.updateRect()},
    reset:()=>{if(sel===null)return;change(()=>{if(isAdd(sel)){const a=addOf(sel);delete a.tf}else delete edits[sel.slice(1)]})}});
  window.addEventListener('message',ev=>{let d=ev.data;if(typeof d==='string'){try{d=JSON.parse(d)}catch(e){return}}if(d&&typeof d.qttCall==='string'&&api[d.qttCall])api[d.qttCall](...(d.args||[]))});
  const scale=()=>{const p=post();if(!p)return;const k=window.innerWidth/1080;
    p.style.transform='scale('+k+')';p.style.transformOrigin='0 0';document.body.style.height=Math.ceil(p.offsetHeight*k)+'px'};
  const fit=()=>{scale();if(mv)mv.updateRect()};
  const start=()=>{
    post().dataset.qttBase=post().getAttribute('style')||'';fit();window.addEventListener('resize',fit);
    pristine=post().innerHTML;
    render();
    document.addEventListener('click',ev=>{
      if(ev.target.closest&&ev.target.closest('.moveable-control-box'))return;
      const add=ev.target.closest&&ev.target.closest('[data-qtt-add]');
      if(add&&add.dataset.qttAdd!=='bg'){const a=addOf('a:'+add.dataset.qttAdd);if(a&&!a.lock){select('a:'+a.id);return}}
      const p=qttPieces();const i=p.findIndex(el=>el===ev.target||el.contains(ev.target));
      if(i>=0&&!(edits[i]&&edits[i].lock)){cropping=false;select('p'+i)}else api.none();
    },true);
    send({type:'ready',pieces:qttPieces().length});status();
  };
  const wait=()=>window.qttReady&&window.Moveable?start():setTimeout(wait,80);wait();
})();
</script>"""


def editor_page(page: str, files: dict[str, bytes], width: int, edits_for_format: dict | None, srcs: dict | None = None) -> str:
	"""The design's page for the app's editor: its pictures inside it, the page as wide as the frame, Moveable and the
	editor. The page's own fitting runs first, unchanged. srcs: {photo ref: file name} for the photos the changes use."""
	from qtt_platform.design import base

	page = inline_files(page, files)
	# The design is drawn 1080 wide; the editor shrinks it to the frame's width itself (an Android web view doesn't
	# always honour a fixed viewport width), so the page is the frame's width and the post is scaled inside it.
	head = ('<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">'
			"<style>html,body{width:100%!important;height:auto!important;overflow-x:hidden!important;overflow-y:auto!important;"
			"-webkit-user-select:none;user-select:none;touch-action:none}.moveable-control-box{z-index:9999}</style>")
	page = page.replace("</head>", head + "</head>", 1)
	uris = {ref: _data_uri(name, files[name]) for ref, name in (srcs or {}).items() if name in files}
	fonts = {f: base.font_url(f) for f in _fonts()}
	# fonts chosen in the editor come in as they're picked
	loader = ("<script>window.qttFontUrls=" + _json(fonts) + ";(function(){const seen={};const st=window.qttStyle;"
			  "window.qttStyle=function(el,s){if(s&&s.f&&!seen[s.f]&&qttFontUrls[s.f]){seen[s.f]=1;const l=document.createElement('link');"
			  "l.rel='stylesheet';l.href=qttFontUrls[s.f];document.head.appendChild(l)}return st(el,s)}})()</script>")
	saved = f"<script>window.qttSaved={_json(edits_for_format or {})};window.qttSrc={_json(uris)}</script>"
	tail = f'{saved}{loader}<script src="{MOVEABLE}"></script>{EDITOR_JS}'
	return page.replace("</body>", tail + "</body>", 1)
