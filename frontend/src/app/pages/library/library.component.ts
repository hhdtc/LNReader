import { Component, OnInit, OnDestroy, signal, computed } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { forkJoin, of, interval, Subscription } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Book, AudioJobStatus, SearchResponse, LinovelibBook, DownloadJob } from '../../models/book.model';

/** One entry shown in the task center (downloads + audio generation). */
interface TaskItem {
  id: string;
  kind: 'download' | 'audio';
  title: string;
  status: string; // running / done / failed / cancelled
  progress: number; // 0..1
  detail: string;
  error?: string;
  bookId?: number;
  job?: DownloadJob;
}

@Component({
  selector: 'app-library',
  imports: [CommonModule, RouterLink],
  templateUrl: './library.component.html',
  styleUrls: ['./library.component.scss'],
})
export class LibraryComponent implements OnInit, OnDestroy {
  books = signal<Book[]>([]);
  loading = signal(false);
  uploading = signal(false);
  error = signal('');
  dragOver = signal(false);
  audioJobs = signal<Map<number, AudioJobStatus>>(new Map());
  generatingIds = signal<Set<number>>(new Set());
  searchQuery = signal('');
  searching = signal(false);
  searchResults = signal<SearchResponse | null>(null);
  downloadJobs = signal<Map<string, DownloadJob>>(new Map());
  downloadStarting = signal<Set<string>>(new Set());

  // Task center (bottom-right)
  taskCenterOpen = signal(false);
  private dismissedAudio = signal<Set<number>>(new Set());

  tasks = computed<TaskItem[]>(() => {
    const items: TaskItem[] = [];

    // Bilinovel download jobs
    for (const job of this.downloadJobs().values()) {
      const total = job.total_chapters || 0;
      items.push({
        id: `dl-${job.id}`,
        kind: 'download',
        title: job.title || `Novel #${job.novel_id}`,
        status: job.status,
        progress: total ? job.chapters_done / total : 0,
        detail: total ? `${job.chapters_done} / ${total} CH` : 'Fetching catalog...',
        error: job.error ?? undefined,
        bookId: job.book_id ?? undefined,
        job,
      });
    }

    // Voicebox chapter-audio jobs (skip idle books and dismissed entries)
    const dismissed = this.dismissedAudio();
    const titleById = new Map(this.books().map(b => [b.id, b.title] as const));
    for (const [bookId, st] of this.audioJobs().entries()) {
      if (st.status === 'idle' || dismissed.has(bookId)) continue;
      const total = st.total_chapters || 0;
      items.push({
        id: `au-${bookId}`,
        kind: 'audio',
        title: titleById.get(bookId) || `Book #${bookId}`,
        status: st.status,
        progress: total ? st.chapters_done / total : 0,
        detail: total ? `${st.chapters_done} / ${total} CH` : '',
        error: st.error,
        bookId,
      });
    }

    return items;
  });

  runningCount = computed(() =>
    this.tasks().filter(t => t.status === 'running').length
  );

  private pollInterval: ReturnType<typeof setInterval> | null = null;
  private searchDebounce: ReturnType<typeof setTimeout> | null = null;
  private downloadPoll: Subscription | null = null;

  constructor(
    public auth: AuthService,
    private api: ApiService,
    private router: Router
  ) {}

  ngOnInit() {
    this.loadBooks();
  }

  ngOnDestroy() {
    clearInterval(this.pollInterval!);
    clearTimeout(this.searchDebounce!);
    this.downloadPoll?.unsubscribe();
  }

  loadBooks() {
    this.loading.set(true);
    this.api.getBooks().subscribe({
      next: (b) => {
        this.books.set(b);
        this.loading.set(false);
        this.loadAllAudioStatuses(b.map(x => x.id));
      },
      error: () => { this.loading.set(false); }
    });
  }

  onSearchInput(value: string) {
    this.searchQuery.set(value);
    if (this.searchDebounce) clearTimeout(this.searchDebounce);
    const q = value.trim();
    if (!q) {
      this.searchResults.set(null);
      return;
    }
    this.searchDebounce = setTimeout(() => this.doSearch(), 500);
  }

  doSearch() {
    if (this.searchDebounce) {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = null;
    }
    const q = this.searchQuery().trim();
    if (!q) return;
    this.searching.set(true);
    this.api.searchBooks(q).subscribe({
      next: (res) => {
        this.searching.set(false);
        this.searchResults.set(res);
      },
      error: () => {
        this.searching.set(false);
        this.error.set('Search failed. Please try again.');
        setTimeout(() => this.error.set(''), 4000);
      }
    });
  }

  clearSearch() {
    this.searchQuery.set('');
    this.searchResults.set(null);
    if (this.searchDebounce) {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = null;
    }
  }

  openLinovelib(book: LinovelibBook) {
    window.open(book.url, '_blank', 'noopener,noreferrer');
  }

  // ---------- Bilinovel downloads ----------

  getDownloadJob(book: LinovelibBook): DownloadJob | null {
    return this.downloadJobs().get(book.url) ?? null;
  }

