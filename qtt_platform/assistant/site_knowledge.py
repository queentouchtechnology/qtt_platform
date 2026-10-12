"""
Everything on www.queentouchtech.com, for QTT's WhatsApp receptionist (and
the Hermes company skill): every page's readable text in site_pages.json,
a map of the whole site, and the pages that best match a question.

Pure — no Frappe. Refresh after the website changes (then commit the JSON):

	python -m qtt_platform.assistant.site_knowledge
"""

import json
import math
import os
import re
import urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "site_pages.json")
SITE = "https://www.queentouchtech.com"
MAX_PAGE = 3500  # characters kept per page

# Site map sections, in the order the receptionist sees them.
SECTIONS = [
	("packages", "Packages (ready bundles)"), ("service", "Services"), ("solutions", "Solutions"),
	("what-we-do", "What we do"), ("products", "Our products"), ("industries", "Industries"),
	("case-studies", "Case studies"), ("locations", "Locations we serve"), ("insights", "Articles"),
	("", "Company"),
]

_STOP = set("""a an and are as at be by can do does for from get has have how i in is it me my of on or our please so
that the their them there this to us we what when where which who why will with you your hai hi hello hey sir madam
ok okay thanks thank yes no need want know tell about any some more also qtt queen touch technology""".split())

# ---- building (fetch + extract) --------------------------------------------------

_SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe", "button"}
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "section", "article", "tr", "br", "td", "th", "dt", "dd"}


class _Text(HTMLParser):
	def __init__(self):
		super().__init__()
		self.skip, self.parts, self.title, self.in_title, self.desc = 0, [], "", False, ""

	def handle_starttag(self, tag, attrs):
		a = dict(attrs)
		if tag in _SKIP:
			self.skip += 1
		if tag == "title":
			self.in_title = True
		if tag == "meta" and (a.get("name") or "").lower() == "description":
			self.desc = a.get("content") or ""
		if tag in _BLOCK:
			self.parts.append("\n")
		if tag in ("h1", "h2", "h3") and not self.skip:
			self.parts.append("# " if tag == "h1" else "## ")
		if tag == "li" and not self.skip:
			self.parts.append("- ")

	def handle_endtag(self, tag):
		if tag in _SKIP and self.skip:
			self.skip -= 1
		if tag == "title":
			self.in_title = False
		if tag in _BLOCK:
			self.parts.append("\n")

	def handle_data(self, data):
		if self.in_title:
			self.title += data
		elif not self.skip:
			self.parts.append(data)


def clean_text(text: str) -> str:
	text = re.sub(r"[ \t\r\f\v]+", " ", text)
	out, seen = [], set()
	for line in (l.strip() for l in text.split("\n")):
		if not line or line in ("-", "#", "##"):
			continue
		if line.lower() in seen and len(line) < 120:  # repeated menu / footer bits
			continue
		seen.add(line.lower())
		out.append(line)
	return "\n".join(out)


def page_from_html(url: str, html: str) -> dict:
	p = _Text()
	p.feed(html)
	title = re.sub(r"\s*\|\s*QTT\s*$", "", clean_text(p.title).replace("\n", " "))
	return {"url": url, "title": title, "description": p.desc.strip(), "text": clean_text("".join(p.parts))[:MAX_PAGE]}


def _get(url: str) -> str:
	req = urllib.request.Request(url, headers={"User-Agent": "QTT-knowledge-builder"})
	return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def build(out: str = DATA) -> int:
	urls = re.findall(r"<loc>([^<]+)</loc>", _get(SITE + "/sitemap.xml"))
	pages = []
	for url in urls:
		try:
			pages.append(page_from_html(url.strip(), _get(url.strip())))
		except Exception as e:  # one bad page never stops the rest
			print("skipped", url, e)
	with open(out, "w", encoding="utf-8", newline="\n") as f:
		json.dump(pages, f, ensure_ascii=False, indent=0)
		f.write("\n")
	return len(pages)


# ---- using -----------------------------------------------------------------------

def load_pages() -> list[dict]:
	if not os.path.exists(DATA):
		return []
	with open(DATA, encoding="utf-8") as f:
		return json.load(f)


def section_of(url: str) -> str:
	path = url.replace(SITE, "").strip("/")
	first = path.split("/")[0] if path else ""
	return first if any(first == s for s, _ in SECTIONS) else ""


def link(url: str) -> str:
	return url.replace("https://", "")


def site_index(pages: list[dict]) -> str:
	"""Every page by title, grouped — so the receptionist knows everything QTT offers."""
	groups: dict[str, list[str]] = {}
	for p in pages:
		if any(w in p["url"] for w in ("privacy-policy", "terms-of-service", "data-deletion")):
			continue
		groups.setdefault(section_of(p["url"]), []).append(p["title"].split(" | ")[0].split(" — ")[0].split(" – ")[0].strip())
	lines = []
	for key, label in SECTIONS:
		titles = sorted({t for t in groups.get(key, []) if t})
		if titles:
			lines.append(f"{label}: " + "; ".join(titles))
	return "\n".join(lines)


def _stem(w: str) -> str:
	"""Just enough to match everyday forms: testing / tested / tests → test, websites → website."""
	for end in ("ing", "ed"):
		if len(w) > len(end) + 3 and w.endswith(end):
			return w[: -len(end)]
	return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def _words(text: str) -> list[str]:
	out = []
	for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
		if len(w) < 3 or w in _STOP:
			continue
		out.append(_stem(w))
	return out


def pick_pages(pages: list[dict], query: str, *, k: int = 4, budget: int = 9000) -> list[dict]:
	"""The pages that best answer `query` (title and address count most). A greeting picks nothing."""
	terms = set(_words(query))
	if not terms or not pages:
		return []
	docs = []
	for p in pages:
		head = set(_words(p["title"] + " " + p["url"].replace("-", " ").replace("/", " ") + " " + p.get("description", "")))
		body = _words(p["text"])
		docs.append((p, head, body))
	n = len(docs)
	df = {t: sum(1 for _, head, body in docs if t in head or t in body) for t in terms}
	scored = []
	for p, head, body in docs:
		counts = {}
		for w in body:
			if w in terms:
				counts[w] = counts.get(w, 0) + 1
		score = 0.0
		for t in terms:
			if not df[t]:
				continue
			idf = math.log(1 + n / df[t])
			score += idf * (3.0 * (t in head) + min(counts.get(t, 0), 5) * 0.4)
		if section_of(p["url"]) == "insights":
			score *= 0.5  # articles last: offers and services first
		if score > 0:
			scored.append((score, p))
	scored.sort(key=lambda x: -x[0])
	if not scored:
		return []
	best, out, used = scored[0][0], [], 0
	for score, p in scored:
		if len(out) >= k or score < best * 0.35:
			break
		if used + len(p["text"]) > budget and out:
			continue
		out.append(p)
		used += len(p["text"])
	return out


def pages_text(pages: list[dict]) -> str:
	return "\n\n".join(f"### {p['title']}\n({link(p['url'])})\n{p['text']}" for p in pages)


if __name__ == "__main__":
	print(build(), "pages ->", DATA)
