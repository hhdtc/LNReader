# JPReader — Architecture & Functionality Reference

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Frontend](#3-frontend)
   - [Components](#31-components)
   - [Services](#32-services)
   - [Models & Guards](#33-models--guards)
   - [Routing](#34-routing)
4. [Backend](#4-backend)
   - [Database Models](#41-database-models)
   - [Pydantic Schemas](#42-pydantic-schemas)
   - [API Endpoints](#43-api-endpoints)
   - [Services](#44-services)
5. [TTS Service (Qwen)](#5-tts-service)
6. [Voicebox Chapter-Audio Pipeline](#6-voicebox-chapter-audio-pipeline)
7. [Key Data Flows](#7-key-data-flows)
   - [Book Upload](#71-book-upload)
   - [Chapter Loading](#72-chapter-loading)
   - [Scroll-mode Virtualization](#73-scroll-mode-virtualization)
   - [Pagination](#74-pagination)
   - [Translation](#75-translation)
   - [Japanese Annotation (Furigana)](#76-japanese-annotation-furigana)
   - [Progress Tracking](#77-progress-tracking)
   - [Authentication](#78-authentication)
   - [Voicebox Audio Generation](#79-voicebox-audio-generation)
   - [Listening Progress](#710-listening-progress)
8. [Configuration & Infrastructure](#8-configuration--infrastructure)

---

## 1. Project Overview

JPReader is a self-hosted e-book reader focused on Japanese content. Core features:

- EPUB and plain-text book library management
- Virtual-scroll and paginated reading modes
- Japanese furigana annotation via MeCab morphological analysis
- Multi-provider text translation (DeepL, Google, OpenAI)
- Chapter-by-chapter audio generation via Voicebox (locally-running TTS server)
- Dedicated listening page with resume support and chapter-read sync
- Persistent reading progress
- Google OAuth + local authentication

**Tech stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | Angular 21, Signals, RxJS 7, TypeScript 5.9 |
| Backend | FastAPI 0.111, SQLAlchemy 2, SQLite/PostgreSQL |
| Japanese | fugashi (MeCab), jaconv, unidic-lite |
| TTS | Qwen3-TTS WebUI (Docker + CUDA) |
| Infra | Docker Compose |

---

## 2. Repository Structure

```
JPReader/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── database.py          # SQLAlchemy models + session factory
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth.py          # OAuth + local auth endpoints
│   │   ├── books.py         # Book CRUD + content delivery
│   │   ├── progress.py      # Reading progress endpoints
│   │   ├── translate.py     # Translation proxy endpoint
│   │   ├── settings.py      # User settings endpoints
│   │   └── tts.py           # TTS proxy endpoint
│   │   ├── voicebox.py      # Voicebox chapter-audio endpoints
│   │   └── listening.py     # Listening progress endpoints
│   ├── services/
│   │   ├── book_parser.py   # EPUB/TXT parsing logic
│   │   ├── japanese.py      # Language detection + annotation
│   │   └── voicebox_service.py  # Voicebox API + text split + WAV concat
│   ├── books/               # Uploaded book files (runtime)
│   ├── audio/               # Generated chapter WAV files (runtime)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/app/
│   │   ├── pages/
│   │   │   ├── auth/
│   │   │   │   ├── auth.component.ts
│   │   │   │   └── auth-callback.component.ts
│   │   │   ├── library/library.component.ts
│   │   │   ├── reader/reader.component.ts
│   │   │   ├── settings/settings.component.ts
│   │   │   └── listen/listen.component.ts  # Audio player page
│   │   ├── services/
│   │   │   ├── api.service.ts
│   │   │   ├── auth.service.ts
│   │   │   ├── chapter-cache.service.ts
│   │   │   └── settings.service.ts
│   │   ├── models/book.model.ts
│   │   ├── guards/auth.guard.ts
│   │   ├── app.routes.ts
│   │   ├── app.config.ts
│   │   └── app.ts
│   ├── proxy.conf.json
│   ├── angular.json
│   └── package.json
├── qwen-tts/
│   ├── Dockerfile
│   ├── models/              # TTS model weights
│   └── test.py
└── docker-compose.yml
```

---

## 3. Frontend

### 3.1 Components

#### `AuthComponent` — `/login`

Displays two login options.

| Method | Description |
|--------|-------------|
| `loginLocal()` | Calls `POST /auth/local`, stores JWT in localStorage, redirects to `/library` |
| `loginGoogle()` | Redirects to `/auth/google` to start OAuth flow |

---

#### `AuthCallbackComponent` — `/auth/callback`

Handles the OAuth redirect back from Google.

| Method | Description |
|--------|-------------|
| `ngOnInit()` | Reads `?token=` query param, stores in localStorage, calls `AuthService.loadUser()`, navigates to `/library` |

---

#### `LibraryComponent` — `/library`

Displays all books in a grid.

| Method | Description |
|--------|-------------|
| `loadBooks()` | Calls `ApiService.getBooks()`, populates `books` signal |
| `uploadFile(file)` | Sends file to `ApiService.uploadBook()`, prepends result to list |
| `onDrop(event)` | Handles drag-and-drop file events, delegates to `uploadFile()` |
| `deleteBook(id)` | Calls `ApiService.deleteBook(id)`, removes from list |
| `openBook(id)` | Navigates to `/reader/:id` |
| `getCoverUrl(id)` | Returns `/api/books/{id}/cover` URL |

**State signals:** `books`, `uploading`, `dragOver`

---

#### `ReaderComponent` — `/reader/:id`

The core reading experience. Most complex component in the app.

**Initialization methods:**

| Method | Description |
|--------|-------------|
| `ngOnInit()` | Loads book metadata, progress, chapter index, then loads saved chapter |
| `loadBook(id)` | Fetches book metadata from `ApiService.getBook()` |
| `loadChapterIndex(id)` | Fetches all chapter titles via `ApiService.getChapterIndex()` |
| `loadProgress(id)` | Fetches last-read chapter/page/scroll from `ApiService.getProgress()` |
| `loadChapter(idx)` | Fetches chapter HTML (from cache or API), stores in `chapterContent` signal |

**View mode methods:**

| Method | Description |
|--------|-------------|
| `toggleViewMode()` | Switches between `scroll` and `paginate` modes, saves preference |
| `recalcPages()` | In paginate mode: measures content height in a hidden div and breaks into pages |
| `splitIntoChunks(html)` | In scroll mode: splits HTML children into display chunks (~14 nodes / ~2600 chars) |
| `estimateBlockHeight(html)` | Estimates rendered height of a chunk for virtual scroll positioning |
| `updateVirtualWindow()` | Calculates which chunks are in viewport (+ 900 px overscan) and sets spacer heights |
| `onScroll()` | Triggers `updateVirtualWindow()` and schedules progress save |
| `onResize()` | Re-measures viewport, re-runs pagination or virtual scroll recalc |

**Navigation methods:**

| Method | Description |
|--------|-------------|
| `prevChapter()` | Loads `currentChapterIndex - 1` |
| `nextChapter()` | Loads `currentChapterIndex + 1` |
| `prevPage()` | In paginate mode: decrements page, handles chapter boundary |
| `nextPage()` | In paginate mode: increments page, handles chapter boundary |
| `jumpToChapter(idx)` | Directly loads a chapter by index |

**Feature methods:**

| Method | Description |
|--------|-------------|
| `toggleAnnotate()` | Reloads chapter with `annotate=true/false` query param |
| `translateSelected()` | Sends `selectedText` to `ApiService.translate()`, displays result |
| `startTTS()` | Extracts sentences, loads reference audio, starts buffered synthesis (button hidden in UI) |
| `stopTTS()` | Halts playback, clears audio cache |
| `bufferAhead(idx)` | Pre-fetches TTS audio for sentences `idx` through `idx+2` |
| `fetchAndPlay(idx)` | Requests audio for sentence `idx`, plays it, queues next |
| `scheduleSave()` | Debounces (2 s) `saveProgress()` call |
| `saveProgress()` | PUT to `/api/progress/{bookId}` with current chapter/page/scroll |

**State signals:** `book`, `chapterContent`, `chapterIndex`, `currentChapterIndex`, `pages`, `currentPage`, `viewMode`, `annotate`, `selectedText`, `translatedText`, `ttsActive`, `ttsIndex`, `fontSize`, `fontFamily`, `bgColor`, `pageWidth`

---

#### `SettingsComponent` — `/settings`

Manages translation provider configuration and displays user profile.

| Method | Description |
|--------|-------------|
| `ngOnInit()` | Loads settings via `SettingsService` |
| `save()` | PATCH to `/api/settings` with updated provider, API key, and target language |

---

### 3.2 Services

#### `ApiService`

Centralized HTTP client. All backend communication goes through this service.

| Method | HTTP | Endpoint | Description |
|--------|------|----------|-------------|
| `getUser()` | GET | `/auth/user` | Current authenticated user |
| `loginLocal()` | POST | `/auth/local` | Issue local dev JWT |
| `logout()` | POST | `/auth/logout` | Clear session |
| `getBooks()` | GET | `/api/books` | List all books |
| `uploadBook(file)` | POST | `/api/books` | Upload EPUB/TXT file |
| `getBook(id)` | GET | `/api/books/:id` | Book metadata |
| `getChapterIndex(id)` | GET | `/api/books/:id/chapters` | All chapter titles |
| `getChapter(id, idx, annotate)` | GET | `/api/books/:id/content` | Chapter HTML + metadata |
| `deleteBook(id)` | DELETE | `/api/books/:id` | Delete book + progress |
| `getCoverUrl(id)` | — | — | Returns cover image URL string |
| `getProgress(id)` | GET | `/api/progress/:id` | Reading progress |
| `updateProgress(id, data)` | PUT | `/api/progress/:id` | Save progress |
| `getSettings()` | GET | `/api/settings` | User settings |
| `updateSettings(data)` | PATCH | `/api/settings` | Update settings |
| `translate(req)` | POST | `/api/translate` | Translate text |
| `tts(text, refAudioB64)` | POST | `/api/tts` | Synthesize speech |

---

#### `AuthService`

Manages authentication state using Angular signals.

| Method | Description |
|--------|-------------|
| `init()` | Called on app startup; calls `loadUser()` |
| `loadUser()` | GET `/auth/user`, populates `user` signal |
| `loginLocally()` | POST `/auth/local`, stores token |
| `loginWithGoogle()` | Redirects browser to `/auth/google` |
| `logout()` | POST `/auth/logout`, clears localStorage token |
| `isAuthenticated()` | Returns `true` if `user` signal has a value |
| `getToken()` | Returns JWT from localStorage |

**Signal:** `user: Signal<UserInfo | null>`

---

#### `ChapterCacheService`

LRU cache for fetched chapter HTML (max 5 entries).

| Method | Description |
|--------|-------------|
| `get(bookId, chapterIdx)` | Returns cached `ChapterContent` or `null` |
| `set(bookId, chapterIdx, content)` | Stores content; evicts entry farthest from `chapterIdx` if over limit |
| `clear()` | Empties entire cache |

---

#### `SettingsService`

Wraps user settings in an Angular signal.

| Method | Description |
|--------|-------------|
| `load()` | Fetches settings from API, updates `settings` signal |
| `update(patch)` | Calls `ApiService.updateSettings()`, re-loads signal |

**Signal:** `settings: Signal<SettingsResponse>`

---

### 3.3 Models & Guards

#### `book.model.ts` — Interfaces

| Interface | Fields |
|-----------|--------|
| `Book` | `id`, `title`, `author`, `language`, `total_chapters`, `cover_path`, `uploaded_at` |
| `ChapterContent` | `title`, `content` (HTML), `chapter_index`, `total_chapters` |
| `ChapterSummary` | `index`, `title` |
| `ReadingProgress` | `book_id`, `chapter_index`, `page_index`, `scroll_position` |
| `UserSettings` | `translation_provider`, `translation_api_key`, `translation_target_lang`, `bg_color`, `font_size`, `font_family`, `page_width`, `view_mode` |
| `UserInfo` | `email`, `name`, `picture`, `auth_type` |

#### `auth.guard.ts`

`canActivate()` — checks `AuthService.isAuthenticated()`; redirects to `/login` if not authenticated.

---

### 3.4 Routing

```
/             →  redirect to /library
/login        →  AuthComponent            (public)
/auth/callback →  AuthCallbackComponent  (public)
/library      →  LibraryComponent        (guarded)
/reader/:id   →  ReaderComponent         (guarded)
/settings     →  SettingsComponent       (guarded)
/listen/:id   →  ListenComponent         (guarded)
```

All page components are lazy-loaded. Proxy config forwards `/api/*` and `/auth/*` to `localhost:8000` in development.

---

## 4. Backend

### 4.1 Database Models

#### `Book`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `title` | String | |
| `author` | String | nullable |
| `file_path` | String | absolute path on disk |
| `file_type` | String | `epub` or `txt` |
| `cover_path` | String | nullable, path to extracted cover |
| `language` | String | `ja` or `unknown` |
| `total_chapters` | Integer | |
| `uploaded_at` | DateTime | UTC |

#### `ReadingProgress`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `book_id` | Integer FK → Book | |
| `chapter_index` | Integer | 0-based |
| `page_index` | Integer | paginate mode |
| `scroll_position` | Float | scroll mode |
| `last_read_at` | DateTime | |

#### `UserSettings`

Single-row table (id = 1).

| Column | Type | Notes |
|--------|------|-------|
| `translation_provider` | String | `deepl` / `google` / `openai` |
| `translation_api_key` | String | encrypted at rest in DB |
| `translation_target_lang` | String | e.g. `EN-US` |
| `bg_color` | String | CSS color |
| `font_size` | Integer | px |
| `font_family` | String | |
| `page_width` | Integer | % |
| `view_mode` | String | `scroll` / `paginate` |
| `google_user_email` | String | populated after OAuth |
| `google_user_name` | String | |
| `google_user_picture` | String | |

---

### 4.2 Pydantic Schemas

| Schema | Purpose |
|--------|---------|
| `BookResponse` | Response for book list/detail |
| `ChapterContent` | Response for chapter content (title, HTML, indices) |
| `ChapterSummary` | One entry in chapter index (index + title) |
| `ProgressUpdate` | Request body for PUT /progress |
| `ProgressResponse` | Response from GET /progress |
| `TranslationRequest` | text, source_lang, target_lang, provider, api_key |
| `TranslationResponse` | translated_text |
| `SettingsUpdate` | Partial settings PATCH body |
| `SettingsResponse` | Full settings response |
| `UserInfo` | email, name, picture, auth_type |

---

### 4.3 API Endpoints

#### Auth Router — prefix `/auth`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/local` | Issue JWT for local dev user |
| GET | `/auth/google` | Redirect to Google OAuth consent screen |
| GET | `/auth/callback` | Exchange OAuth code, issue JWT, redirect to frontend |
| GET | `/auth/user` | Return current user info (reads from UserSettings) |
| POST | `/auth/logout` | No-op server side; client drops token |

#### Books Router — prefix `/api/books`

| Method | Path | Query | Description |
|--------|------|-------|-------------|
| GET | `/api/books` | | List all books, newest first |
| POST | `/api/books` | | Upload EPUB/TXT file (multipart) |
| GET | `/api/books/{id}` | | Book metadata |
| DELETE | `/api/books/{id}` | | Delete book file, cover, and progress record |
| GET | `/api/books/{id}/chapters` | | List of `{index, title}` objects |
| GET | `/api/books/{id}/content` | `chapter` (int), `annotate` (bool) | Chapter HTML with optional furigana |
| GET | `/api/books/{id}/cover` | | Binary cover image |
| GET | `/api/books/{id}/asset` | `path` (URL-encoded relative path) | Extract and serve EPUB asset (images, fonts) |

#### Progress Router — prefix `/api/progress`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/progress/{book_id}` | Get progress; returns defaults if no record |
| PUT | `/api/progress/{book_id}` | Upsert progress record |

#### Translate Router

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/translate` | Proxy translation request to DeepL / Google / OpenAI |

#### Settings Router

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Return UserSettings row |
| PATCH | `/api/settings` | Partial update of settings |

#### TTS Router

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tts` | Forward synthesis request to Qwen-TTS container |

#### Misc

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status":"healthy"}` for Docker health check |
| GET | `/` | API info |

---

### 4.4 Services

#### `book_parser.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_epub` | `(file_path) → (title, author, chapters, cover_bytes)` | Uses ebooklib to extract spine items; converts HTML to chapter dicts; rewrites relative asset URLs |
| `parse_txt` | `(file_path) → (title, chapters)` | Detects chapter breaks via regex (`第`, `Chapter`, etc.); falls back to 3000-char chunks |
| `clear_book_cache` | `()` | Clears the LRU parse cache |

The `parse_epub` and `parse_txt` functions are decorated with `@lru_cache` keyed on file path. On `GET /api/books/{id}/content`, the router:
1. Looks up `book.file_path` and `book.file_type`
2. Calls the appropriate parser (cached)
3. Returns the chapter at `chapters[chapter_index]`
4. If `annotate=true`, calls `annotate_japanese(content)` on the HTML

#### `japanese.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `detect_language` | `(text) → str` | Counts CJK chars; returns `"ja"` if >5%, else `"unknown"` |
| `annotate_japanese` | `(html_text) → str` | Parses HTML with BS4; walks text nodes; injects `<ruby>` + span classes |
| `is_japanese_char` | `(char) → bool` | True for hiragana/katakana/kanji ranges |
| `_contains_kanji` | `(text) → bool` | True if any char is in CJK Unified Ideographs block |
| `_wrap_chars_in_spans` | `(text) → str` | Wraps each char in `<span class="hiragana|katakana|kanji|other">` |

Internal annotation pipeline inside `annotate_japanese`:

1. Parse HTML with BeautifulSoup
2. Find all text nodes not inside `<script>`, `<style>`, or `<rt>` tags
3. For each text node:
   - Tokenize with `fugashi.Tagger` (MeCab)
   - For tokens containing kanji: extract reading from MeCab feature, convert katakana → hiragana via `jaconv`, wrap in `<ruby>kanji<rt>reading</rt></ruby>`
   - Wrap remaining chars in typed `<span>` elements
4. Return serialized HTML

---

## 5. TTS Service

Runs as a separate Docker container on port 7860 using Qwen3-TTS-12Hz-1.7B-Base model.

**Endpoint consumed by backend:**
```
POST http://jpreader-tts:7860/qwenapi/v1/voice-clone
Body:
{
  "model_name": "/models/Qwen3-TTS-12Hz-1.7B-Base",
  "text": "sentence to synthesize",
  "ref_audio_base64": "<base64 WAV>",
  "language": null,
  "segment_gen": false
}
Response:
{
  "audio_files_base64": ["<base64 audio>"],
  "info": "..."
}
```

The backend `/api/tts` router strips the `ref_audio_base64` field from the request, forwards to the TTS container, and returns `{ audio_base64: string }` to the frontend.

Reference audio source: the frontend loads `/ref/tts_ref.wav` (served as a static asset) and encodes it as base64 on the first TTS call.

---

## 6. Voicebox Chapter-Audio Pipeline

Voicebox is a separate, locally-running TTS server. JPReader's backend proxies all Voicebox calls — the frontend never contacts Voicebox directly.

### 6.1 Database Tables

#### `BookAudioJob`
One row per book; tracks overall generation state.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `book_id` | Integer | not a FK to avoid cascade issues |
| `status` | String | `idle` / `running` / `done` / `failed` |
| `chapters_done` | Integer | incremented after each chapter |
| `total_chapters` | Integer | |
| `error` | Text | nullable; last error message |
| `started_at` | DateTime | |
| `completed_at` | DateTime | |

#### `ChapterAudio`
One row per generated chapter.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `book_id` | Integer | |
| `chapter_index` | Integer | unique together with book_id |
| `audio_path` | String | absolute path to WAV on disk |
| `duration` | Float | seconds |
| `status` | String | `pending` / `done` / `failed` |
| `created_at` | DateTime | |

#### `ListeningProgress`
One row per book; tracks where the user stopped listening.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `book_id` | Integer | unique |
| `chapter_index` | Integer | |
| `position_seconds` | Float | |
| `last_listened_at` | DateTime | |

### 6.2 Voicebox API (consumed by backend)

| Method | Path | Use |
|--------|------|-----|
| POST | `/models/load` | Load TTS model into GPU |
| GET | `/profiles` | List voice profiles |
| POST | `/generate` | Generate speech → `{id, duration}` |
| GET | `/audio/{id}` | Download WAV bytes |
| DELETE | `/history/{id}` | Clean up after download |

**`/generate` body:** `profile_id`, `text` (≤5000 chars), `language`, `model_size`

### 6.3 Backend Service — `voicebox_service.py`

| Function | Description |
|----------|-------------|
| `get_voicebox_base(url, port)` | Builds base URL string |
| `extract_plain_text(html)` | BeautifulSoup strip → plain text for synthesis |
| `_split_text(text)` | Splits text at paragraph/sentence boundaries into ≤4800 char segments |
| `_concat_wav_bytes(chunks)` | Concatenates WAV byte blobs using Python `wave` module |
| `load_model(base_url)` | POST `/models/load` |
| `list_profiles(base_url)` | GET `/profiles` |
| `generate_chapter_audio(...)` | Split → generate each segment → download → delete history → concatenate → save WAV |

### 6.4 Backend Router — `routers/voicebox.py`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/voicebox/load-model` | Proxy to Voicebox `/models/load` |
| GET | `/api/voicebox/profiles` | Proxy to Voicebox `/profiles` |
| POST | `/api/voicebox/generate/{book_id}` | Start background audio generation |
| GET | `/api/voicebox/status/{book_id}` | Return `AudioStatusResponse` (job + chapter list) |
| GET | `/api/voicebox/audio/{book_id}/{chapter_index}` | Stream WAV file via `FileResponse` |
| DELETE | `/api/voicebox/audio/{book_id}` | Delete all audio + reset job |

**Background task `_run_generation`**: runs in FastAPI `BackgroundTasks`; iterates chapters, calls `generate_chapter_audio`, updates DB, handles failures per-chapter.

### 6.5 Backend Router — `routers/listening.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/listening-progress/{book_id}` | Returns saved position (defaults 0,0) |
| PUT | `/api/listening-progress/{book_id}` | Upserts `ListeningProgress` |

### 6.6 Frontend — Settings (Voicebox section)

New fields saved to `UserSettings`:
- `voicebox_url` (default `http://localhost`)
- `voicebox_port` (default `8000`)
- `voicebox_profile_id` — selected from fetched Voicebox profiles
- `voicebox_language` (`en` / `zh`)
- `voicebox_model_size` (default `1.7B`)

`loadProfiles()` — fetches `GET /api/voicebox/profiles`, populates dropdown.  
`loadModel()` — calls `POST /api/voicebox/load-model`, shows inline status.

### 6.7 Frontend — Library (audio controls per card)

New signals:
- `audioJobs: Signal<Map<number, AudioJobStatus>>` — status per book
- `generatingIds: Signal<Set<number>>` — books with in-flight start request

On `loadBooks()`: fires `getAudioStatus` for every book in parallel via `forkJoin`.

Polling: `setInterval(3s)` while any job is `running`; clears when all done/failed.

Per-card states: `idle` → GENERATE AUDIO button | `running` → progress text + spinner | `done` → LISTEN + delete buttons | `failed` → FAILED + RETRY.

### 6.8 Frontend — ListenComponent (`/listen/:id`)

| Method | Description |
|--------|-------------|
| `ngOnInit()` | Loads book, chapter index, audio status, listening progress in parallel; resumes at saved position |
| `loadAudio(idx, resume)` | Sets `<audio>` src to `/api/voicebox/audio/:id/:idx`, seeks to saved position if resume |
| `togglePlay()` | Play/pause, saves progress on pause |
| `onTimeUpdate()` | Debounced 2s progress save |
| `onEnded()` | Marks chapter as read via `updateProgress()`, auto-advances to next chapter with audio |
| `prevChapter()` / `nextChapter()` | Navigate; preserves playing state |
| `jumpToChapter(idx)` | Click from sidebar; only for chapters with audio |
| `setSpeed(rate)` | Updates `audio.playbackRate` |
| `saveProgress()` | PUT `/api/listening-progress/:id` |
| `formatTime(secs)` | `"m:ss"` format for display |

**Layout:** sticky header (back + book title) | left sidebar (chapter list with audio indicator) | player area (cover, title, progress bar, controls, speed).

---

## 7. Key Data Flows

### 7.1 Book Upload

```
User selects file
  → LibraryComponent.uploadFile(file)
  → ApiService.uploadBook(file)            POST /api/books  (multipart)
  → backend: save to BOOKS_DIR with unique filename
  → book_parser.parse_epub / parse_txt
      - extract title, author, chapters, cover
  → japanese.detect_language(first 5 chapters)
      - counts CJK chars → "ja" | "unknown"
  → create Book row in DB
  → extract cover image (EPUB only) → save to covers/
  → return BookResponse
  → frontend prepends book to grid
```

### 7.2 Chapter Loading

```
User opens book (/reader/:id)
  → ReaderComponent.ngOnInit()
  → parallel:
      loadBook(id)          GET /api/books/:id
      loadChapterIndex(id)  GET /api/books/:id/chapters
      loadProgress(id)      GET /api/progress/:id
  → loadChapter(savedChapterIndex)
      → ChapterCacheService.get(bookId, idx)  (check cache)
      → if miss: ApiService.getChapter(id, idx, annotate)
            GET /api/books/:id/content?chapter=idx&annotate=bool
            → book_parser (cached) → chapters[idx]
            → if annotate: japanese.annotate_japanese(html)
            → rewrite asset URLs in HTML
            → return ChapterContent
      → ChapterCacheService.set(...)
  → if paginate mode: recalcPages()
  → if scroll mode:   splitIntoChunks() + updateVirtualWindow()
  → restore scroll/page from saved progress
  → async prefetch adjacent chapters into cache
```

### 7.3 Scroll-mode Virtualization

```
Chapter HTML
  → splitIntoChunks()
      - walk child nodes; flush at 14 nodes OR 2600 chars
      - each chunk stored as raw HTML string

Per chunk → estimateBlockHeight(html)
  - strip tags, count plaintext chars
  - chars_per_line = containerWidth / (fontSize * 0.6)
  - lines = ceil(chars / chars_per_line)
  - add bonuses: headings (+2 lines), images (+300px), tables (+100px/row)
  - height = lines * (fontSize * 1.6) + padding

On scroll / init → updateVirtualWindow()
  - compute cumulative offsets
  - find first visible chunk: offset + height > scrollY - 900
  - find last visible chunk:  offset < scrollY + viewportHeight + 900
  - render only [first..last] range
  - set top spacer = cumulative height before first
  - set bottom spacer = cumulative height after last

After render → measure actual heights → update estimates
```

### 7.4 Pagination

```
recalcPages()
  1. Create hidden off-screen div with same CSS as reader
     (font, width, padding, line-height)
  2. Reset div content; start page 1 accumulator
  3. For each child node of chapter HTML:
       - append node clone to hidden div
       - if div.scrollHeight > viewportHeight:
           - remove last node; save current HTML as page N
           - start new page with this node
  4. Save last partial page
  5. Store all pages in `pages` signal
  6. Navigate to saved pageIndex (from progress) or page 0

User presses → / next button:
  currentPage++
  if currentPage >= pages.length and more chapters: nextChapter()

User presses ← / prev button:
  if currentPage > 0: currentPage--
  else if more chapters before: prevChapter() → jump to last page
```

### 7.5 Translation

```
User selects text in reader
  → window selection event → selectedText signal updates

User clicks TRANSLATE
  → ReaderComponent.translateSelected()
  → ApiService.translate({
        text: selectedText,
        source_lang: book.language === 'ja' ? 'ja' : undefined,
        target_lang: settings.translation_target_lang,
        provider: settings.translation_provider,
        api_key: settings.translation_api_key
    })
  → POST /api/translate
  → backend routes by provider:

    DeepL:
      - key ends in ':fx' → api-free.deepl.com, else api.deepl.com
      - POST /v2/translate  {text, source_lang, target_lang, auth_key}
      - return translations[0].text

    Google:
      - POST translation.googleapis.com/language/translate/v2
      - {q, source, target, key}
      - return data.translations[0].translatedText

    OpenAI:
      - POST api.openai.com/v1/chat/completions
      - model: gpt-4o-mini
      - system: "Translate to {target_lang}. Return only the translation."
      - return choices[0].message.content

  → TranslationResponse {translated_text}
  → frontend displays in translation panel
```

### 7.6 Japanese Annotation (Furigana)

```
User clicks 日 toggle (annotate = true)
  → loadChapter(idx) with annotate=true
  → GET /api/books/:id/content?chapter=idx&annotate=true

backend japanese.annotate_japanese(html):
  → BS4 parse HTML
  → walk all text nodes (skip script/style/rt tags)
  → for each text node:
       fugashi.Tagger() tokenizes into morphemes
       for each token:
         if token contains kanji:
           reading = token.feature.kana  (katakana from MeCab)
           reading = jaconv.kata2hira(reading)  (→ hiragana)
           emit <ruby>{surface}<rt>{reading}</rt></ruby>
         else:
           _wrap_chars_in_spans(surface)
           each char → <span class="hiragana|katakana|other">{char}</span>
  → return modified HTML

frontend CSS:
  .kanji    { color: #e06c75 }  (example)
  .hiragana { color: #98c379 }
  .katakana { color: #61afef }
```

### 7.7 Progress Tracking

```
Triggers: scroll event, page change, chapter change

ReaderComponent.scheduleSave():
  → clear existing debounce timer
  → setTimeout(saveProgress, 2000)

saveProgress():
  → ApiService.updateProgress(bookId, {
        chapter_index: currentChapterIndex,
        page_index:    currentPage,         // paginate mode
        scroll_position: window.scrollY     // scroll mode
    })
  → PUT /api/progress/{bookId}
  → upsert ReadingProgress row

On next open:
  → loadProgress() → GET /api/progress/{bookId}
  → restore chapter, then:
      scroll mode:   window.scrollTo(0, scroll_position)
      paginate mode: navigate to page_index
```

### 7.8 Authentication

**Local (dev):**
```
POST /auth/local
  → create JWT: { sub: "local", email: "local@localhost" }
  → return { token }
  → frontend stores in localStorage
  → subsequent requests: Authorization: Bearer <token>
```

**Google OAuth:**
```
GET /auth/google
  → redirect to accounts.google.com/o/oauth2/auth
      ?client_id=...&redirect_uri=BACKEND_URL/auth/callback
      &scope=openid email profile

User authorizes → Google redirects to:
GET /auth/callback?code=...
  → exchange code for Google tokens via token endpoint
  → fetch user info from googleapis.com/oauth2/v2/userinfo
  → store email/name/picture in UserSettings row
  → create JWT: { sub: email }
  → redirect to FRONTEND_URL/auth/callback?token=...

AuthCallbackComponent.ngOnInit():
  → read ?token= from URL
  → localStorage.setItem('token', token)
  → AuthService.loadUser()
  → navigate to /library
```

---

### 7.9 Voicebox Audio Generation

```
User clicks GENERATE AUDIO on a book card
  → LibraryComponent.generateAudio(book)
  → ApiService.startAudioGeneration(bookId)   POST /api/voicebox/generate/:id
  → backend: guard (no profile set? → 400), guard (already running? → 409)
  → create/reset BookAudioJob (status=running)
  → BackgroundTasks.add_task(_run_generation, book_id, SessionLocal)
  → return AudioJobStatus {status: 'running', chapters_done: 0}

_run_generation (background thread):
  for each chapter 0..N-1:
    → book_parser.parse_epub/txt → chapters[idx]
    → voicebox_service.extract_plain_text(html)
    → voicebox_service.generate_chapter_audio():
        split text into ≤4800 char segments
        for each segment:
          POST voicebox/generate → {id, duration}
          GET  voicebox/audio/{id} → WAV bytes
          DELETE voicebox/history/{id}
        concatenate WAV files using Python wave module
        save to ./audio/{book_id}/chapter_{idx}.wav
    → update ChapterAudio (status=done, path, duration)
    → increment BookAudioJob.chapters_done

Frontend polls GET /api/voicebox/status/:id every 3s
  → updates book card UI (progress counter)
  → stops polling when status = done/failed
```

### 7.10 Listening Progress

```
User opens /listen/:id
  → parallel:
      getBook(id)
      getChapterIndex(id)
      getAudioStatus(id)   → list of ChapterAudioInfo
      getListeningProgress(id) → {chapter_index, position_seconds}
  → loadAudio(savedChapterIndex, resume=true)
      → audio.src = /api/voicebox/audio/:id/:chapterIdx
      → on loadedmetadata: audio.currentTime = position_seconds

User plays / seeks / skips chapters
  → onTimeUpdate → debounced 2s → PUT /api/listening-progress/:id
  → onEnded:
      → PUT /api/progress/:id  (mark chapter read)
      → if next chapter has audio: auto-advance + play
      → else: stay on completed chapter

User leaves page (ngOnDestroy)
  → saveProgress() called immediately
```

---

## 8. Configuration & Infrastructure

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `JWT_SECRET` | — | Secret for JWT signing |
| `FRONTEND_URL` | `http://localhost:4200` | CORS origin + OAuth redirect base |
| `BACKEND_URL` | `http://localhost:8000` | OAuth callback URI base |
| `BOOKS_DIR` | `./books` | Directory for uploaded book files |
| `AUDIO_DIR` | `./audio` | Directory for generated chapter WAV files |
| `DATABASE_URL` | `sqlite:///./jpreader.db` | SQLAlchemy connection string |

### Docker Compose Services

| Service | Port | Build | Notes |
|---------|------|-------|-------|
| `backend` | 8000 | `./backend` | Health check: `GET /health` |
| `frontend` | 4800 | `./frontend` | Depends on backend healthy |
| `tts` | 7860 | `./qwen-tts` | Requires `nvidia` runtime (GPU) |

**Volumes:** `books_data` (EPUB files), `db_data` (SQLite)

### CORS

Backend allows:
- `FRONTEND_URL` environment variable value
- `http://localhost:4200` (development)

### Backend Middleware

1. `CORSMiddleware` — whitelist origin, allow credentials, all methods/headers
2. `StaticFiles` — mounts `/covers` for book cover images

### Backend Auto-migration

On startup, `init_db()` in `database.py`:
- Creates all tables from SQLAlchemy metadata
- If `UserSettings` table exists but is missing `view_mode` column → `ALTER TABLE` to add it
