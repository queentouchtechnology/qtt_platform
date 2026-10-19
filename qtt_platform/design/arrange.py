"""
QTT Studio › Move and resize (PROJ-0012 S2): a design's pieces — every line of words, the button, the badge, the logo,
each photo and each decoration — dragged, made bigger or smaller, turned, their words changed or hidden, on the design
itself. The editor is the design's own page in the app (Moveable, MIT, for the touch handles); what's saved is a small
list of changes per size, which the renderer applies to the same page — so the picture is exactly what was arranged.

  PIECES_JS     numbers the pieces in page order (the same in the editor and the renderer) and applies saved changes
  clean_edits   the app's changes checked (untrusted): known sizes, numbered pieces, a transform of only translate /
                rotate / scale / matrix, words up to 300 characters, hidden or not
  script_for    the changes for one size as a <script> for the page
  editor_page   the page for the app's editor: pictures inlined, Moveable and the editor wired to the app

Pure (no Frappe); tests/test_arrange.py.
"""

import base64
import io
import json
import re

FORMATS = ("square", "portrait", "story")
MOVEABLE = "https://cdn.jsdelivr.net/npm/moveable@0.53.0/dist/moveable.min.js"
MAX_PIECES = 400
MAX_TEXT = 300
_NUM = r"[-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?(?:px|deg|rad|turn|%)?"
_TF = re.compile(r"^(?:\s*(?:translate|translateX|translateY|rotate|scale|matrix)\(\s*" + _NUM + r"(?:\s*,\s*" + _NUM + r"){0,5}\s*\)\s*)*$")

# The pieces: walking the post, the first element that has its own words, or is a picture / drawing / decoration, is a
# piece (its insides aren't). Anything covering most of the post (the background) isn't. Then the saved changes:
# words (before the text is fitted), and after fitting the moves — window.qttEdits = {"3": {t, tf, text, hide}}.
PIECES_JS = """<script>
window.qttPieces=function(){
  if(window.__qttP)return window.__qttP;
  const post=document.querySelector('.post');if(!post)return [];
  const pr=post.getBoundingClientRect(),area=pr.width*pr.height,out=[];
  const walk=el=>{for(const c of el.children){
    const tag=c.tagName.toLowerCase();if(tag==='script'||tag==='style')continue;
    const r=c.getBoundingClientRect(),cs=getComputedStyle(c);
    const words=[...c.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
    const media=tag==='img'||tag==='svg'||c.classList.contains('ph')||(cs.backgroundImage!=='none'&&!c.children.length);
    if((words||media)&&r.width>3&&r.height>3&&r.width*r.height<area*.85){out.push(c);continue}
    if(tag!=='svg')walk(c);
  }};
  walk(post);window.__qttP=out;return out;
};
window.qttText=function(el){
  return el.innerHTML.replace(/<em[^>]*>(.*?)<\\/em>/gi,'*$1*').replace(/<br\\s*\\/?>/gi,'\\n').replace(/<[^>]+>/g,'')
    .replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&nbsp;/g,' ').replace(/&amp;/g,'&');
};
window.qttSetText=function(el,t){
  const e=String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  el.innerHTML=e.replace(/\\*([^*]+)\\*/g,'<em>$1</em>').replace(/\\n/g,'<br>');
};
window.qttFit=function(el){if(!el.hasAttribute('data-fit'))return;el.style.fontSize='';const cs=getComputedStyle(el);
  let s=parseFloat(cs.fontSize),m=s*.42;const mh=cs.maxHeight==='none'?el.clientHeight:parseFloat(cs.maxHeight);
  while((el.scrollHeight>mh+6||el.scrollWidth>el.clientWidth+2)&&s>m){s-=1.5;el.style.fontSize=s+'px'}
};
window.qttWords=function(edits){const p=qttPieces();
  for(const k in (edits||{})){const e=edits[k],el=p[+k];if(!el||el.tagName!==e.t)continue;
    if(typeof e.text==='string')qttSetText(el,e.text);}
};
// a moved piece comes to the front: it, and every layer around it that has a stacking order of its own
window.qttFront=function(el){
  for(let a=el;a&&!(a.classList&&a.classList.contains('post'));a=a.parentElement){const cs=getComputedStyle(a);
    if(a===el||cs.position!=='static'||cs.transform!=='none'||cs.zIndex!=='auto'||parseFloat(cs.opacity)<1){
      if(cs.position==='static')a.style.position='relative';a.style.zIndex='60'}}
};
window.qttMoves=function(edits){const p=qttPieces();
  for(const k in (edits||{})){const e=edits[k],el=p[+k];if(!el||el.tagName!==e.t)continue;
    if(e.tf){el.style.transform=e.tf;qttFront(el)}if(e.hide)el.style.visibility='hidden';}
};
</script>"""


