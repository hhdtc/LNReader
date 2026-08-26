"""OPDS router — two surfaces:

- server_router (/opds...): exposes the local library as an OPDS 1.x catalog
  (navigation root, acquisition catalog, search feed, OpenSearch description,
  book file downloads) so external OPDS clients can browse and acquire books.
- client_router (/api/opds...): turns LNreader into an OPDS client — saved
  sources, remote feed browsing (normalized to JSON), and acquisition of
  external books into the local library.
"""
import os
import re
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import Book, OpdsSource, get_db
from schemas import (
    BookResponse,
    OpdsAcquireRequest,
    OpdsFeedResponse,
    OpdsServerInfo,
    OpdsSourceCreate,
    OpdsSourceResponse,
)
from services.ingest import register_book_file, unique_path
from services.opds import (
    ACQUISITION_MIME,
    FEED_MIME,
    build_catalog_feed,
    build_opensearch_xml,
    build_root_feed,
    build_search_feed,
    extract_search_template,
    parse_opds_feed,
)

BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")

USER_AGENT = "LNreader/1.0 (+https://github.com/LNReader; OPDS client)"

server_router = APIRouter(tags=["opds-server"])
client_router = APIRouter(prefix="/api/opds", tags=["opds-client"])


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Only http(s) URLs are supported")


