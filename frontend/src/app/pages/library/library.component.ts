import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Book, AudioJobStatus } from '../../models/book.model';

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

  private pollInterval: ReturnType<typeof setInterval> | null = null;

  constructor(
    public auth: AuthService,
    private api: ApiService,
    private router: Router
  ) {}

  ngOnInit() {
    this.loadBooks();
  }

  ngOnDestroy() {
    if (this.pollInterval) clearInterval(this.pollInterval);
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
    this.api.cancelAudioGeneration(book.id).subscribe({
      next: (job) => {
        const map = new Map(this.audioJobs());
        map.set(book.id, job);
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
}
