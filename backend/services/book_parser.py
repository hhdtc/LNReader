import os
import re
from functools import lru_cache
from typing import List, Tuple, Optional
from pathlib import Path


@lru_cache(maxsize=8)
def parse_txt(file_path: str) -> Tuple[str, List[dict]]:
    """Parse a TXT file into chapters (splits by double newlines or heading patterns)."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    title = Path(file_path).stem

    # Try to detect chapter breaks
    chapter_pattern = re.compile(
        r"^(第[一二三四五六七八九十百千\d]+[章話节節回]|Chapter\s*\d+|CHAPTER\s*\d+|第\d+章)",
        re.MULTILINE
    )
    matches = list(chapter_pattern.finditer(text))

    if len(matches) >= 2:
        chapters = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chapter_text = text[start:end].strip()
            chapter_title = match.group()
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
        item_type = item.get_type()
        # ebooklib assigns ITEM_UNKNOWN to files with media-type="text/html";
        # accept those alongside ITEM_DOCUMENT (application/xhtml+xml)
        if item_type not in HTML_TYPES:
            continue
        if item_type == ebooklib.ITEM_UNKNOWN:
            ext = os.path.splitext(item.get_name() or "")[1].lower()
            if ext not in HTML_EXTENSIONS:
                continue
        try:
            raw_html = item.get_content().decode("utf-8", errors="replace")
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
                "content": content_html
            })

    return title, author, chapters, cover_bytes


def clear_book_cache():
    """Clear the LRU caches for both parsers (e.g. after a book is deleted)."""
    parse_epub.cache_clear()
    parse_txt.cache_clear()
