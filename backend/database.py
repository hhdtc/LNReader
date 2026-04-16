from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jpreader.db")
BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    author = Column(String(500), default="Unknown")
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(10), nullable=False)  # epub or txt
    cover_path = Column(String(1000), nullable=True)
    language = Column(String(10), default="unknown")
    total_chapters = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    chapter_index = Column(Integer, default=0)
    page_index = Column(Integer, default=0)
    scroll_position = Column(Float, default=0.0)
    last_read_at = Column(DateTime, default=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, default=1)
    translation_provider = Column(String(50), default="deepl")
    translation_api_key = Column(String(500), default="")
    translation_target_lang = Column(String(10), default="en")
    bg_color = Column(String(20), default="#0b0b0b")
    font_size = Column(Integer, default=16)
    font_family = Column(String(100), default="Space Grotesk")
    page_width = Column(Integer, default=720)
    view_mode = Column(String(20), default="scroll")
    google_user_email = Column(String(200), default="")
    google_user_name = Column(String(200), default="")
    google_user_picture = Column(String(500), default="")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import pathlib
    os.makedirs(BOOKS_DIR, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # Migrate: add view_mode column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT view_mode FROM user_settings LIMIT 1"))
        except Exception:
            conn.execute(text("ALTER TABLE user_settings ADD COLUMN view_mode VARCHAR(20) DEFAULT 'scroll'"))
            conn.commit()
    db = SessionLocal()
    try:
        settings = db.query(UserSettings).first()
        if not settings:
            db.add(UserSettings(id=1))
            db.commit()
    finally:
        db.close()