def clean_edits(raw) -> dict:
	"""{format: {piece: {t, tf?, text?, hide?}}} — only what's valid; anything else dropped."""
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
		for k, e in list(pieces.items())[:MAX_PIECES]:
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
			if e.get("hide") in (True, 1, "1", "true"):
				one["hide"] = 1
			if len(one) > 1:
				got[str(int(k))] = one
		if got:
			out[fmt] = got
	return out


def without_text(edits: dict) -> dict:
	"""The same changes without words typed on the design (the design's words were changed another way)."""
	out = {}
	for fmt, pieces in (edits or {}).items():
		kept = {}
		for k, e in pieces.items():
			e = {x: v for x, v in e.items() if x != "text"}
			if len(e) > 1:
				kept[k] = e
		if kept:
			out[fmt] = kept
	return out


def _json(v) -> str:
	return json.dumps(v, ensure_ascii=False).replace("<", "\\u003c")


def script_for(edits: dict | None, fmt: str) -> str:
	"""The page's saved changes for one size (an empty string when there are none)."""
	one = (edits or {}).get(fmt) or {}
	return f"<script>window.qttEdits={_json(one)}</script>" if one else ""


def _data_uri(name: str, data: bytes) -> str:
	"""A picture as a data: address for the editor (photos brought down to 1200 px so the page stays light)."""
	ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
	if ext in ("jpg", "jpeg", "webp") and len(data) > 250_000:
		try:
			from PIL import Image

			im = Image.open(io.BytesIO(data)).convert("RGB")
			im.thumbnail((1200, 1200))
			buf = io.BytesIO()
			im.save(buf, "JPEG", quality=82)
			data, ext = buf.getvalue(), "jpg"
		except Exception:
			pass
	mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml"}.get(ext, "image/png")
	return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def inline_files(page: str, files: dict[str, bytes]) -> str:
	"""The page's pictures (referenced by file name) put inside it, for a page with no file server behind it."""
	for name, data in files.items():
		uri = _data_uri(name, data)
		page = re.sub(r"(?<=[\"'(])" + re.escape(name) + r"(?=[\"')])", uri, page)
	return page