  isDownloadStarting(book: LinovelibBook): boolean {
    return this.downloadStarting().has(book.url);
  }

  downloadNovel(book: LinovelibBook, event: MouseEvent) {
    event.stopPropagation();
    this.startDownloadForUrl(book.url);
  }

  private startDownloadForUrl(url: string) {
    const starting = new Set(this.downloadStarting());
    starting.add(url);
    this.downloadStarting.set(starting);

    this.api.startDownload(url).subscribe({
      next: (job) => {
        const starting2 = new Set(this.downloadStarting());
        starting2.delete(url);
        this.downloadStarting.set(starting2);
        const map = new Map(this.downloadJobs());
        map.set(url, job);
        this.downloadJobs.set(map);
        this.startDownloadPolling();
      },
      error: (err) => {
        const starting2 = new Set(this.downloadStarting());
        starting2.delete(url);
        this.downloadStarting.set(starting2);
        this.error.set(err?.error?.detail ?? 'Failed to start download');
        setTimeout(() => this.error.set(''), 4000);
      }
    });
  }

  private startDownloadPolling() {
    if (this.downloadPoll) return;
    this.downloadPoll = interval(3000)
      .pipe(
        switchMap(() => {
          const running = [...this.downloadJobs().values()]
            .filter(j => j.status === 'running')
            .map(j => j.id);
          if (!running.length) return of([]);
          return forkJoin(
            running.map(id => this.api.getDownloadStatus(id).pipe(catchError(() => of(null))))
          );
        })
      )
      .subscribe(results => {
        if (!results?.length) return;
        let anyRunning = false;
        const map = new Map(this.downloadJobs());
        for (const res of results) {
          if (!res) continue;
          const prev = [...map.values()].find(j => j.id === res.id);
          map.set(res.novel_url, res);
          if (res.status === 'running') anyRunning = true;
          if (res.status === 'done' && res.book_id && prev?.status !== 'done') {
            // New book in the library — refresh the grid.
            this.loadBooks();
          }
        }
        this.downloadJobs.set(map);
        if (!anyRunning) {
          this.downloadPoll?.unsubscribe();
          this.downloadPoll = null;
        }
      });
  }

  openDownloadedBook(book: LinovelibBook, event: MouseEvent) {
    event.stopPropagation();
    const job = this.getDownloadJob(book);
    if (job?.book_id) {
      this.router.navigate(['/reader', job.book_id]);
    }
  }

  cancelJob(book: LinovelibBook, event: MouseEvent) {
    event.stopPropagation();
    const job = this.getDownloadJob(book);
    if (job) this.cancelDownloadJob(job);
  }

  cancelDownloadJob(job: DownloadJob) {
    if (!job || job.status !== 'running') return;
    this.api.cancelDownload(job.id).subscribe({
      next: (updated) => {
        const map = new Map(this.downloadJobs());
        map.set(job.novel_url, updated);
        this.downloadJobs.set(map);
      },
      error: () => {}
    });
  }

  loadAllAudioStatuses(bookIds: number[]) {
    if (!bookIds.length) return;
    const requests = bookIds.map(id =>
      this.api.getAudioStatus(id).pipe(catchError(() => of(null)))
    );
    forkJoin(requests).subscribe(results => {
      const map = new Map(this.audioJobs());
      results.forEach((res, i) => {
        if (res) map.set(bookIds[i], res.job);
      });
      this.audioJobs.set(map);
      this.startPollingIfNeeded();
    });
  }

