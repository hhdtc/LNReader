# LNreader — Architecture & Functionality Reference

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
5. [On-demand TTS Service](#5-on-demand-tts-service-omnivoice--indextts-25)
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
   - [Search (local + bilinovel.com)](#711-search-local--bilinovelcom)
   - [Bilinovel Download (→ EPUB → library)](#712-bilinovel-download--epub--library)
   - [Task Center](#713-task-center-library-page)
8. [Configuration & Infrastructure](#8-configuration--infrastructure)
9. [OPDS (Open Publication Distribution System)](#9-opds-open-publication-distribution-system)

---

## 1. Project Overview

LNreader is a self-hosted e-book reader focused on Japanese content. Core features:

- EPUB and plain-text book library management
- Virtual-scroll and paginated reading modes
- Japanese furigana annotation via MeCab morphological analysis
- Multi-provider text translation (DeepL, Google, OpenAI)
- Unified search across the local library and bilinovel.com (mirror of linovelib.com)
- One-click novel download from bilinovel.com → EPUB assembly → auto-registered into the library (background job with progress + cancel)
- Chapter-by-chapter audio generation via Voicebox (locally-running TTS server)
- On-demand TTS via OmniVoice / IndexTTS-2.5 containers (voice cloning with reference audio)
- Dedicated listening page with resume support and chapter-read sync
- Task center UI on the library page — collapsible panel listing download & audio tasks with progress bars and cancel/retry/dismiss actions
- Persistent reading progress
- Google OAuth + local authentication

**Tech stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | Angular 21, Signals, RxJS 7, TypeScript 5.9 |
| Backend | FastAPI 0.111, SQLAlchemy 2, SQLite/PostgreSQL |
| Japanese | fugashi (MeCab), jaconv, unidic-lite |
| TTS | OmniVoice / IndexTTS-2.5 (Docker containers, optional GPU) |
| Scraping | curl_cffi (Chrome TLS impersonation), BeautifulSoup |
| Infra | Docker Compose, nginx |

---

## 2. Repository Structure

```
LNreader/
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
│   │   ├── tts.py           # On-demand TTS proxy (OmniVoice/IndexTTS)
│   │   ├── voicebox.py      # Voicebox chapter-audio endpoints
│   │   ├── listening.py     # Listening progress endpoints
│   │   ├── search.py        # Local + bilinovel.com search
│   │   └── downloads.py     # Bilinovel → EPUB background download jobs
│   ├── services/
│   │   ├── book_parser.py   # EPUB/TXT parsing logic
│   │   ├── japanese.py      # Language detection + annotation
│   │   ├── voicebox_service.py  # Voicebox API + text split + WAV concat
│   │   ├── linovelib.py         # Bilinovel search (Jieqi guard dance)
│   │   └── bilinovel_downloader.py  # Novel scraper + EPUB builder
│   ├── books/               # Uploaded book files (runtime)
│   ├── audio/               # Generated chapter WAV files (runtime)
│   ├── tests/               # pytest tests (epub build, chapterlog, linovelib)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/app/
│   │   ├── pages/
│   │   │   ├── auth/
│   │   │   │   ├── auth.component.ts
│   │   │   │   └── auth-callback.component.ts
│   │   │   ├── library/library.component.ts   # Grid + search + download + task center
│   │   │   ├── reader/reader.component.ts
│   │   │   ├── settings/settings.component.ts
│   │   │   └── listen/listen.component.ts      # Audio player page
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
├── omnivoice-tts/           # OmniVoice TTS container (default, GPU; Dockerfile.cpu variant)
├── indextts-tts/            # IndexTTS-2.5 TTS container (alternative)
├── qwen-tts/                # Legacy Qwen TTS container (deprecated, commented out)
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

Displays all books in a grid, plus a unified search bar (local library + bilinovel.com), per-book audio controls, and a bottom-right collapsible **task center**.

**Book management methods:**

| Method | Description |
|--------|-------------|
| `loadBooks()` | Calls `ApiService.getBooks()`, populates `books` signal, then fetches audio status for every book in parallel |
| `uploadFile(file)` | Sends file to `ApiService.uploadBook()`, prepends result to list |
| `onDrop(event)` | Handles drag-and-drop file events, delegates to `uploadFile()` |
| `deleteBook(id)` | Calls `ApiService.deleteBook(id)` (+ deletes audio), removes from list |
| `openBook(id)` | Navigates to `/reader/:id` |
| `getCoverUrl(id)` | Returns `/api/books/{id}/cover` URL |

**Search methods (local + linovelib):**

| Method | Description |
|--------|-------------|
| `onSearchInput(value)` | Debounced (500 ms) search input → `doSearch()` |
| `doSearch()` | Calls `ApiService.searchBooks(q)` → `GET /api/search?q=`, populates `searchResults` signal |
| `clearSearch()` | Clears query and results, back to library grid |
| `openLinovelib(book)` | Opens the novel page on bilinovel.com in a new tab |

**Download methods (bilinovel → EPUB):**

| Method | Description |
|--------|-------------|
| `downloadNovel(book, event)` | Delegates to `startDownloadForUrl(book.url)` → `POST /api/downloads` |
| `startDownloadForUrl(url)` | Starts a download job, stores it in `downloadJobs` map (keyed by novel URL), starts 3 s polling |
| `startDownloadPolling()` | `interval(3000)` + `switchMap` polls all running jobs via `getDownloadStatus()`; refreshes the grid when a job completes |
| `getDownloadJob(book)` / `isDownloadStarting(book)` | Lookups for the search-result card UI |
| `cancelJob(book, event)` / `cancelDownloadJob(job)` | `POST /api/downloads/{id}/cancel` |
| `openDownloadedBook(book)` | Navigates to `/reader/:id` when the downloaded book is registered |

**Audio methods (per book card):**

| Method | Description |
|--------|-------------|
| `loadAllAudioStatuses(bookIds)` | `forkJoin` of `getAudioStatus(id)` for every book; fills `audioJobs` map |
| `startPollingIfNeeded()` / `pollRunningJobs()` | 3 s interval while any audio job is `running` |
| `generateAudio(book, event)` / `startAudioGeneration(book)` | `POST /api/voicebox/generate/{id}` |
| `stopGeneration(book, event)` / `cancelAudioTask(bookId)` | `POST /api/voicebox/cancel/{id}` |
| `deleteAudio(book)` | `DELETE /api/voicebox/audio/{id}` |
| `openListen(book)` | Navigates to `/listen/:id` |

**Task center methods (bottom-right collapsible panel):**

| Method | Description |
|--------|-------------|
| `tasks` (computed) | Merges `downloadJobs` + `audioJobs` (skips `idle` audio jobs and dismissed entries) into a unified `TaskItem[]` with `progress` (0..1) and `detail` (`12 / 620 CH`) |
| `runningCount` (computed) | Number of tasks with status `running`; shown as a badge on the FAB |
| `toggleTaskCenter()` | Expands/collapses the panel (`taskCenterOpen` signal) |
| `cancelTask(task)` | Cancels a running download or audio job |
| `retryTask(task)` | Restarts a failed download / failed or cancelled audio job |
| `dismissTask(task)` | Removes a finished task from the center (audio dismissal is a view-only flag so book cards keep their status) |
| `openTaskBook(task)` | `READ` → `/reader/:id` (download), `LISTEN` → `/listen/:id` (audio) |

**State signals:** `books`, `loading`, `uploading`, `error`, `dragOver`, `audioJobs`, `generatingIds`, `searchQuery`, `searching`, `searchResults`, `downloadJobs`, `downloadStarting`, `taskCenterOpen`, `dismissedAudio` (private), plus computed `tasks` and `runningCount`.

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
| `applyDisplaySettings(s)` | Applies `bg_color`/`font_size`/`font_family`/`page_width`/`view_mode` from settings; called reactively via `toObservable(settings.settings)` so a hard refresh (when `SettingsService.load()` is still in flight) re-applies the saved values instead of stale defaults; only re-layouts when a value actually changed |

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
| `searchBooks(query)` | GET | `/api/search?q=` | Local + linovelib search |
| `startDownload(url)` | POST | `/api/downloads` | Start bilinovel download job |
| `getDownloadStatus(jobId)` | GET | `/api/downloads/:id` | Download job progress |
| `cancelDownload(jobId)` | POST | `/api/downloads/:id/cancel` | Cancel download job |
| `getProgress(id)` | GET | `/api/progress/:id` | Reading progress |
| `updateProgress(id, data)` | PUT | `/api/progress/:id` | Save progress |
| `getSettings()` | GET | `/api/settings` | User settings |
| `updateSettings(data)` | PATCH | `/api/settings` | Update settings |
| `translate(req)` | POST | `/api/translate` | Translate text |
| `tts(text, refAudioB64, lang)` | POST | `/api/tts` | On-demand TTS (legacy sentence TTS) |
| `uploadTtsRefAudio(file)` | POST | `/api/tts/ref-audio` | Upload reference audio to TTS container |
| `getVoiceboxProfiles(url?, port?)` | GET | `/api/voicebox/profiles` | List Voicebox profiles |
| `loadVoiceboxModel(url?, port?)` | POST | `/api/voicebox/load-model` | Load TTS model into GPU |
| `startAudioGeneration(bookId)` | POST | `/api/voicebox/generate/:id` | Start chapter-audio generation |
| `cancelAudioGeneration(bookId)` | POST | `/api/voicebox/cancel/:id` | Cancel chapter-audio generation |
| `getAudioStatus(bookId)` | GET | `/api/voicebox/status/:id` | Job + chapter audio list |
| `getChapterAudioUrl(bookId, idx)` | — | — | WAV URL for `<audio>` src |
| `deleteBookAudio(bookId)` | DELETE | `/api/voicebox/audio/:id` | Delete all audio + reset job |
| `getListeningProgress(id)` | GET | `/api/listening-progress/:id` | Saved listening position |
| `updateListeningProgress(id, data)` | PUT | `/api/listening-progress/:id` | Save listening position |

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
/opds         →  OpdsComponent           (public)
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
| `voicebox_url` | String | Voicebox server host (default `http://host.docker.internal`) |
| `voicebox_port` | Integer | Voicebox server port (default `17493`) |
| `voicebox_profile_id` | String | selected Voicebox voice profile |
| `voicebox_language` | String | `en` / `zh` |
| `voicebox_model_size` | String | default `1.7B` |
| `tts_language` | String | on-demand TTS language `zh` / `en` / `ja` (default `zh`) |

#### `BookDownloadJob`

One row per bilinovel download job.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `novel_id` | String | bilinovel novel id |
| `novel_url` | String | original novel page URL |
| `title` | String | filled once the catalog is fetched |
| `status` | String | `running` / `done` / `failed` / `cancelled` |
| `chapters_done` | Integer | incremented per fetched chapter |
| `total_chapters` | Integer | from the catalog |
| `book_id` | Integer | nullable; set when the EPUB is registered into the library |
| `error` | Text | nullable; last error message |
| `created_at` | DateTime | |
| `completed_at` | DateTime | |

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
| `TranslationResponse` | translated_text + provider |
| `SettingsUpdate` | Partial settings PATCH body |
| `SettingsResponse` | Full settings response |
| `UserInfo` | email, name, picture, auth_type |
| `AudioJobStatus` | book_id, status, chapters_done, total_chapters, error |
| `ChapterAudioInfo` | per-chapter audio state (index, status, duration, has_audio) |
| `AudioStatusResponse` | job + chapters list |
| `VoiceboxProfile` | id, name, language, description |
| `ListeningProgressUpdate` / `Response` | chapter_index + position_seconds |
| `LinovelibBookResponse` | title, url, author, publisher, cover_url, status, rating, description, tags |
| `SearchResponse` | query, local books, linovelib books, total, suggestion, error |
| `DownloadStartRequest` | url |
| `DownloadJobResponse` | full download job state |

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

#### TTS Router — prefix `/api/tts`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tts` | Forward synthesis request to the TTS container (`{text, language}`; `ref_audio_base64` accepted but ignored — reference audio lives in the container) |
| POST | `/api/tts/ref-audio` | Forward reference-audio upload (multipart) to the TTS container for voice cloning |

#### Search Router — prefix `/api/search`

| Method | Path | Query | Description |
|--------|------|-------|-------------|
| GET | `/api/search` | `q` (required, 1–100 chars) | Searches local `books` (title/author LIKE) and bilinovel.com in parallel; returns `SearchResponse` (linovelib errors are captured in `linovelib_error`, not raised) |

#### Downloads Router — prefix `/api/downloads`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/downloads` | Start a bilinovel download job (body `{url}`; validates the URL matches `linovelib/bilinovel.com/novel|download/{id}`) |
| GET | `/api/downloads/{job_id}` | Poll job state (progress, status, error) |
| POST | `/api/downloads/{job_id}/cancel` | Set status to `cancelled` (checked cooperatively by the worker between chapters) |

Downloads run in a plain daemon `threading.Thread` (not FastAPI `BackgroundTasks`) because they can run for a long time; the thread registry lives in `_job_threads`.

#### Misc

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status":"ok"}` for Docker health check |
| GET | `/` | API info |

---

### 4.4 Services

#### `book_parser.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_epub` | `(file_path) → (title, author, chapters, cover_bytes)` | Uses ebooklib to extract spine items; converts HTML to chapter dicts; rewrites relative asset URLs |
| `parse_txt` | `(file_path) → (title, chapters)` | Detects chapter breaks via regex (`第X章`, `Chapter`, aozora `<a name="N">` anchors); falls back to 3000-char chunks |
| `decode_text` | `(bytes) → str` | Text-encoding auto-detection: BOM (UTF-8/16/32) → strict UTF-8 → legacy codecs (cp932, euc-jp, gb18030, big5) scored by kana presence (kana-less tie prefers GBK family) |
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

#### `linovelib.py` — bilinovel.com search

| Function | Description |
|----------|-------------|
| `search_linovelib(query) → LinovelibSearchResult` | Runs the Jieqi search-guard cookie chain (`/search.html?search_guard=css\|js\|redeem`), POSTs the search form, parses `li.book-li` results |
| `_run_guard(session)` | Completes the css/js/redeem cookie dance using `curl_cffi` with Chrome TLS impersonation — no browser or user cookies needed |
| `_parse_results(html)` | Extracts title/url/author/publisher/cover/status/rating/description/tags; filters to novel URLs only |

`LinovelibError` is raised on network/parse failure and surfaced to the frontend as `linovelib_error` in the search response.

#### `bilinovel_downloader.py` — novel scraper + EPUB builder

Ports the scraping logic of `bili_novel_packer` (montaro2017/bili_novel_packer):

| Function | Description |
|----------|-------------|
| `fetch_novel(novel_id) → NovelMeta` | Title, author, cover URL |
| `fetch_catalog(novel_id) → [VolumeRef]` | Volume-grouped chapter list (some chapters hide URLs and need probing) |
| `resolve_chapter_url(volumes, pos)` | Probes next/prev chapter links to recover hidden chapter URLs |
| `fetch_chapter(url, volume_title)` | Fetches one chapter: multi-page handling (`url_previous`/`url_next` + `#footlink`), junk-tag cleanup, lazy-image extraction, unicode-host obfuscation (`\U0001d623`) fixup |
| `download_image(src)` | Rate-limited image download |
| `build_epub(meta, volumes, htmls, images, dest)` | Assembles a cover + volumes + chapters EPUB compatible with the reader |

The scraper is rate-limited (15 text req/min, 10 image req/min) and restores the site's paragraph-shuffle obfuscation driven by `chapterlog.js` template parameters (`test_chapterlog.py` covers this).

---

## 5. On-demand TTS Service (OmniVoice / IndexTTS-2.5)

Runs as a separate Docker container on the internal Docker network. Two engines are supported, exactly one active at a time (selected by the `TTS_URL_BASE` env var in `docker-compose.yml`):

| Container | Service name (default) | Notes |
|-----------|------------------------|-------|
| `omnivoice-tts` | `lnreader-omnivoice-tts:8765` | Default; GPU runtime; CPU variant `lnreader-omnivoice-tts-cpu:8767` |
| `indextts-tts` | `lnreader-indextts-tts:8766` | IndexTTS-2.5 zero-shot voice cloning (zh/en/ja/es/ar) |

Both containers expose the same API surface (`omnivoice-tts/server.py`, `indextts-tts/server.py`):

```
POST {TTS_BASE}/tts
Body: { "text": "...", "language": "zh" }        # zh | en | ja
Response: { "audio_base64": "<base64 WAV>" }       # (engine-specific JSON)

POST {TTS_BASE}/ref-audio                          # multipart upload, voice cloning
GET  {TTS_BASE}/health
```

- The backend `/api/tts` router proxies `{text, language}` to `POST {TTS_BASE}/tts` (a legacy `ref_audio_base64` field is accepted but ignored — the reference audio lives inside the container, not in the request).
- Reference audio: uploaded from the Settings page via `POST /api/tts/ref-audio`, stored by the container at `/app/data/ref.wav` (falls back to the bundled `/app/ref.wav`).
- Consumer: the reader's sentence-level TTS (`ReaderComponent.startTTS()` / `bufferAhead()` / `fetchAndPlay()`) — kept for compatibility, its UI button is currently hidden.
- Chapter-by-chapter audio for the listen page uses the separate **Voicebox** pipeline (Section 6), not this endpoint.

---

## 6. Voicebox Chapter-Audio Pipeline

Voicebox is a separate, locally-running TTS server (default `http://host.docker.internal:17493`; the API shape below matches an OmniVoice instance). LNreader's backend proxies all Voicebox calls — the frontend never contacts Voicebox directly. This pipeline generates the per-chapter WAV files used by the listen page (`/listen/:id`), distinct from the on-demand `/api/tts` container (Section 5).

### 6.1 Database Tables

#### `BookAudioJob`
One row per book; tracks overall generation state.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `book_id` | Integer | not a FK to avoid cascade issues |
| `status` | String | `idle` / `running` / `done` / `failed` / `cancelled` |
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
| POST | `/api/voicebox/load-model` | Proxy to Voicebox `/models/load` (optional `url`/`port` query params override settings) |
| GET | `/api/voicebox/profiles` | Proxy to Voicebox `/profiles` (optional `url`/`port` query params) |
| POST | `/api/voicebox/generate/{book_id}` | Start background audio generation (400 if no profile set, 409 if already running) |
| POST | `/api/voicebox/cancel/{book_id}` | Set running job status to `cancelled` (worker checks between chapters) |
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
- `voicebox_url` (DB default `http://host.docker.internal`)
- `voicebox_port` (DB default `17493`)
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
  1. Read vpHeight / vpWidth from the .paginate-viewport element
  2. Create hidden off-screen measurer div that mirrors the real article
     exactly: width = pageWidthPct% of the viewport's clientWidth,
     box-sizing:border-box + padding:40px 24px (content width = pct% - 48,
     matching .chapter-content), same font/line-height.
     (The .paginate-container itself is full-width without padding or
     max-width — the article's own max-width controls the reading column,
     so the measurer stays in sync with the rendered text at every width.)
  3. Reset div content; start page 1 accumulator
  4. For each child node of chapter HTML:
       - append node clone to hidden div
       - if div.scrollHeight > vpHeight:
           - remove last node; save current HTML as page N
           - start new page with this node
  4b. If a single child alone overflows (whole chapter trapped in an
       unclosed `<a name="...">` anchor, a giant converted paragraph):
       splitOverflowingNode() flattens element children and binary-searches
       text slices that fit (snapping to word/line boundaries), then the
       fragments accumulate as usual
  5. Save last partial page
  6. Store all pages in `pages` signal
  7. Navigate to saved pageIndex (from progress) or page 0
  8. Once per chapter: re-run the whole recalc when document.fonts.ready
     resolves (first pass may have measured with the fallback font while
     the webfont was still loading, which shifts line metrics)

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
  → LibraryComponent.generateAudio(book) / startAudioGeneration(book)
  → ApiService.startAudioGeneration(bookId)   POST /api/voicebox/generate/:id
  → backend: guard (no profile set? → 400), guard (already running? → 409)
  → create/reset BookAudioJob (status=running)
  → BackgroundTasks.add_task(_run_generation, book_id, SessionLocal)
  → return AudioJobStatus {status: 'running', chapters_done: 0}

_run_generation (background task):
  for each chapter 0..N-1:
    → book_parser.parse_epub/txt → chapters[idx]
    → skip chapter if ChapterAudio already done (resume support)
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
    → check job.status: if 'cancelled' (set via POST /api/voicebox/cancel/:id) → break

Frontend polls GET /api/voicebox/status/:id every 3s
  → updates book card UI + task center progress
  → stops polling when status = done/failed
```

The same job appears in the library task center (bottom-right panel) with a progress bar, a CANCEL action while running, and RESUME/DISMISS once finished.

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

### 7.11 Search (local + bilinovel.com)

```
User types in the library search bar
  → onSearchInput → debounce 500ms → doSearch()
  → GET /api/search?q=...

backend routers/search.py:
  → query local books: title/author ILIKE %q%
  → services.linovelib.search_linovelib(q):
      _run_guard(session):
        GET /search.html                       (Jieqi page)
        GET /search.html?search_guard=css      → sets jieqiSearchCss
        GET /search.html?search_guard=js       → extracts jieqiSearchJs inline
        GET /search.html?search_guard=redeem   → sets jieqiSearchTicket
      POST the search form with cookies → parse li.book-li results
  → merge into SearchResponse; linovelib failures → linovelib_error (frontend shows it)

Frontend renders:
  → LOCAL LIBRARY section (click → /reader/:id)
  → LINOVELIB.COM section: cover/author/publisher/status/rating/tags/description,
    click card → open bilinovel.com in a new tab, Download button → start job
```

### 7.12 Bilinovel Download (→ EPUB → library)

```
User clicks DOWNLOAD on a linovelib search result
  → LibraryComponent.startDownloadForUrl(url)
  → POST /api/downloads {url}  (validated against novel-id regex)
  → backend creates BookDownloadJob(status=running), spawns daemon thread
  → _run_download (threading.Thread, separate DB session):
      1. fetch_novel(novel_id)            → title, author, cover
      2. fetch_catalog(novel_id)          → volumes → total_chapters
      3. per chapter (rate-limited):
           resolve_chapter_url (probe next/prev) if catalog hides the URL
           fetch_chapter  → {title, html, images}   (multi-page + shuffle restore)
           job.chapters_done += 1; db.commit()
         — stops early if job.status == 'cancelled'
      4. download images (dedup by URL, skip failures)
      5. build_epub(...) → save to BOOKS_DIR/{title}_{id}.epub
      6. _register_epub(dest)  → parse_epub + detect_language → new Book row
      7. job.status = done, job.book_id = <new book id>
  → failure → job.status = failed + error (truncated 500 chars); partial epub removed

Frontend polls GET /api/downloads/:id every 3s
  → task center + search-result card show "12 / 620" progress
  → on done: grid refreshes, card shows READ
```

### 7.13 Task Center (library page)

```
FAB bottom-right (badge = running task count) → toggleTaskCenter() expands panel

tasks = computed(...)  merges:
  - downloadJobs: every BookDownloadJob  (title or "Novel #{id}", 0..1 progress)
  - audioJobs:    every job with status != idle (skips dismissedAudio book ids)

Per task: kind badge (DOWNLOAD/AUDIO), status label, title, progress bar
  (+ indeterminate animation while running with no chapters yet), "x / y CH" text,
  error message, and actions:
    running  → CANCEL      (POST /api/downloads/:id/cancel | /api/voicebox/cancel/:id)
    failed   → RETRY + DISMISS
    cancelled→ RESUME (audio) + DISMISS
    done     → READ (/reader/:id) or LISTEN (/listen/:id) + DISMISS

Dismissing a download removes it from downloadJobs; dismissing audio only adds the
book id to dismissedAudio so the book card keeps its LISTEN/status controls.
```

---

## 8. Configuration & Infrastructure

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `JWT_SECRET` | — | Secret for JWT signing |
| `FRONTEND_URL` | `http://localhost:4200` | CORS origin + OAuth redirect base (compose sets `http://localhost`) |
| `BACKEND_URL` | `http://localhost:8000` | OAuth callback URI base |
| `BOOKS_DIR` | `./books` | Directory for uploaded book files (compose: `/app/books`) |
| `AUDIO_DIR` | `./audio` | Directory for generated chapter WAV files |
| `DATABASE_URL` | `sqlite:///./lnreader.db` | SQLAlchemy connection string (compose: `sqlite:////app/data/lnreader.db`) |
| `TTS_URL_BASE` | `http://lnreader-omnivoice-tts:8765` | On-demand TTS container base URL (`...-tts-cpu:8767` / `...-indextts-tts:8766` for the alternatives) |

### Docker Compose Services

| Service | Port | Build | Notes |
|---------|------|-------|-------|
| `backend` | internal 8000 | `./backend` | Health check: `GET /health`; only reachable via nginx |
| `frontend` | host `127.0.0.1:8080` | `./frontend` | nginx serves the Angular app and reverse-proxies `/api` + `/auth` to backend; depends on backend healthy |
| `omnivoice-tts` | internal 8765 | `./omnivoice-tts` | Default TTS engine; `runtime: nvidia` (GPU); CPU variant `omnivoice-tts-cpu` (Dockerfile.cpu, port 8767) commented out by default |
| `indextts-tts` | internal 8766 | `./indextts-tts` | IndexTTS-2.5 alternative (CPU or GPU), commented out by default |
| `qwen-tts` / GPT-SoVITS | — | — | Legacy TTS containers, commented out |

**Volumes:** `books_data` (EPUB files), `db_data` (SQLite), `omnivoice_cache` / `omnivoice_refaudio` (HF cache + uploaded reference audio), `indextts_checkpoints` / `indextts_refaudio`

### CORS

Backend allows:
- `FRONTEND_URL` environment variable value
- `http://localhost:4200` (development)

### Backend Middleware

1. `CORSMiddleware` — whitelist origin, allow credentials, all methods/headers
2. `StaticFiles` — mounts `/covers` (under `BOOKS_DIR`) for book cover images

### Backend Auto-migration

On startup, `init_db()` in `database.py`:
- Creates all tables from SQLAlchemy metadata
- Runs a list of column-level `ALTER TABLE` migrations against `user_settings` (currently: `view_mode`, `voicebox_url`, `voicebox_port`, `voicebox_profile_id`, `voicebox_language`, `voicebox_model_size`, `tts_language`) — each is added only if the `SELECT` for it fails
- Drops the obsolete `linovelib_cookie` column if present
- Inserts the single `UserSettings` row (id=1) if missing
---

## 9. OPDS (Open Publication Distribution System)

LNreader is both an **OPDS server** — its library is published as a standard
OPDS 1.x catalog any OPDS client (Foliate, KOReader, Thorium…) can browse
and acquire from — and an **OPDS client** — it can register external catalog
URLs, browse their feeds, search them, and download their books straight
into the local library.

### 9.1 OPDS Server — `/opds`

All paths are unauthenticated Atom feeds (content type
`application/atom+xml;profile=opds-catalog`), with absolute URLs derived from
`request.base_url` (Host header).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/opds` | Navigation feed — `Library` subsection entry + search link |
| GET | `/opds/catalog?page&page_size` | Acquisition feed of all books (paginated via `next` link, `opensearch:totalResults`) |
| GET | `/opds/search?q` | Search feed over title/author |
| GET | `/opds/opensearch.xml` | OpenSearch description (template `/opds/search?q={searchTerms}`) |
| GET | `/opds/books/{id}/file` | Raw `.epub`/`.txt` acquisition target (`Content-Disposition: attachment`) |

Entries carry Atom/DC metadata (title, author, language, updated), cover
links (`http://opds-spec.org/image` + `image/thumbnail` → `/api/books/{id}/cover`)
and an `http://opds-spec.org/acquisition/open-access` link per book. Feed
builder: `services/opds.py` (`build_root_feed`, `build_catalog_feed`,
`build_search_feed`, `build_opensearch_xml`).

### 9.2 OPDS Client — `/api/opds`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/opds/server` | Absolute URL of this instance's catalog |
| GET | `/api/opds/sources` | List saved catalogs |
| POST | `/api/opds/sources` | `{name, url}` — add a catalog |
| DELETE | `/api/opds/sources/{id}` | Remove a catalog |
| GET | `/api/opds/browse?url&q` | Fetch + normalize a remote feed (JSON); with `q` resolves the advertised search template (inline `{searchTerms}` or via the OpenSearch description) |
| POST | `/api/opds/acquire` | `{url}` — download a remote `.epub`/`.txt` into `BOOKS_DIR` and register it (returns `Book`) |

`browse` guards: http(s) only, 30 s timeout, 10 MiB feed cap. `acquire`
resolves the file type from URL suffix → `Content-Disposition` →
`Content-Type` (extensionless links like `/download/123` are common in the
wild); only EPUB/TXT are imported, streamed in 1 MiB chunks, partial files
removed on failure. Feeds are parsed by `services/opds.py
parse_opds_feed` (namespace-tolerant ElementTree: Atom + `dc:language`,
OPDS rel URIs, relative-href resolution, subsection vs acquisition entries).

### 9.3 Database

#### `OpdsSource`
One row per saved external catalog: `id`, `name`, `url`, `created_at`.
Created by `Base.metadata.create_all` — no manual migration needed.

### 9.4 Frontend — `OpdsComponent` (`/opds`)

Nav link "OPDS CATALOG" in the library header. Page shows the instance's
catalog URL (copy button), external-catalog management (add/remove), and a
browser with breadcrumbs (`‹ CATALOGS`, `‹ BACK`), per-entry
cover/title/author/summary cards, category `OPEN` (subsection links),
`DOWNLOAD & READ` (acquire → navigate to `/reader/{id}`), catalog search
(when the feed advertises `search_url`) and `LOAD MORE` pagination through
`next_url`.

### 9.5 Data Flow — OPDS acquire

```
User clicks DOWNLOAD & READ
  → POST /api/opds/acquire {url: acquisition link}
  → stream remote file into BOOKS_DIR (unique name)
  → register_book_file() (parse_epub, cover, language detect)
  → Book row committed → frontend routes to /reader/{id}
```

External client flow: `/opds` → `/opds/catalog` → `/opds/books/{id}/file`
(cover via `/api/books/{id}/cover`); search via `/opds/search?q=` or the
OpenSearch template.
