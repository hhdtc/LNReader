import os
import shutil
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db, UserSettings, Book, BookAudioJob, ChapterAudio, AUDIO_DIR
from schemas import AudioJobStatus, AudioStatusResponse, ChapterAudioInfo, VoiceboxProfile
from services import voicebox_service
from services.book_parser import parse_epub, parse_txt

router = APIRouter(prefix="/api/voicebox", tags=["voicebox"])


def _get_settings(db: Session) -> UserSettings:
    s = db.query(UserSettings).first()
    if not s:
        raise HTTPException(500, "Settings not initialised")
    return s


def _build_base_url(s: UserSettings) -> str:
    return voicebox_service.get_voicebox_base(s.voicebox_url, s.voicebox_port)


def _job_response(job: BookAudioJob) -> AudioJobStatus:
    return AudioJobStatus(
        book_id=job.book_id,
        status=job.status,
        chapters_done=job.chapters_done,
        total_chapters=job.total_chapters,
        error=job.error,
    )


# ---------- background task ----------

def _run_generation(book_id: int, db_session_factory):
    db = db_session_factory()
    try:
        settings = db.query(UserSettings).first()
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book or not settings:
            return

        base_url = voicebox_service.get_voicebox_base(settings.voicebox_url, settings.voicebox_port)

        if book.file_type == "epub":
            _, _, chapters, _ = parse_epub(book.file_path)
        else:
            _, chapters = parse_txt(book.file_path)

        job = db.query(BookAudioJob).filter(BookAudioJob.book_id == book_id).first()
        job.total_chapters = len(chapters)
        job.chapters_done = 0
        db.commit()

        import asyncio

        async def _generate_all():
            for idx, chapter in enumerate(chapters):
                db.refresh(job)
                if job.status == "cancelled":
                    break

                existing = (
                    db.query(ChapterAudio)
                    .filter(ChapterAudio.book_id == book_id, ChapterAudio.chapter_index == idx)
                    .first()
                )
                if not existing:
                    existing = ChapterAudio(book_id=book_id, chapter_index=idx, audio_path="", status="pending")
                    db.add(existing)
                    db.commit()
                    db.refresh(existing)

                if existing and existing.status == "done":
                    job.chapters_done += 1
                    db.commit()
                    continue

                plain = voicebox_service.extract_plain_text(chapter.get("content", ""))
                if not plain.strip():
                    existing.status = "done"
                    existing.duration = 0.0
                    existing.audio_path = ""
                    db.commit()
                    job.chapters_done += 1
                    db.commit()
                    continue

                try:
                    path, duration = await voicebox_service.generate_chapter_audio(
                        book_id=book_id,
                        chapter_index=idx,
                        plain_text=plain,
                        profile_id=settings.voicebox_profile_id,
                        language=settings.voicebox_language,
                        model_size=settings.voicebox_model_size,
                        base_url=base_url,
                        audio_dir=AUDIO_DIR,
                    )
                    existing.audio_path = path
                    existing.duration = duration
                    existing.status = "done"
                except Exception as e:
                    existing.status = "failed"
                    existing.audio_path = ""
                    job.error = str(e)

                db.commit()
                job.chapters_done += 1
                db.commit()

        asyncio.run(_generate_all())

        db.refresh(job)
        if job.status != "cancelled":
            job.status = "done"
            job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        job = db.query(BookAudioJob).filter(BookAudioJob.book_id == book_id).first()
        if job:
            job.status = "failed"
            job.error = str(e)
            db.commit()
    finally:
        db.close()


# ---------- endpoints ----------

@router.post("/load-model")
async def load_model(
    url: str = Query(None),
    port: int = Query(None),
    db: Session = Depends(get_db),
):
    s = _get_settings(db)
    base_url = voicebox_service.get_voicebox_base(url or s.voicebox_url, port if port is not None else s.voicebox_port)
    try:
        result = await voicebox_service.load_model(base_url)
        return {"status": "ok", "detail": result}
    except Exception as e:
        raise HTTPException(502, f"Voicebox unreachable: {e}")