  startPollingIfNeeded() {
    const hasRunning = [...this.audioJobs().values()].some(j => j.status === 'running');
    if (hasRunning && !this.pollInterval) {
      this.pollInterval = setInterval(() => this.pollRunningJobs(), 3000);
    } else if (!hasRunning && this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }

  pollRunningJobs() {
    const runningIds = [...this.audioJobs().entries()]
      .filter(([, j]) => j.status === 'running')
      .map(([id]) => id);

    if (!runningIds.length) {
      clearInterval(this.pollInterval!);
      this.pollInterval = null;
      return;
    }

    runningIds.forEach(id => {
      this.api.getAudioStatus(id).subscribe(res => {
        const map = new Map(this.audioJobs());
        map.set(id, res.job);
        this.audioJobs.set(map);
        if (res.job.status !== 'running') this.startPollingIfNeeded();
      });
    });
  }

  getAudioJob(bookId: number): AudioJobStatus | null {
    return this.audioJobs().get(bookId) ?? null;
  }

  generateAudio(book: Book, event: MouseEvent) {
    event.stopPropagation();
    this.startAudioGeneration(book);
  }

  private startAudioGeneration(book: Book) {
    const ids = new Set(this.generatingIds());
    ids.add(book.id);
    this.generatingIds.set(ids);

    this.api.startAudioGeneration(book.id).subscribe({
      next: (job) => {
        const map = new Map(this.audioJobs());
        map.set(book.id, job);
        this.audioJobs.set(map);
        const ids2 = new Set(this.generatingIds());
        ids2.delete(book.id);
        this.generatingIds.set(ids2);
        // Re-show the task in the center if it had been dismissed earlier.
        const dismissed = new Set(this.dismissedAudio());
        dismissed.delete(book.id);
        this.dismissedAudio.set(dismissed);
        this.startPollingIfNeeded();
      },
      error: (err) => {
        const ids2 = new Set(this.generatingIds());
        ids2.delete(book.id);
        this.generatingIds.set(ids2);
        this.error.set(err?.error?.detail ?? 'Failed to start generation');
        setTimeout(() => this.error.set(''), 4000);
      }
    });
  }

  stopGeneration(book: Book, event: MouseEvent) {
    event.stopPropagation();
    this.cancelAudioTask(book.id);
  }

  cancelAudioTask(bookId: number) {
    this.api.cancelAudioGeneration(bookId).subscribe({
      next: (job) => {
        const map = new Map(this.audioJobs());
        map.set(bookId, job);
        this.audioJobs.set(map);
        this.startPollingIfNeeded();
      },
      error: () => {}
    });
  }

  deleteAudio(book: Book, event: MouseEvent) {
    event.stopPropagation();
    if (!confirm(`Delete all audio for "${book.title}"?`)) return;
    this.api.deleteBookAudio(book.id).subscribe(() => {
      const map = new Map(this.audioJobs());
      map.delete(book.id);
      this.audioJobs.set(map);
    });
  }

  openListen(book: Book, event: MouseEvent) {
    event.stopPropagation();
    this.router.navigate(['/listen', book.id]);
  }

  onFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files?.length) {
      this.uploadFile(input.files[0]);
      input.value = '';
    }
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(false);
    const file = event.dataTransfer?.files[0];
    if (file) this.uploadFile(file);
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(true);
  }

  onDragLeave() {
    this.dragOver.set(false);
  }

  uploadFile(file: File) {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'epub' && ext !== 'txt') {
      this.error.set('Only .epub and .txt files are supported.');
      setTimeout(() => this.error.set(''), 3000);
      return;
    }
    this.uploading.set(true);
    this.error.set('');
    this.api.uploadBook(file).subscribe({
      next: (book) => {
        this.books.update(b => [book, ...b]);
        this.uploading.set(false);
      },
      error: () => {
        this.error.set('Upload failed. Please try again.');
        this.uploading.set(false);
        setTimeout(() => this.error.set(''), 3000);
      }
    });
  }

  openBook(book: Book) {
    this.router.navigate(['/reader', book.id]);
  }

  deleteBook(book: Book, event: MouseEvent) {
    event.stopPropagation();
    if (!confirm(`Delete "${book.title}"?`)) return;
    this.api.deleteBookAudio(book.id).subscribe();
    this.api.deleteBook(book.id).subscribe(() => {
      this.books.update(b => b.filter(x => x.id !== book.id));
      const map = new Map(this.audioJobs());
      map.delete(book.id);
      this.audioJobs.set(map);
    });
  }

  getCoverUrl(book: Book): string {
    if (!book.cover_path) return '';
    return this.api.getCoverUrl(book.id);
  }

  formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  formatProgress(job: AudioJobStatus): string {
    return `${job.chapters_done} / ${job.total_chapters} CH`;
  }

  // ---------- Task center ----------

  toggleTaskCenter() {
    this.taskCenterOpen.update(v => !v);
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'running': return 'RUNNING';
      case 'done': return 'DONE';
      case 'failed': return 'FAILED';
      case 'cancelled': return 'CANCELLED';
      default: return status.toUpperCase();
    }
  }

  retryLabel(task: TaskItem): string {
    return task.kind === 'audio' && task.status === 'cancelled' ? 'RESUME' : 'RETRY';
  }

  cancelTask(task: TaskItem) {
    if (task.kind === 'download' && task.job) {
      this.cancelDownloadJob(task.job);
    } else if (task.kind === 'audio' && task.bookId != null) {
      this.cancelAudioTask(task.bookId);
    }
  }

  retryTask(task: TaskItem) {
    if (task.kind === 'download' && task.job) {
      this.startDownloadForUrl(task.job.novel_url);
    } else if (task.kind === 'audio' && task.bookId != null) {
      const book = this.books().find(b => b.id === task.bookId);
      if (book) this.startAudioGeneration(book);
    }
  }

  dismissTask(task: TaskItem) {
    if (task.kind === 'download') {
      if (task.job) {
        const map = new Map(this.downloadJobs());
        map.delete(task.job.novel_url);
        this.downloadJobs.set(map);
      }
    } else if (task.kind === 'audio' && task.bookId != null) {
      // Keep the entry in audioJobs (book card still shows its state),
      // but hide it from the task center.
      const dismissed = new Set(this.dismissedAudio());
      dismissed.add(task.bookId);
      this.dismissedAudio.set(dismissed);
    }
  }

  openTaskBook(task: TaskItem) {
    if (task.bookId == null) return;
    if (task.kind === 'download') {
      this.router.navigate(['/reader', task.bookId]);
    } else {
      this.router.navigate(['/listen', task.bookId]);
    }
  }
}
