"""
Office Pulse Files — the words inside a file, for search (PROJ-0016 B), pure (tests/test_files.py): PDF (pypdf), Word /
Excel / PowerPoint and OpenDocument (their XML, read straight from the zip — no extra library), text and CSV.
Never raises: a file it can't read just has no words.
"""

import io
import re
import zipfile
from html import unescape

MAX_TEXT = 200_000  # characters kept per file
MAX_PAGES = 60


def _xml_text(xml: bytes) -> str:
	t = xml.decode("utf-8", "ignore")
	t = re.sub(r"</(?:w:p|a:p|text:p|text:h|row|si)>", "\n", t)  # paragraphs, rows, shared strings: a new line
	t = re.sub(r"<(?:w:tab|text:tab)\s*/>", " ", t)
	t = re.sub(r"<[^>]+>", " ", t)
	return re.sub(r"[ \t]+", " ", unescape(t))


def _zip_text(data: bytes, ext: str) -> str:
	with zipfile.ZipFile(io.BytesIO(data)) as z:
		names = z.namelist()
		if ext in ("docx",):
			parts = [n for n in names if re.fullmatch(r"word/(document|header\d*|footer\d*|footnotes)\.xml", n)]
		elif ext in ("xlsx",):
			parts = ["xl/sharedStrings.xml"] if "xl/sharedStrings.xml" in names else []
			parts += sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
		elif ext in ("pptx",):
			parts = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[-1]).group()))
		else:  # odt / ods / odp
			parts = ["content.xml"] if "content.xml" in names else []
		out, size = [], 0
		for n in parts:
			if size > MAX_TEXT:
				break
			text = _xml_text(z.read(n))
			if ext == "xlsx" and n.startswith("xl/worksheets/"):
				text = re.sub(r"\s+", " ", text)  # numbers in cells
			out.append(text)
			size += len(text)
		return "\n".join(out)


def _pdf_text(data: bytes) -> str:
	from pypdf import PdfReader

	r = PdfReader(io.BytesIO(data))
	out, size = [], 0
	for page in r.pages[:MAX_PAGES]:
		t = page.extract_text() or ""
		out.append(t)
		size += len(t)
		if size > MAX_TEXT:
			break
	return "\n".join(out)


def text_of(name: str, data: bytes) -> str:
	"""The words in a file (empty when there are none or it can't be read)."""
	ext = str(name or "").rsplit(".", 1)[-1].lower() if "." in str(name or "") else ""
	try:
		if ext == "pdf":
			t = _pdf_text(data)
		elif ext in ("docx", "xlsx", "pptx", "odt", "ods", "odp"):
			t = _zip_text(data, ext)
		elif ext in ("txt", "csv", "md", "json", "xml", "html", "htm", "log"):
			t = data[: MAX_TEXT * 2].decode("utf-8", "ignore")
			if ext in ("html", "htm", "xml"):
				t = unescape(re.sub(r"<[^>]+>", " ", t))
		else:
			return ""
	except Exception:
		return ""
	t = re.sub(r"[ \t\r\f\v]+", " ", t)
	t = re.sub(r"\n\s*\n+", "\n", t).strip()
	return t[:MAX_TEXT]


def snippet(text: str, words: list[str], width: int = 160) -> str:
	"""A short piece of the text around the first word found."""
	low = (text or "").lower()
	at = min((low.find(w.lower()) for w in words if w and low.find(w.lower()) >= 0), default=-1)
	if at < 0:
		return ""
	start = max(0, at - width // 3)
	piece = re.sub(r"\s+", " ", text[start:start + width]).strip()
	return ("…" if start else "") + piece + ("…" if start + width < len(text) else "")


def search_words(q: str) -> list[str]:
	"""What to look for: every word (2+ letters), at most 6."""
	return [w for w in re.findall(r"[^\s\"'`,;()]+", str(q or "").lower()) if len(w) >= 2][:6]
