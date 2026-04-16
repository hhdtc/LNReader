from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class BookBase(BaseModel):
    title: str
    author: str = "Unknown"
    language: str = "unknown"


class BookCreate(BookBase):
    file_path: str
    file_type: str
    cover_path: Optional[str] = None
    total_chapters: int = 0


class BookResponse(BookBase):
    id: int
    file_type: str
    cover_path: Optional[str] = None
    total_chapters: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class ChapterContent(BaseModel):
    chapter_index: int
    chapter_title: str
    content: str
    total_chapters: int
    is_japanese: bool = False


class ChapterSummary(BaseModel):
    chapter_index: int
    chapter_title: str


class ProgressUpdate(BaseModel):
    chapter_index: int
    page_index: int = 0
    scroll_position: float = 0.0


class ProgressResponse(BaseModel):
    book_id: int
    chapter_index: int
    page_index: int
    scroll_position: float
    last_read_at: Optional[datetime]

    class Config:
        from_attributes = True


class TranslationRequest(BaseModel):
    text: str
    source_lang: str = "ja"
    target_lang: str = "en"
    provider: str = "deepl"
    api_key: str


class TranslationResponse(BaseModel):
    translated_text: str
    provider: str


class SettingsUpdate(BaseModel):
    translation_provider: Optional[str] = None
    translation_api_key: Optional[str] = None
    translation_target_lang: Optional[str] = None
    bg_color: Optional[str] = None
    font_size: Optional[int] = None
    font_family: Optional[str] = None
    page_width: Optional[int] = None
    view_mode: Optional[str] = None


class SettingsResponse(BaseModel):
    translation_provider: str
    translation_api_key: str
    translation_target_lang: str
    bg_color: str
    font_size: int
    font_family: str
    page_width: int
    view_mode: str
    google_user_email: str
    google_user_name: str
    google_user_picture: str

    class Config:
        from_attributes = True


class UserInfo(BaseModel):
    email: str
    name: str
    picture: str
    is_authenticated: bool = True
