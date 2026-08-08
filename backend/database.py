from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, UniqueConstraint, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lnreader.db")
BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")
AUDIO_DIR = os.getenv("AUDIO_DIR", "./audio")

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
    voicebox_url = Column(String(200), default="http://host.docker.internal")
    voicebox_port = Column(Integer, default=17493)
    voicebox_profile_id = Column(String(200), default="")
    voicebox_language = Column(String(10), default="en")
    voicebox_model_size = Column(String(20), default="1.7B")


class BookAudioJob(Base):
    __tablename__ = "book_audio_jobs"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), default="idle")  # idle/running/done/failed
    chapters_done = Column(Integer, default=0)
    total_chapters = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class ChapterAudio(Base):
    __tablename__ = "chapter_audio"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False)
    audio_path = Column(String(1000), nullable=False)
    duration = Column(Float, default=0.0)
    status = Column(String(20), default="pending")  # pending/done/failed
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("book_id", "chapter_index"),)


class ListeningProgress(Base):
    __tablename__ = "listening_progress"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, nullable=False, unique=True, index=True)
    chapter_index = Column(Integer, default=0)
    position_seconds = Column(Float, default=0.0)
    last_listened_at = Column(DateTime, default=datetime.utcnow)


class BookDownloadJob(Base):
    __tablename__ = "book_download_jobs"

    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(String(20), nullable=False)
    novel_url = Column(String(500), nullable=False)
    title = Column(String(500), default="")
    status = Column(String(20), default="running")  # running/done/failed/cancelled
    chapters_done = Column(Integer, default=0)
    total_chapters = Column(Integer, default=0)
    book_id = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_VOICEBOX_MIGRATIONS = [
    ("view_mode", "ALTER TABLE user_settings ADD COLUMN view_mode VARCHAR(20) DEFAULT 'scroll'"),
    ("voicebox_url", "ALTER TABLE user_settings ADD COLUMN voicebox_url VARCHAR(200) DEFAULT 'http://host.docker.internal'"),
    ("voicebox_port", "ALTER TABLE user_settings ADD COLUMN voicebox_port INTEGER DEFAULT 17493"),
    ("voicebox_profile_id", "ALTER TABLE user_settings ADD COLUMN voicebox_profile_id VARCHAR(200) DEFAULT ''"),
    ("voicebox_language", "ALTER TABLE user_settings ADD COLUMN voicebox_language VARCHAR(10) DEFAULT 'en'"),
    ("voicebox_model_size", "ALTER TABLE user_settings ADD COLUMN voicebox_model_size VARCHAR(20) DEFAULT '1.7B'"),
]


def init_db():
    os.makedirs(BOOKS_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for col, sql in _VOICEBOX_MIGRATIONS:
            try:
                conn.execute(text(f"SELECT {col} FROM user_settings LIMIT 1"))
            except Exception:
                conn.execute(text(sql))
                conn.commit()
        # Cleanup: the linovelib cookie column is no longer used.
        try:
            conn.execute(text("SELECT linovelib_cookie FROM user_settings LIMIT 1"))
            conn.execute(text("ALTER TABLE user_settings DROP COLUMN linovelib_cookie"))
            conn.commit()
        except Exception:
            pass
    db = SessionLocal()
    try:
        settings = db.query(UserSettings).first()
        if not settings:
            db.add(UserSettings(id=1))
            db.commit()
    finally:
        db.close()
