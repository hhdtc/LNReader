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
    voicebox_url: Optional[str] = None
    voicebox_port: Optional[int] = None
    voicebox_profile_id: Optional[str] = None
    voicebox_language: Optional[str] = None
    voicebox_model_size: Optional[str] = None
    tts_language: Optional[str] = None


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
    voicebox_url: str
    voicebox_port: int
    voicebox_profile_id: str
    voicebox_language: str
    voicebox_model_size: str
    tts_language: str

    class Config:
        from_attributes = True


class UserInfo(BaseModel):
    email: str
    name: str
    picture: str
    is_authenticated: bool = True


# --- Audio / Voicebox schemas ---

class AudioJobStatus(BaseModel):
    book_id: int
    status: str  # idle/running/done/failed
    chapters_done: int
    total_chapters: int
    error: Optional[str] = None

    class Config:
        from_attributes = True


class ChapterAudioInfo(BaseModel):
    chapter_index: int
    status: str  # pending/done/failed
    duration: float
    has_audio: bool

    class Config:
        from_attributes = True


class AudioStatusResponse(BaseModel):
    job: AudioJobStatus
    chapters: List[ChapterAudioInfo]


class VoiceboxProfile(BaseModel):
    id: str
    name: str
    language: str = "en"
    description: Optional[str] = None


# --- Listening progress schemas ---

class ListeningProgressUpdate(BaseModel):
    chapter_index: int
    position_seconds: float


class ListeningProgressResponse(BaseModel):
    book_id: int
    chapter_index: int
    position_seconds: float
    last_listened_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Search schemas ---

class LinovelibBookResponse(BaseModel):
    title: str
    url: str
    author: str = ""
    publisher: str = ""
    cover_url: str = ""
    status: str = ""
    rating: str = ""
    description: str = ""
    tags: str = ""


class SearchResponse(BaseModel):
    query: str
    local: List[BookResponse] = []
    linovelib: List[LinovelibBookResponse] = []
    linovelib_total: int = 0
    linovelib_error: Optional[str] = None


# --- Download schemas ---

class DownloadStartRequest(BaseModel):
    url: str


class DownloadJobResponse(BaseModel):
    id: int
    novel_id: str
    novel_url: str
    title: str = ""
    status: str
    chapters_done: int = 0
    total_chapters: int = 0
    book_id: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
