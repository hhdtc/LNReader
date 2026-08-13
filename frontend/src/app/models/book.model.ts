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
  voicebox_url: string;
  voicebox_port: number;
  voicebox_profile_id: string;
  voicebox_language: string;
  voicebox_model_size: string;
  tts_language: string;
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

export interface VoiceboxProfile {
  id: string;
  name: string;
  language: string;
  description?: string;
}

export interface AudioJobStatus {
  book_id: number;
  status: string; // idle/running/done/failed
  chapters_done: number;
  total_chapters: number;
  error?: string;
}

export interface ChapterAudioInfo {
  chapter_index: number;
  status: string;
  duration: number;
  has_audio: boolean;
}

export interface AudioStatusResponse {
  job: AudioJobStatus;
  chapters: ChapterAudioInfo[];
}

export interface ListeningProgress {
  book_id: number;
  chapter_index: number;
  position_seconds: number;
  last_listened_at: string | null;
}

export interface LinovelibBook {
  title: string;
  url: string;
  author: string;
  publisher: string;
  cover_url: string;
  status: string;
  rating: string;
  description: string;
  tags: string;
}

export interface SearchResponse {
  query: string;
  local: Book[];
  linovelib: LinovelibBook[];
  linovelib_total: number;
  linovelib_error: string | null;
  linovelib_suggestion: string | null;
}

export interface DownloadJob {
  id: number;
  novel_id: string;
  novel_url: string;
  title: string;
  status: 'running' | 'done' | 'failed' | 'cancelled';
  chapters_done: number;
  total_chapters: number;
  book_id: number | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}
