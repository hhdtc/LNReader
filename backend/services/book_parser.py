import os
import re
import codecs
from functools import lru_cache
from typing import List, Tuple, Optional
from pathlib import Path


_LEGACY_ENCODINGS = ("cp932", "euc-jp", "gb18030", "big5")


def decode_text(data: bytes) -> str:
    """Decode text bytes with BOM and common-legacy-encoding detection.

    Japanese TXT from web sources is usually Shift-JIS (cp932) and Chinese
    TXT often GBK/GB18030 — both decode into garbage under plain UTF-8.
    Detection order: BOM (UTF-8/UTF-16/UTF-32) → strict UTF-8 → legacy
    codecs scored by presence of kana (strong Japanese-language signal);
    the wrong encoding yields little-to-no kana here (SJIS as GBK → all-CJK
    garbage, GBK as cp932 → usually a decode error).
    """
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig")
    if data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE):
        return data.decode("utf-32")
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    sample = data[: 256 * 1024]
    best_encoding = None
    best_kana = -1
    decoded = {}
    for encoding in _LEGACY_ENCODINGS:
        try:
            text = sample.decode(encoding)
        except UnicodeDecodeError:
            continue
        kana = sum(
            1 for ch in text
            if "\u3041" <= ch <= "\u30ff" or "\uff66" <= ch <= "\uff9d"
        )
        decoded[encoding] = kana
        if kana > best_kana:
            best_kana = kana
            best_encoding = encoding
    if best_encoding:
        if best_kana == 0 and "gb18030" in decoded:
            # No candidate produced kana: this is almost certainly Chinese
            # (GBK) text — Japanese prose of any length contains kana, while
            # GBK bytes often decode cleanly (but meaninglessly) via cp932.
            best_encoding = "gb18030"
        return data.decode(best_encoding)
    return data.decode("utf-8", errors="replace")


@lru_cache(maxsize=8)
def parse_txt(file_path: str) -> Tuple[str, List[dict]]:
    """Parse a TXT file into chapters (splits by double newlines or heading patterns)."""
    with open(file_path, "rb") as f:
        text = decode_text(f.read())

    title = Path(file_path).stem

    # Try to detect chapter breaks: 第X章/Chapter headings, plus aozora-style
    # HTML anchors (<a name="1">, common in z-library/librivox exports).
    chapter_pattern = re.compile(
        r"^[ \t\u3000]*(?:第[一二三四五六七八九十百千\d]+[章話节節回]|Chapter\s*\d+|CHAPTER\s*\d+|第\d+章|<a name=\"?\d+\"?>)",
        re.MULTILINE
    )
    matches = list(chapter_pattern.finditer(text))

    if len(matches) >= 2:
        chapters = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chapter_text = text[start:end].strip()
            chapter_title = match.group().strip()
            if chapter_title.startswith("<a "):
                # Read the visible heading on the anchor line (e.g. "<a name=\"1\">１").
                first_line = chapter_text.split("\n", 1)[0]
                visible = first_line.replace(chapter_title, "", 1).strip()
                chapter_title = visible or f"Chapter {i + 1}"
            chapters.append({"title": chapter_title, "content": chapter_text})
    else:
        # No chapter markers: split into chunks of ~3000 chars
        chunk_size = 3000
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        if not chunks:
            chunks = [text]
        chapters = [{"title": f"Page {i+1}", "content": chunk} for i, chunk in enumerate(chunks)]

    return title, chapters


@lru_cache(maxsize=8)
def parse_epub(file_path: str) -> Tuple[str, str, List[dict], Optional[bytes]]:
    """
    Parse EPUB file. Returns (title, author, chapters, cover_bytes).
    chapters = [{"title": str, "content": str (HTML or plain)}]
    """
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(file_path)

    title = book.title or Path(file_path).stem
    author = "Unknown"
    creators = book.get_metadata("DC", "creator")
    if creators:
        author = creators[0][0]

    cover_bytes = None
    try:
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_COVER:
                cover_bytes = item.get_content()
                break
        if not cover_bytes:
            for item in book.get_items():
                if "cover" in (item.get_name() or "").lower() and item.get_type() == ebooklib.ITEM_IMAGE:
                    cover_bytes = item.get_content()
                    break
    except Exception:
        pass

    chapters = []
    spine_ids = [sid for sid, _ in book.spine]

    HTML_TYPES = {ebooklib.ITEM_DOCUMENT, ebooklib.ITEM_UNKNOWN}
    HTML_EXTENSIONS = {".html", ".xhtml", ".htm"}

    for item_id in spine_ids:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        item_name = item.get_name() or ""
        item_type = item.get_type()
        # ebooklib assigns ITEM_UNKNOWN to files with media-type="text/html";
        # accept those alongside ITEM_DOCUMENT (application/xhtml+xml)
        if item_type not in HTML_TYPES:
            continue
        if item_type == ebooklib.ITEM_UNKNOWN:
            ext = os.path.splitext(item_name)[1].lower()
            if ext not in HTML_EXTENSIONS:
                continue
        try:
            raw_html = decode_text(item.get_content())
        except Exception:
            continue

        soup = BeautifulSoup(raw_html, "html.parser")

        # Extract chapter title
        chapter_title = ""
        heading = soup.find(["h1", "h2", "h3", "title"])
        if heading:
            chapter_title = heading.get_text(strip=True)

        # Extract and clean text content
        # Remove script and style tags
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()

        # Convert to structured HTML for the reader
        body = soup.find("body")
        if body:
            content_html = str(body.decode_contents())
        else:
            content_html = str(soup)

        if content_html.strip():
            chapters.append({
                "title": chapter_title or f"Chapter {len(chapters) + 1}",
                "content": content_html,
                "source_name": item_name,
            })

    return title, author, chapters, cover_bytes


def clear_book_cache():
    """Clear the LRU caches for both parsers (e.g. after a book is deleted)."""
    parse_epub.cache_clear()
    parse_txt.cache_clear()
