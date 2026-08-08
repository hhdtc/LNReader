from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db, Book
from schemas import SearchResponse, LinovelibBookResponse
from services.linovelib import search_linovelib, LinovelibError

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search_books(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    query = q.strip()
    local = (
        db.query(Book)
        .filter(
            Book.title.ilike(f"%{query}%")
            | Book.author.ilike(f"%{query}%")
        )
        .order_by(Book.uploaded_at.desc())
        .all()
    )

    linovelib_books = []
    linovelib_total = 0
    linovelib_error = None
    if query:
        try:
            result = search_linovelib(query)
            linovelib_books = [LinovelibBookResponse(**b.__dict__) for b in result.books]
            linovelib_total = result.total
        except LinovelibError as exc:
            linovelib_error = str(exc)

    return SearchResponse(
        query=query,
        local=local,
        linovelib=linovelib_books,
        linovelib_total=linovelib_total,
        linovelib_error=linovelib_error,
    )