async def _fetch_feed(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30, headers={"user-agent": USER_AGENT}
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Cannot reach OPDS server: {str(exc)[:200]}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OPDS server returned HTTP {resp.status_code}")
    if len(resp.content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Feed too large")
    return resp.content


def _apply_search_template(template: str, query: str) -> str:
    if "{searchTerms}" in template:
        return template.replace("{searchTerms}", quote(query))
    raise HTTPException(
        status_code=400,
        detail="This catalog advertises a search link without a {searchTerms} template.",
    )

async def _resolve_feed_search(feed: OpdsFeedResponse) -> None:
    """If the feed's rel=search link is an OpenSearch description (not an
    inline template), fetch it and substitute the Url template."""
    if not feed.search_url or "{searchTerms}" in feed.search_url:
        return
    try:
        content = await _fetch_feed(feed.search_url)
    except HTTPException:
        feed.search_url = None
        return
    template = extract_search_template(content)
    feed.search_url = template or None


def _resolve_file_extension(url_suffix: str, disposition: str, content_type: str) -> Optional[str]:
    """Pick .epub/.txt from URL path, Content-Disposition, then Content-Type.

    OPDS acquisition links are frequently extensionless (e.g. /download/123);
    Content-Type is the reliable signal in that case.
    """
    if url_suffix in (".epub", ".txt"):
        return url_suffix
    match = re.search(r'filename="?([^";]+)"?', disposition or "")
    if match:
        disp_suffix = Path(match.group(1)).suffix.lower()
        if disp_suffix in (".epub", ".txt"):
            return disp_suffix
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype == "application/epub+zip":
        return ".epub"
    if ctype == "text/plain":
        return ".txt"
    return None


# ========== OPDS server — expose local library ==========

@server_router.get("/opds")
def opds_root(request: Request):
    """Navigation feed — the OPDS entry point."""
    return Response(content=build_root_feed(_base(request)), media_type=FEED_MIME)


@server_router.get("/opds/catalog")
def opds_catalog(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Acquisition feed — all library books, paginated."""
    base = _base(request)
    total = db.query(Book).count()
    books = (
        db.query(Book)
        .order_by(Book.uploaded_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Response(
        content=build_catalog_feed(base, books, total, page, page_size),
        media_type=ACQUISITION_MIME,
    )


@server_router.get("/opds/search")
def opds_search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    """Search acquisition feed over title/author."""
    base = _base(request)
    query = q.strip()
    books = (
        db.query(Book)
        .filter(Book.title.ilike(f"%{query}%") | Book.author.ilike(f"%{query}%"))
        .order_by(Book.uploaded_at.desc())
        .all()
    )
    return Response(
        content=build_search_feed(base, books, query),
        media_type=ACQUISITION_MIME,
    )


@server_router.get("/opds/opensearch.xml")
def opds_opensearch(request: Request):
    return Response(
        content=build_opensearch_xml(_base(request)),
        media_type="application/opensearchdescription+xml",
    )


@server_router.get("/opds/books/{book_id}/file")
def opds_file(book_id: int, db: Session = Depends(get_db)):
    """Acquisition target: the raw .epub/.txt file of a library book."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not os.path.exists(book.file_path):
        raise HTTPException(status_code=404, detail="Book file not found on disk")
    file_mime = "application/epub+zip" if book.file_type == "epub" else "text/plain"
    return FileResponse(book.file_path, media_type=file_mime, filename=os.path.basename(book.file_path))


# ========== OPDS client — browse other catalogs ==========

@client_router.get("/server", response_model=OpdsServerInfo)
def server_info(request: Request):
    """Absolute URL of this instance's OPDS catalog (for sharing)."""
    return OpdsServerInfo(url=f"{_base(request)}/opds")


@client_router.get("/sources", response_model=List[OpdsSourceResponse])
def list_sources(db: Session = Depends(get_db)):
    return db.query(OpdsSource).order_by(OpdsSource.created_at.desc()).all()


@client_router.post("/sources", response_model=OpdsSourceResponse)
def add_source(body: OpdsSourceCreate, db: Session = Depends(get_db)):
    url = body.url.strip()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Source name is required")
    _validate_http_url(url)
    source = OpdsSource(name=name, url=url)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@client_router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(OpdsSource).filter(OpdsSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"message": "Source deleted"}


@client_router.get("/browse", response_model=OpdsFeedResponse)
async def browse_feed(
    url: str = Query(..., min_length=4),
    q: Optional[str] = Query(None, max_length=200),
):
    """Fetch and normalize a remote OPDS feed. With q, resolves the catalog's
    advertised search template: either the passed URL is the template itself
    or the feed's rel="search" link is used."""
    feed_url = url.strip()
    _validate_http_url(feed_url)
    if q and "{searchTerms}" in feed_url:
        feed_url = _apply_search_template(feed_url, q.strip())

    content = await _fetch_feed(feed_url)
    try:
        feed = parse_opds_feed(content, feed_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await _resolve_feed_search(feed)

    if q and "{searchTerms}" not in url:
        if not feed.search_url:
            raise HTTPException(
                status_code=400,
                detail="This catalog does not advertise a search link",
            )
        search_url = _apply_search_template(feed.search_url, q.strip())
        if search_url != feed_url:
            content = await _fetch_feed(search_url)
            try:
                feed = parse_opds_feed(content, search_url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            await _resolve_feed_search(feed)
    return feed


@client_router.post("/acquire", response_model=BookResponse)
async def acquire_book(body: OpdsAcquireRequest, db: Session = Depends(get_db)):
    """Download an OPDS acquisition URL (.epub/.txt) into the library."""
    url = body.url.strip()
    _validate_http_url(url)

    path = urlparse(url).path
    suffix = Path(unquote(path)).suffix.lower()

    if suffix and suffix not in (".epub", ".txt"):
        raise HTTPException(
            status_code=400,
            detail="Only EPUB and TXT files can be imported from OPDS catalogs",
        )

    os.makedirs(BOOKS_DIR, exist_ok=True)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=120, headers={"user-agent": USER_AGENT}
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Remote server returned HTTP {resp.status_code}",
                    )

                # Extensionless acquisition links are common (e.g.
                # /download/123); decide the file type from the URL
                # path, Content-Disposition, then Content-Type.
                ext = _resolve_file_extension(
                    suffix,
                    resp.headers.get("content-disposition", ""),
                    resp.headers.get("content-type", ""),
                )
                if not ext:
                    raise HTTPException(
                        status_code=400,
                        detail="Only EPUB and TXT files can be imported from OPDS catalogs",
                    )

                filename = Path(unquote(path)).name
                safe_name = (
                    "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
                    or f"book_{int(time.time())}"
                )
                if not safe_name.lower().endswith(ext):
                    safe_name += ext
                dest_path = unique_path(BOOKS_DIR, safe_name)

                with open(dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(1024 * 1024):
                        f.write(chunk)
    except HTTPException:
        if "dest_path" in locals() and os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    except Exception as exc:
        if "dest_path" in locals() and os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=502, detail=f"Failed to download: {str(exc)[:200]}")

    book = register_book_file(dest_path)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book