@router.get("/profiles")
async def list_profiles(
    url: str = Query(None),
    port: int = Query(None),
    db: Session = Depends(get_db),
):
    s = _get_settings(db)
    base_url = voicebox_service.get_voicebox_base(url or s.voicebox_url, port if port is not None else s.voicebox_port)
    try:
        profiles = await voicebox_service.list_profiles(base_url)
        return profiles
    except Exception as e:
        raise HTTPException(502, f"Voicebox unreachable: {e}")


@router.post("/generate/{book_id}", response_model=AudioJobStatus)
def start_generation(book_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    s = _get_settings(db)
    if not s.voicebox_profile_id:
        raise HTTPException(400, "Voicebox profile not configured — set it in Settings")

    job = db.query(BookAudioJob).filter(BookAudioJob.book_id == book_id).first()
    if job and job.status == "running":
        raise HTTPException(409, "Generation already running for this book")

    if not job:
        job = BookAudioJob(book_id=book_id)
        db.add(job)

    job.status = "running"
    job.chapters_done = 0
    job.total_chapters = book.total_chapters
    job.error = None
    job.started_at = datetime.utcnow()
    job.completed_at = None
    db.commit()
    db.refresh(job)

    from database import SessionLocal
    background_tasks.add_task(_run_generation, book_id, SessionLocal)

    return _job_response(job)


@router.post("/cancel/{book_id}", response_model=AudioJobStatus)
def cancel_generation(book_id: int, db: Session = Depends(get_db)):
    job = db.query(BookAudioJob).filter(BookAudioJob.book_id == book_id).first()
    if not job or job.status != "running":
        raise HTTPException(400, "No running job for this book")
    job.status = "cancelled"
    db.commit()
    db.refresh(job)
    return _job_response(job)


@router.get("/status/{book_id}", response_model=AudioStatusResponse)
def get_status(book_id: int, db: Session = Depends(get_db)):
    job = db.query(BookAudioJob).filter(BookAudioJob.book_id == book_id).first()
    if not job:
        job_resp = AudioJobStatus(book_id=book_id, status="idle", chapters_done=0, total_chapters=0)
    else:
        job_resp = _job_response(job)

    chapters_db = (
        db.query(ChapterAudio)
        .filter(ChapterAudio.book_id == book_id)
        .order_by(ChapterAudio.chapter_index)
        .all()
    )
    chapters_info = [
        ChapterAudioInfo(
            chapter_index=c.chapter_index,
            status=c.status,
            duration=c.duration,
            has_audio=c.status == "done" and bool(c.audio_path) and os.path.exists(c.audio_path),
        )
        for c in chapters_db
    ]

    return AudioStatusResponse(job=job_resp, chapters=chapters_info)


@router.get("/audio/{book_id}/{chapter_index}")
def get_audio(book_id: int, chapter_index: int, db: Session = Depends(get_db)):
    record = (
        db.query(ChapterAudio)
        .filter(ChapterAudio.book_id == book_id, ChapterAudio.chapter_index == chapter_index)
        .first()
    )
    if not record or not record.audio_path or not os.path.exists(record.audio_path):
        raise HTTPException(404, "Audio not found")
    return FileResponse(record.audio_path, media_type="audio/wav")


@router.delete("/audio/{book_id}")
def delete_audio(book_id: int, db: Session = Depends(get_db)):
    db.query(ChapterAudio).filter(ChapterAudio.book_id == book_id).delete()

    job = db.query(BookAudioJob).filter(BookAudioJob.book_id == book_id).first()
    if job:
        job.status = "idle"
        job.chapters_done = 0
        job.error = None
        job.started_at = None
        job.completed_at = None

    db.commit()

    book_audio_dir = os.path.join(AUDIO_DIR, str(book_id))
    if os.path.exists(book_audio_dir):
        shutil.rmtree(book_audio_dir)

    return {"status": "deleted"}
