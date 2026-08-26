import os
import re
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, Book, BookDownloadJob, SessionLocal
from schemas import DownloadStartRequest, DownloadJobResponse
from services.bilinovel_downloader import BilinovelDownloader, BilinovelError
from services.ingest import register_book_file

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")

_NOVEL_ID_RE = re.compile(r"(?:linovelib|bilinovel)\.com/(?:novel|download)/(\d+)")

_job_threads: dict[int, threading.Thread] = {}


def _job_response(job: BookDownloadJob) -> DownloadJobResponse:
    return DownloadJobResponse(
        id=job.id,
        novel_id=job.novel_id,
        novel_url=job.novel_url,
        title=job.title or "",
        status=job.status,
        chapters_done=job.chapters_done or 0,
        total_chapters=job.total_chapters or 0,
        book_id=job.book_id,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


# ---------- background worker ----------


def _run_download(job_id: int):
    db = SessionLocal()
    dest_path = None
    try:
        job = db.query(BookDownloadJob).filter(BookDownloadJob.id == job_id).first()
        if not job:
            return

        downloader = BilinovelDownloader()
        meta = downloader.fetch_novel(job.novel_id)
        job.title = meta.title
        db.commit()

        volumes = downloader.fetch_catalog(job.novel_id)
        all_chapters = [c for v in volumes for c in v.chapters]
        job.total_chapters = len(all_chapters)
        job.chapters_done = 0
        db.commit()

        chapter_htmls = []
        image_urls = []
        flat_pos = 0
        for vol in volumes:
            if job.status == "cancelled":
                break
            for chapter in vol.chapters:
                db.refresh(job)
                if job.status == "cancelled":
                    break
                if chapter.href:
                    url = chapter.href
                else:
                    url = downloader.resolve_chapter_url(volumes, flat_pos)
                title, html, imgs = downloader.fetch_chapter(url, vol.title)
                chapter_htmls.append((title or chapter.title, html))
                image_urls.extend(imgs)
                flat_pos += 1
                job.chapters_done = flat_pos
                db.commit()

        if job.status == "cancelled":
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        # Download images (dedup by URL).
        unique_images = list(dict.fromkeys(image_urls))
        images = []
        for src in unique_images:
            if job.status == "cancelled":
                break
            try:
                images.append((src, downloader.download_image(src)))
            except BilinovelError:
                continue  # skip broken images rather than failing the job

        if job.status == "cancelled":
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        # Build EPUB and register it.
        safe_base = "".join(c for c in meta.title if c.isalnum() or c in "._- ").strip() or "novel"
        dest_path = os.path.join(BOOKS_DIR, f"{safe_base}_{meta.novel_id}.epub")
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(
                BOOKS_DIR, f"{safe_base}_{meta.novel_id}_{counter}.epub"
            )
            counter += 1

        os.makedirs(BOOKS_DIR, exist_ok=True)
        from services.bilinovel_downloader import build_epub

        build_epub(meta, volumes, chapter_htmls, images, dest_path)

        book = register_book_file(dest_path)
        db.add(book)
        db.commit()
        db.refresh(book)
        job.book_id = book.id
        job.status = "done"
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        job = db.query(BookDownloadJob).filter(BookDownloadJob.id == job_id).first()
        if job and job.status != "cancelled":
            job.status = "failed"
            job.error = str(e)[:500]
            job.completed_at = datetime.utcnow()
            db.commit()
            # build_epub may have left a truncated file at dest_path.
            if dest_path and os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
    finally:
        _job_threads.pop(job_id, None)
        db.close()


# ---------- endpoints ----------

@router.post("", response_model=DownloadJobResponse)
def start_download(body: DownloadStartRequest, db: Session = Depends(get_db)):
    match = _NOVEL_ID_RE.search(body.url.strip())
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL — expected a linovelib/bilinovel novel page.",
        )
    novel_id = match.group(1)

    job = BookDownloadJob(novel_id=novel_id, novel_url=body.url.strip(), status="running")
    db.add(job)
    db.commit()
    db.refresh(job)

    thread = threading.Thread(target=_run_download, args=(job.id,), daemon=True)
    _job_threads[job.id] = thread
    thread.start()
    return _job_response(job)


@router.get("/{job_id}", response_model=DownloadJobResponse)
def get_download(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BookDownloadJob).filter(BookDownloadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return _job_response(job)


@router.post("/{job_id}/cancel", response_model=DownloadJobResponse)
def cancel_download(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BookDownloadJob).filter(BookDownloadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    if job.status == "running":
        job.status = "cancelled"
        db.commit()
    return _job_response(job)
