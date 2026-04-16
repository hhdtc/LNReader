import os
import shutil
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from database import get_db, Book, ReadingProgress
from schemas import BookResponse, ChapterContent, ChapterSummary
from services.book_parser import parse_epub, parse_txt, clear_book_cache
from services.japanese import detect_language, annotate_japanese
from dotenv import load_dotenv

load_dotenv()

BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")
router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=List[BookResponse])
def list_books(db: Session = Depends(get_db)):
    return db.query(Book).order_by(Book.uploaded_at.desc()).all()


@router.post("", response_model=BookResponse)
async def upload_book(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".epub", ".txt"):
        raise HTTPException(status_code=400, detail="Only .epub and .txt files are supported")

    os.makedirs(BOOKS_DIR, exist_ok=True)

    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ").strip()
    dest_path = os.path.join(BOOKS_DIR, safe_name)

    # Ensure unique filename
    counter = 1
    base, ext = os.path.splitext(dest_path)
    while os.path.exists(dest_path):
        dest_path = f"{base}_{counter}{ext}"
        counter += 1

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    cover_path = None
    if suffix == ".epub":
        try:
            title, author, chapters, cover_bytes = parse_epub(dest_path)
            total_chapters = len(chapters)
            if cover_bytes:
                cover_file = dest_path.replace(ext, "_cover.jpg")
                with open(cover_file, "wb") as cf:
                    cf.write(cover_bytes)
                cover_path = os.path.basename(cover_file)
        except Exception as e:
            title = Path(file.filename).stem
            author = "Unknown"
            total_chapters = 0
    else:
        try:
            title, chapters = parse_txt(dest_path)
            total_chapters = len(chapters)
            author = "Unknown"
        except Exception:
            title = Path(file.filename).stem
            total_chapters = 0

    # Detect language by sampling multiple chapters (first chapter is often front matter)
    language = "unknown"
    if total_chapters > 0:
        sample = ""
        for ch in chapters[:5]:
            sample += ch.get("content", "")
            if len(sample) >= 2000:
                break
        language = detect_language(sample)

    book = Book(
        title=title,
        author=author,
        file_path=dest_path,
        file_type=suffix.lstrip("."),
        cover_path=cover_path,
        language=language,
        total_chapters=total_chapters,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.get("/{book_id}/chapters", response_model=List[ChapterSummary])
def get_chapter_index(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not os.path.exists(book.file_path):
        raise HTTPException(status_code=404, detail="Book file not found on disk")

    try:
        if book.file_type == "epub":
            _, _, chapters_list, _ = parse_epub(book.file_path)
            chapter_summaries = [
                ChapterSummary(chapter_index=i, chapter_title=(ch.get("title") or f"Chapter {i + 1}"))
                for i, ch in enumerate(chapters_list)
            ]
        else:
            _, chapters = parse_txt(book.file_path)
            chapter_summaries = [
                ChapterSummary(chapter_index=i, chapter_title=(ch.get("title") or f"Chapter {i + 1}"))
                for i, ch in enumerate(chapters)
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading chapter index: {str(e)}")

    return chapter_summaries


@router.get("/{book_id}/cover")
def get_cover(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book or not book.cover_path:
        raise HTTPException(status_code=404, detail="No cover available")
    cover_full_path = os.path.join(BOOKS_DIR, book.cover_path)
    if not os.path.exists(cover_full_path):
        raise HTTPException(status_code=404, detail="Cover file not found")
    return FileResponse(cover_full_path, media_type="image/jpeg")


@router.get("/{book_id}/content", response_model=ChapterContent)
def get_chapter(
    book_id: int,
    chapter: int = 0,
    annotate: bool = False,
    db: Session = Depends(get_db)
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not os.path.exists(book.file_path):
        raise HTTPException(status_code=404, detail="Book file not found on disk")

    try:
        if book.file_type == "epub":
            _, _, chapters_list, _ = parse_epub(book.file_path)
            total = len(chapters_list)

            if chapter >= total or chapter < 0:
                raise HTTPException(status_code=404, detail="Chapter not found")

            ch = chapters_list[chapter]
            content = ch["content"]
            chapter_title = ch["title"]

            if book.total_chapters != total:
                book.total_chapters = total
                db.commit()

        else:  # txt
            _, chapters = parse_txt(book.file_path)
            if chapter >= len(chapters) or chapter < 0:
                raise HTTPException(status_code=404, detail="Chapter not found")
            ch = chapters[chapter]
            content = ch["content"].replace("\n", "<br>")
            chapter_title = ch["title"]
            total = len(chapters)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading book: {str(e)}")

    is_jp = book.language == "ja"
    if annotate and is_jp:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, "html.parser")
        for text_node in soup.find_all(string=True):
            if text_node.parent.name not in ["script", "style"]:
                annotated = annotate_japanese(str(text_node))
                text_node.replace_with(BeautifulSoup(annotated, "html.parser"))
        content = str(soup)

    return ChapterContent(
        chapter_index=chapter,
        chapter_title=chapter_title,
        content=content,
        total_chapters=total,
        is_japanese=is_jp,
    )


@router.delete("/{book_id}")
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if os.path.exists(book.file_path):
        os.remove(book.file_path)
        clear_book_cache()
    if book.cover_path:
        cover_full = os.path.join(BOOKS_DIR, book.cover_path)
        if os.path.exists(cover_full):
            os.remove(cover_full)

    db.query(ReadingProgress).filter(ReadingProgress.book_id == book_id).delete()
    db.delete(book)
    db.commit()
    return {"message": "Book deleted"}
