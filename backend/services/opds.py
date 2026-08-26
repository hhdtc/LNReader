"""OPDS support: Atom feed generation (server side) and feed parsing (client side).

Server side builds OPDS 1.x feeds — a navigation root, a paginated
acquisition catalog, a search feed and an OpenSearch description — over the
local books table. Client side parses any remote OPDS feed into a normalized
JSON model for the frontend browser.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from database import Book

ATOM_NS = "http://www.w3.org/2005/Atom"
OPDS_CATALOG_NS = "http://opds-spec.org/2010/catalog"
OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"
DC_NS = "http://purl.org/dc/elements/1.1/"

ACQUISITION_REL = "http://opds-spec.org/acquisition/open-access"
IMAGE_REL = "http://opds-spec.org/image"
THUMBNAIL_REL = "http://opds-spec.org/image/thumbnail"

FEED_MIME = "application/atom+xml;profile=opds-catalog"
ACQUISITION_MIME = "application/atom+xml;profile=opds-catalog;type=acquisition"

EBOOK_TYPES = {"application/epub+zip", "text/plain"}
COVER_RELS = {IMAGE_REL, THUMBNAIL_REL, "http://opds-spec.org/cover", "cover", "thumbnail", "image"}
SUBSECTION_RELS = {"subsection", "http://opds-spec.org/subsection"}


# ---------- feed building (server) ----------

def _q(tag: str, ns: str = ATOM_NS) -> str:
    return f"{{{ns}}}{tag}"


def _sub(parent, tag: str, text: Optional[str] = None, attrs: Optional[Dict[str, str]] = None, ns: str = ATOM_NS):
    el = ET.SubElement(parent, _q(tag, ns))
    if text is not None:
        el.text = text
    for k, v in (attrs or {}).items():
        el.set(k, v)
    return el


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialize(root) -> bytes:
    ET.register_namespace("", ATOM_NS)
    ET.register_namespace("opds", OPDS_CATALOG_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("opensearch", OPENSEARCH_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _new_feed(title: str, subtitle: str, base_url: str) -> ET.Element:
    feed = ET.Element(_q("feed"))
    _sub(feed, "id", f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, base_url + '/opds')}")
    _sub(feed, "title", title)
    if subtitle:
        _sub(feed, "subtitle", subtitle)
    _sub(feed, "updated", _now())
    author = _sub(feed, "author")
    _sub(author, "name", "LNreader")
    return feed


def _book_entry(feed: ET.Element, book: Book, base_url: str) -> None:
    entry = _sub(feed, "entry")
    _sub(entry, "id", f"urn:lnreader:book:{book.id}")
    _sub(entry, "title", book.title)
    if book.author and book.author != "Unknown":
        author = _sub(entry, "author")
        _sub(author, "name", book.author)
    if book.language and book.language != "unknown":
        _sub(entry, "language", book.language)
    if book.uploaded_at:
        uploaded = book.uploaded_at.replace(tzinfo=timezone.utc)
        _sub(entry, "updated", uploaded.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if book.cover_path:
        cover = f"{base_url}/api/books/{book.id}/cover"
        _sub(entry, "link", attrs={"rel": IMAGE_REL, "type": "image/jpeg", "href": cover})
        _sub(entry, "link", attrs={"rel": THUMBNAIL_REL, "type": "image/jpeg", "href": cover})
    file_mime = "application/epub+zip" if book.file_type == "epub" else "text/plain"
    _sub(entry, "link", attrs={"rel": ACQUISITION_REL, "type": file_mime, "href": f"{base_url}/opds/books/{book.id}/file"})


def build_root_feed(base_url: str) -> bytes:
    feed = _new_feed("LNreader", "Personal ebook catalog", base_url)
    _sub(feed, "link", attrs={"rel": "self", "type": FEED_MIME, "href": f"{base_url}/opds"})
    _sub(feed, "link", attrs={"rel": "start", "type": FEED_MIME, "href": f"{base_url}/opds"})
    _sub(feed, "link", attrs={"rel": "search", "type": "application/opensearchdescription+xml", "href": f"{base_url}/opds/opensearch.xml"})

    entry = _sub(feed, "entry")
    _sub(entry, "id", "urn:lnreader:library")
    _sub(entry, "title", "Library")
    _sub(entry, "updated", _now())
    _sub(entry, "link", attrs={"rel": "subsection", "type": ACQUISITION_MIME, "href": f"{base_url}/opds/catalog"})
    return _serialize(feed)


def build_catalog_feed(base_url: str, books: List[Book], total: int, page: int, page_size: int) -> bytes:
    feed = _new_feed("LNreader Library", "All books", base_url)
    self_href = f"{base_url}/opds/catalog?page={page}"
    _sub(feed, "link", attrs={"rel": "self", "type": ACQUISITION_MIME, "href": self_href})
    _sub(feed, "link", attrs={"rel": "search", "type": "application/opensearchdescription+xml", "href": f"{base_url}/opds/opensearch.xml"})
    _sub(feed, "totalResults", str(total), ns=OPENSEARCH_NS)
    for book in books:
        _book_entry(feed, book, base_url)
    if page * page_size < total:
        _sub(feed, "link", attrs={"rel": "next", "type": ACQUISITION_MIME, "href": f"{base_url}/opds/catalog?page={page + 1}"})
    return _serialize(feed)


def build_search_feed(base_url: str, books: List[Book], query: str) -> bytes:
    feed = _new_feed(f"Search: {query}", f"Results for \"{query}\"", base_url)
    _sub(feed, "link", attrs={"rel": "self", "type": ACQUISITION_MIME, "href": f"{base_url}/opds/search?q={query}"})
    _sub(feed, "totalResults", str(len(books)), ns=OPENSEARCH_NS)
    for book in books:
        _book_entry(feed, book, base_url)
    return _serialize(feed)


def build_opensearch_xml(base_url: str) -> bytes:
    root = ET.Element("OpenSearchDescription")
    ET.SubElement(root, "ShortName").text = "LNreader"
    ET.SubElement(root, "Description").text = "Search LNreader's ebook catalog"
    ET.SubElement(root, "InputEncoding").text = "UTF-8"
    ET.SubElement(root, "OutputEncoding").text = "UTF-8"
    ET.SubElement(
        root,
        "Url",
        {"type": ACQUISITION_MIME, "template": f"{base_url}/opds/search?q={{searchTerms}}"},
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ---------- feed parsing (client) ----------

def _localname(tag: str) -> str:
    return tag.split("}")[-1]


def _text(el, path: str, ns: str = ATOM_NS) -> str:
    node = el
    for part in path.split("/"):
        try:
            node = node.find(_q(part, ns))
        except AttributeError:  # parent was None
            return ""
        if node is None:
            return ""
    return (node.text or "").strip()


def _links(el) -> List[Tuple[str, str]]:
    """All atom:link descendants as (rel, href) pairs."""
    out = []
    for link in el.findall(_q("link")):
        out.append(((link.get("rel") or ""), (link.get("href") or ""), (link.get("type") or "")))
    return out


def _is_acquisition(rel: str, mime: str) -> bool:
    if rel.startswith("http://opds-spec.org/acquisition/"):
        return True
    # Lenient fallback: some feeds omit the acquisition rel on the download link.
    if not rel and mime in EBOOK_TYPES:
        return True
    return False

def extract_search_template(content: bytes) -> Optional[str]:
    """Pull the Url template out of an OpenSearch description document."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    if _localname(root.tag) != "OpenSearchDescription":
        return None
    for el in root.iter():
        if _localname(el.tag) == "Url":
            template = el.get("template") or ""
            if "{searchTerms}" in template:
                return template
    return None


