from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, ListeningProgress
from schemas import ListeningProgressUpdate, ListeningProgressResponse

router = APIRouter(prefix="/api/listening-progress", tags=["listening"])


@router.get("/{book_id}", response_model=ListeningProgressResponse)
def get_progress(book_id: int, db: Session = Depends(get_db)):
    record = db.query(ListeningProgress).filter(ListeningProgress.book_id == book_id).first()
    if not record:
        return ListeningProgressResponse(
            book_id=book_id,
            chapter_index=0,
            position_seconds=0.0,
            last_listened_at=None,
        )
    return record


@router.put("/{book_id}", response_model=ListeningProgressResponse)
def update_progress(book_id: int, body: ListeningProgressUpdate, db: Session = Depends(get_db)):
    record = db.query(ListeningProgress).filter(ListeningProgress.book_id == book_id).first()
    if not record:
        record = ListeningProgress(book_id=book_id)
        db.add(record)

    record.chapter_index = body.chapter_index
    record.position_seconds = body.position_seconds
    record.last_listened_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record
