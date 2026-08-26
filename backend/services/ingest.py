"""Shared library ingestion: turn a saved .epub/.txt file into a Book row.

Used by direct upload, the bilinovel downloader, and OPDS acquisition so all
three paths extract metadata (title/author/cover/language/chapters) and write
the derived cover file identically.
"""
import os
from pathlib import Path

from database import Book
from services.book_parser import parse_epub, parse_txt
from services.japanese import detect_language


def register_book_file(path: str) -> Book:
    """Parse a saved .epub/.txt file and return a Book row (not yet committed).

    On parse failure the title falls back to the file stem, matching the
    upload endpoint's tolerance — a broken file still lands in the library.
    """
    suffix = Path(path).suffix.lower()
    if suffix not in (".epub", ".txt"):
        raise ValueError(f"Unsupported file type: {suffix}")

    title = Path(path).stem
    author = "Unknown"
    total_chapters = 0
    cover_path = None
    chapters = []

    try:
        if suffix == ".epub":
            title, author, chapters, cover_bytes = parse_epub(path)
            total_chapters = len(chapters)
            if cover_bytes:
                cover_file = str(Path(path).with_suffix("")) + "_cover.jpg"
                with open(cover_file, "wb") as cf:
                    cf.write(cover_bytes)
                cover_path = os.path.basename(cover_file)
        else:
            title, chapters = parse_txt(path)
            total_chapters = len(chapters)
    except Exception:
        pass

    # Detect language by sampling multiple chapters (first is often front matter).
    language = "unknown"
    if total_chapters > 0:
        sample = ""
        for ch in chapters[:5]:
            sample += ch.get("content", "")
            if len(sample) >= 2000:
                break
        language = detect_language(sample)

    return Book(
        title=title,
        author=author,
        file_path=path,
        file_type=suffix.lstrip("."),
        cover_path=cover_path,
        language=language,
        total_chapters=total_chapters,
    )


def unique_path(directory: str, filename: str) -> str:
    """Return directory/filename, suffixing _1, _2... until it does not exist."""
    dest = os.path.join(directory, filename)
    counter = 1
    base, ext = os.path.splitext(dest)
    while os.path.exists(dest):
        dest = f"{base}_{counter}{ext}"
        counter += 1
    return dest
