export interface Book {
  id: number;
  title: string;
  author: string;
  file_type: string;
  cover_path: string | null;
  language: string;
  total_chapters: number;
  uploaded_at: string;
}

export interface ChapterContent {
  chapter_index: number;
  chapter_title: string;
  content: string;
  total_chapters: number;
  is_japanese: boolean;
}

export interface ChapterSummary {
  chapter_index: number;
  chapter_title: string;
}

export interface ReadingProgress {
  book_id: number;
  chapter_index: number;
  page_index: number;
  scroll_position: number;
  last_read_at: string | null;
}

export interface UserSettings {
  translation_provider: string;
  translation_api_key: string;
  translation_target_lang: string;
  bg_color: string;
  font_size: number;
  font_family: string;
  page_width: number;
  view_mode: string;
  google_user_email: string;
  google_user_name: string;
  google_user_picture: string;
}

export interface UserInfo {
  email: string;
  name: string;
  picture: string;
  is_authenticated: boolean;
}

export interface TranslationRequest {
  text: string;
  source_lang: string;
  target_lang: string;
  provider: string;
  api_key: string;
}

export interface TranslationResponse {
  translated_text: string;
  provider: string;
}
