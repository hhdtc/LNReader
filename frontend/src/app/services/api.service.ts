import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  Book, ChapterContent, ReadingProgress,
  UserSettings, TranslationRequest, TranslationResponse, UserInfo, ChapterSummary,
  VoiceboxProfile, AudioJobStatus, AudioStatusResponse, ListeningProgress, SearchResponse,
  DownloadJob
} from '../models/book.model';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiUrl;

  constructor(private http: HttpClient) {}

  // Auth
  getUser(): Observable<UserInfo> {
    return this.http.get<UserInfo>(`${this.base}/auth/user`);
  }

  loginLocal(): Observable<{ token: string }> {
    return this.http.post<{ token: string }>(`${this.base}/auth/local`, {});
  }

  logout(): Observable<any> {
    return this.http.post(`${this.base}/auth/logout`, {});
  }

  // Books
  getBooks(): Observable<Book[]> {
    return this.http.get<Book[]>(`${this.base}/api/books`);
  }

  uploadBook(file: File): Observable<Book> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<Book>(`${this.base}/api/books`, form);
  }

  getBook(id: number): Observable<Book> {
    return this.http.get<Book>(`${this.base}/api/books/${id}`);
  }

  getChapter(bookId: number, chapter: number, annotate = false): Observable<ChapterContent> {
    return this.http.get<ChapterContent>(
      `${this.base}/api/books/${bookId}/content?chapter=${chapter}&annotate=${annotate}`
    );
  }

  getChapterIndex(bookId: number): Observable<ChapterSummary[]> {
    return this.http.get<ChapterSummary[]>(`${this.base}/api/books/${bookId}/chapters`);
  }

  deleteBook(id: number): Observable<any> {
    return this.http.delete(`${this.base}/api/books/${id}`);
  }

  getCoverUrl(bookId: number): string {
    return `${this.base}/api/books/${bookId}/cover`;
  }

  searchBooks(query: string): Observable<SearchResponse> {
    return this.http.get<SearchResponse>(`${this.base}/api/search`, {
      params: { q: query }
    });
  }

  // Bilinovel downloads
  startDownload(url: string): Observable<DownloadJob> {
    return this.http.post<DownloadJob>(`${this.base}/api/downloads`, { url });
  }

  getDownloadStatus(jobId: number): Observable<DownloadJob> {
    return this.http.get<DownloadJob>(`${this.base}/api/downloads/${jobId}`);
  }

  cancelDownload(jobId: number): Observable<DownloadJob> {
    return this.http.post<DownloadJob>(`${this.base}/api/downloads/${jobId}/cancel`, {});
  }

  // Progress
  getProgress(bookId: number): Observable<ReadingProgress> {
    return this.http.get<ReadingProgress>(`${this.base}/api/progress/${bookId}`);
  }

  updateProgress(bookId: number, data: Partial<ReadingProgress>): Observable<ReadingProgress> {
    return this.http.put<ReadingProgress>(`${this.base}/api/progress/${bookId}`, data);
  }

  // Settings
  getSettings(): Observable<UserSettings> {
    return this.http.get<UserSettings>(`${this.base}/api/settings`);
  }

  updateSettings(data: Partial<UserSettings>): Observable<UserSettings> {
    return this.http.patch<UserSettings>(`${this.base}/api/settings`, data);
  }

  // Translation
  translate(req: TranslationRequest): Observable<TranslationResponse> {
    return this.http.post<TranslationResponse>(`${this.base}/api/translate`, req);
  }

  // TTS (old sentence-by-sentence, kept for compatibility)
  tts(text: string, refAudioBase64: string, language = 'zh'): Observable<{ audio_base64: string }> {
    return this.http.post<{ audio_base64: string }>(`${this.base}/api/tts`, { text, ref_audio_base64: refAudioBase64, language });
  }

  uploadTtsRefAudio(file: File): Observable<{ status: string; ref_audio: string }> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<{ status: string; ref_audio: string }>(`${this.base}/api/tts/ref-audio`, form);
  }

  // Voicebox
  // Direct Voicebox calls (browser → Voicebox, avoids Docker loopback issue)
  getVoiceboxProfilesDirect(url: string, port: number): Observable<VoiceboxProfile[]> {
    const base = `${url.replace(/\/+$/, '')}:${port}`;
    return this.http.get<VoiceboxProfile[]>(`${base}/profiles`);
  }

  loadVoiceboxModelDirect(url: string, port: number): Observable<any> {
    const base = `${url.replace(/\/+$/, '')}:${port}`;
    return this.http.post(`${base}/models/load`, {});
  }

  loadVoiceboxModel(url?: string, port?: number): Observable<{ status: string; detail: any }> {
    const params: any = {};
    if (url) params['url'] = url;
    if (port != null) params['port'] = port;
    return this.http.post<{ status: string; detail: any }>(`${this.base}/api/voicebox/load-model`, {}, { params });
  }

  getVoiceboxProfiles(url?: string, port?: number): Observable<VoiceboxProfile[]> {
    const params: any = {};
    if (url) params['url'] = url;
    if (port != null) params['port'] = port;
    return this.http.get<VoiceboxProfile[]>(`${this.base}/api/voicebox/profiles`, { params });
  }

  startAudioGeneration(bookId: number): Observable<AudioJobStatus> {
    return this.http.post<AudioJobStatus>(`${this.base}/api/voicebox/generate/${bookId}`, {});
  }

  cancelAudioGeneration(bookId: number): Observable<AudioJobStatus> {
    return this.http.post<AudioJobStatus>(`${this.base}/api/voicebox/cancel/${bookId}`, {});
  }

  getAudioStatus(bookId: number): Observable<AudioStatusResponse> {
    return this.http.get<AudioStatusResponse>(`${this.base}/api/voicebox/status/${bookId}`);
  }

  getChapterAudioUrl(bookId: number, chapterIndex: number): string {
    return `${this.base}/api/voicebox/audio/${bookId}/${chapterIndex}`;
  }

  deleteBookAudio(bookId: number): Observable<any> {
    return this.http.delete(`${this.base}/api/voicebox/audio/${bookId}`);
  }

  // Listening progress
  getListeningProgress(bookId: number): Observable<ListeningProgress> {
    return this.http.get<ListeningProgress>(`${this.base}/api/listening-progress/${bookId}`);
  }

  updateListeningProgress(bookId: number, data: { chapter_index: number; position_seconds: number }): Observable<ListeningProgress> {
    return this.http.put<ListeningProgress>(`${this.base}/api/listening-progress/${bookId}`, data);
  }
}