EDITOR_JS = """<script>
(function(){
  const send=m=>{try{QttEditor.postMessage(JSON.stringify(m))}catch(e){console.log(m)}};
  const edits=JSON.parse(JSON.stringify(window.qttSaved||{}));let mv=null,sel=-1;
  const kind=el=>[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())?'text':'picture';
  const keep=(i,el,extra)=>{const e=edits[i]||(edits[i]={t:el.tagName});e.t=el.tagName;Object.assign(e,extra||{});
    if(e.tf)qttFront(el);
    if(e.tf==='')delete e.tf;send({type:'changed'})};
  function select(i){
    const p=qttPieces(),el=p[i];if(!el)return;sel=i;
    if(mv)mv.destroy();
    mv=new Moveable(document.body,{target:el,draggable:true,scalable:true,keepRatio:true,rotatable:true,origin:false,
      throttleScale:0.01,renderDirections:['nw','ne','sw','se'],pinchable:true});
    mv.on('drag',e=>{e.target.style.transform=e.transform}).on('scale',e=>{e.target.style.transform=e.transform})
      .on('rotate',e=>{e.target.style.transform=e.transform})
      .on('dragEnd',e=>keep(i,el,{tf:el.style.transform})).on('scaleEnd',e=>keep(i,el,{tf:el.style.transform}))
      .on('rotateEnd',e=>keep(i,el,{tf:el.style.transform}));
    send({type:'select',piece:i,kind:kind(el),text:kind(el)==='text'?qttText(el):'',hidden:!!(edits[i]&&edits[i].hide)});
  }
  window.qttEditor={
    edits:()=>JSON.stringify(edits),
    select:select,
    none:()=>{if(mv)mv.destroy();mv=null;sel=-1;send({type:'select',piece:-1})},
    text:t=>{const el=qttPieces()[sel];if(!el)return;qttSetText(el,t);qttFit(el);keep(sel,el,{text:t});if(mv)mv.updateRect()},
    size:f=>{const el=qttPieces()[sel];if(!el)return;el.style.transform=(el.style.transform||'')+' scale('+f+')';keep(sel,el,{tf:el.style.transform.trim()});if(mv)mv.updateRect()},
    hide:()=>{const el=qttPieces()[sel];if(!el)return;const h=!(edits[sel]&&edits[sel].hide);el.style.visibility=h?'hidden':'';
      el.style.opacity='';keep(sel,el,{hide:h?1:0});if(!h)delete edits[sel].hide;send({type:'select',piece:sel,kind:kind(el),text:qttText(el),hidden:h})},
    reset:()=>{const el=qttPieces()[sel];if(!el)return;el.style.transform=el.dataset.qttTf||'';el.style.visibility='';
      if(edits[sel]&&typeof edits[sel].text==='string'&&el.dataset.qttHtml!==undefined)el.innerHTML=el.dataset.qttHtml;
      delete edits[sel];send({type:'changed'});select(sel)},
    resetAll:()=>{for(const k in edits)delete edits[k];location.reload()},
  };
  const fit=()=>{const post=document.querySelector('.post');if(!post)return;const k=window.innerWidth/1080;
    post.style.transform='scale('+k+')';post.style.transformOrigin='0 0';
    document.body.style.height=Math.ceil(post.offsetHeight*k)+'px';if(mv)mv.updateRect()};
  const start=()=>{
    fit();window.addEventListener('resize',fit);
    const p=qttPieces();
    p.forEach(el=>{el.dataset.qttHtml=el.innerHTML;el.dataset.qttTf=el.style.transform||'';el.style.cursor='pointer'});
    qttWords(edits);
    for(const k in edits)if(typeof edits[k].text==='string'&&p[+k])qttFit(p[+k]);
    qttMoves(edits);
    for(const k in edits)if(edits[k].hide&&p[+k]){p[+k].style.visibility='visible';p[+k].style.opacity='.35'}
    document.addEventListener('click',ev=>{
      if(ev.target.closest&&ev.target.closest('.moveable-control-box'))return;
      const i=p.findIndex(el=>el===ev.target||el.contains(ev.target));
      if(i>=0)select(i);else window.qttEditor.none();
    },true);
    send({type:'ready',pieces:p.length});
  };
  const wait=()=>window.qttReady&&window.Moveable?start():setTimeout(wait,80);wait();
})();
</script>"""


def editor_page(page: str, files: dict[str, bytes], width: int, edits_for_format: dict | None) -> str:
	"""The design's page for the app's editor: its pictures inside it, the page as wide as the phone, Moveable and the
	editor (messages go to the app through the QttEditor channel). The page's own fitting runs first, unchanged."""
	page = inline_files(page, files)
	# The design is drawn 1080 wide; the editor shrinks it to the phone's width itself (an Android web view doesn't
	# always honour a fixed viewport width), so the page is the phone's width and the post is scaled inside it.
	head = ('<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">'
			"<style>html,body{width:100%!important;height:auto!important;overflow-x:hidden!important;overflow-y:auto!important;"
			"-webkit-user-select:none;user-select:none;touch-action:none}.moveable-control-box{z-index:9999}</style>")
	page = page.replace("</head>", head + "</head>", 1)
	saved = f"<script>window.qttSaved={_json(edits_for_format or {})}</script>"  # the editor applies these itself
	tail = f'{saved}<script src="{MOVEABLE}"></script>{EDITOR_JS}'
	return page.replace("</body>", tail + "</body>", 1)
