import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { OpdsEntry, OpdsFeed, OpdsSource } from '../../models/book.model';

@Component({
  selector: 'app-opds',
  imports: [CommonModule, RouterLink],
  templateUrl: './opds.component.html',
  styleUrls: ['./opds.component.scss'],
})
export class OpdsComponent implements OnInit {
  // Sources
  sources = signal<OpdsSource[]>([]);
  newName = signal('');
  newUrl = signal('');
  adding = signal(false);
  serverUrl = signal('');

  // Browsing
  feed = signal<OpdsFeed | null>(null);
  browsing = signal(false);
  searchQuery = signal('');
  searching = signal(false);
  downloading = signal<Set<string>>(new Set());
  loadedPageUrls = signal<string[]>([]);
  private history: OpdsFeed[] = [];

  error = signal('');
  copied = signal(false);

  constructor(
    public auth: AuthService,
    private api: ApiService,
    private router: Router
  ) {}

  ngOnInit() {
    this.loadSources();
    this.api.getOpdsServerUrl().subscribe({
      next: (info) => this.serverUrl.set(info.url),
      error: () => {},
    });
  }

  private flashError(detail: string) {
    this.error.set(detail);
    setTimeout(() => this.error.set(''), 6000);
  }
  onNameInput(event: Event) {
    this.newName.set((event.target as HTMLInputElement).value);
  }

  onUrlInput(event: Event) {
    this.newUrl.set((event.target as HTMLInputElement).value);
  }

  onSearchInput(event: Event) {
    this.searchQuery.set((event.target as HTMLInputElement).value);
  }

  // ---------- sources ----------

  loadSources() {
    this.api.getOpdsSources().subscribe({
      next: (s) => this.sources.set(s),
      error: () => {},
    });
  }

  addSource() {
    const name = this.newName().trim();
    const url = this.newUrl().trim();
    if (!name || !url) return;
    this.adding.set(true);
    this.api.addOpdsSource(name, url).subscribe({
      next: (src) => {
        this.adding.set(false);
        this.newName.set('');
        this.newUrl.set('');
        this.sources.set([src, ...this.sources()]);
        this.openSource(src);
      },
      error: (e) => {
        this.adding.set(false);
        this.flashError(e?.error?.detail ?? 'Failed to add source');
      },
    });
  }

  removeSource(src: OpdsSource) {
    this.api.deleteOpdsSource(src.id).subscribe({
      next: () => this.sources.set(this.sources().filter((s) => s.id !== src.id)),
      error: () => this.flashError('Failed to remove source'),
    });
  }

  openSource(src: OpdsSource) {
    this.history = [];
    this.loadedPageUrls.set([]);
    this.searchQuery.set('');
    this.loadFeed(src.url);
  }

  backToSources() {
    this.feed.set(null);
    this.history = [];
    this.loadedPageUrls.set([]);
    this.searchQuery.set('');
  }

  copyServerUrl() {
    const url = this.serverUrl();
    if (!url) return;
    navigator.clipboard?.writeText(url).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  // ---------- browsing ----------

  loadFeed(url: string, q?: string) {
    this.browsing.set(true);
    this.error.set('');
    this.api.browseOpds(url, q).subscribe({
      next: (feed) => {
        this.feed.set(feed);
        this.browsing.set(false);
        this.searching.set(false);
      },
      error: (e) => {
        this.browsing.set(false);
        this.searching.set(false);
        this.flashError(e?.error?.detail ?? 'Failed to load catalog feed');
      },
    });
  }

  openSubsection(entry: OpdsEntry) {
    if (!entry.subsection_url) return;
    this.history.push(this.feed()!);
    this.loadedPageUrls.set([]);
    this.searchQuery.set('');
    this.loadFeed(entry.subsection_url);
  }

  goBack() {
    const prev = this.history.pop();
    if (prev) {
      this.feed.set(prev);
      this.loadedPageUrls.set([]);
      this.searchQuery.set('');
    } else {
      this.backToSources();
    }
  }

  canGoBack(): boolean {
    return this.history.length > 0;
  }

  loadMore() {
    const next = this.feed()?.next_url;
    if (!next) return;
    this.loadedPageUrls.set([...this.loadedPageUrls(), next]);
    this.loadFeed(next);
  }

  searchFeed() {
    const q = this.searchQuery().trim();
    const feed = this.feed();
    if (!feed?.search_url || !q) return;
    this.searching.set(true);
    this.loadFeed(feed.search_url, q);
  }

  // ---------- download & read ----------

  downloadEntry(entry: OpdsEntry) {
    const url = entry.acquisition_url;
    if (!url) return;
    const s = new Set(this.downloading());
    s.add(url);
    this.downloading.set(s);
    this.api.acquireOpdsBook(url).subscribe({
      next: (book) => {
        const s2 = new Set(this.downloading());
        s2.delete(url);
        this.downloading.set(s2);
        this.router.navigate(['/reader', book.id]);
      },
      error: (e) => {
        const s2 = new Set(this.downloading());
        s2.delete(url);
        this.downloading.set(s2);
        this.flashError(e?.error?.detail ?? 'Download failed');
      },
    });
  }

  isDownloading(entry: OpdsEntry): boolean {
    return !!entry.acquisition_url && this.downloading().has(entry.acquisition_url);
  }
}