def parse_opds_feed(content: bytes, feed_url: str):
    """Parse a remote OPDS feed into an OpdsFeedResponse (imported lazily to
    avoid a schema dependency loop at module load)."""
    from schemas import OpdsEntry, OpdsFeedResponse

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("Not a valid Atom/OPDS XML feed") from exc

    if _localname(root.tag) != "feed":
        raise ValueError("Not an Atom feed (missing <feed> element)")

    feed = OpdsFeedResponse(url=feed_url)
    feed.title = _text(root, "title") or "Untitled feed"
    feed.subtitle = _text(root, "subtitle")
    feed.updated = _text(root, "updated")

    total = _text(root, "totalResults", ns=OPENSEARCH_NS)
    if total.isdigit():
        feed.total_results = int(total)

    for rel, href, _mime in _links(root):
        if rel == "next":
            feed.next_url = urljoin(feed_url, href)
        elif rel == "search":
            feed.search_url = urljoin(feed_url, href)

    for entry_el in root.findall(_q("entry")):
        entry = OpdsEntry(title=_text(entry_el, "title"))
        entry.id = _text(entry_el, "id")
        entry.author = _text(entry_el, "author/name")
        entry.summary = _text(entry_el, "summary")
        entry.language = _text(entry_el, "language") or _text(entry_el, "language", ns=DC_NS)
        entry.updated = _text(entry_el, "updated")
        for rel, href, mime in _links(entry_el):
            if rel in COVER_RELS and not entry.cover_url:
                entry.cover_url = urljoin(feed_url, href)
            if _is_acquisition(rel, mime) and not entry.acquisition_url:
                entry.acquisition_url = urljoin(feed_url, href)
                entry.acquisition_type = mime
            if rel in SUBSECTION_RELS and not entry.subsection_url:
                entry.subsection_url = urljoin(feed_url, href)
        feed.entries.append(entry)

    return feed
