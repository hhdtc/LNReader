import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  Book, ChapterContent, ReadingProgress,
  UserSettings, TranslationRequest, TranslationResponse, UserInfo, ChapterSummary
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
}
