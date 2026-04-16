from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db, ReadingProgress
from schemas import ProgressUpdate, ProgressResponse

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/{book_id}", response_model=ProgressResponse)
def get_progress(book_id: int, db: Session = Depends(get_db)):
    p = db.query(ReadingProgress).filter(ReadingProgress.book_id == book_id).first()
    if not p:
        return ProgressResponse(
            book_id=book_id,
            chapter_index=0,
            page_index=0,
            scroll_position=0.0,
            last_read_at=None
        )
    return p


@router.put("/{book_id}", response_model=ProgressResponse)
def update_progress(book_id: int, body: ProgressUpdate, db: Session = Depends(get_db)):
    p = db.query(ReadingProgress).filter(ReadingProgress.book_id == book_id).first()
    if not p:
        p = ReadingProgress(book_id=book_id)
        db.add(p)

    p.chapter_index = body.chapter_index
    p.page_index = body.page_index
    p.scroll_position = body.scroll_position
    p.last_read_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return p
