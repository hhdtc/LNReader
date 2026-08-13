import {
  Component, OnInit, OnDestroy, signal,
  HostListener, ElementRef, ViewChild, ViewChildren, QueryList, computed, AfterViewChecked,
  Injector, afterNextRender
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ApiService } from '../../services/api.service';
import { SettingsService } from '../../services/settings.service';
import { ChapterCacheService } from '../../services/chapter-cache.service';
import { Book, ChapterContent, ChapterSummary } from '../../models/book.model';

const BG_PRESETS = [
  { label: 'Dark', value: '#0b0b0b' },
  { label: 'Dark Gray', value: '#1a1a1a' },
  { label: 'Sepia', value: '#f4ecd8' },
  { label: 'Warm Gray', value: '#e8e4df' },
  { label: 'Night Blue', value: '#0d1117' },
  { label: 'White', value: '#ffffff' },
];

@Component({
  selector: 'app-reader',
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './reader.component.html',
  styleUrls: ['./reader.component.scss'],
})
export class ReaderComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('viewportRef') viewportRef!: ElementRef<HTMLDivElement>;
  @ViewChild('virtualHostRef') virtualHostRef?: ElementRef<HTMLDivElement>;
  @ViewChildren('virtualBlockRef') virtualBlockRefs?: QueryList<ElementRef<HTMLDivElement>>;

  book = signal<Book | null>(null);
  chapter = signal<ChapterContent | null>(null);
  loading = signal(false);
  bookId = 0;

  currentChapter = signal(0);
  annotateJP = signal(false);
  showSettings = signal(false);
  showTranslate = signal(false);
  showChapterPicker = signal(false);
  selectedText = signal('');
  translatedText = signal('');
  translating = signal(false);
  translateError = signal('');
  chapterIndexLoading = signal(false);
  chapterSummaries = signal<ChapterSummary[]>([]);

  bgColor = signal('#0b0b0b');
  bgPresets = BG_PRESETS;
  fontSize = signal(18);
  fontFamily = signal('Space Grotesk');
  pageWidthPct = signal(75);
  lineHeight = signal(1.9);
  widthOptions = [60, 70, 80, 90];

  private pendingScrollRestore = -1;
  private pendingPageRestore = -1;

  // View mode: 'scroll' = long page, 'paginate' = paginated
  viewMode = signal<'scroll' | 'paginate'>('scroll');
  currentPage = signal(0);
  totalPages = signal(1);
  pagesContent = signal<string[]>([]);
  private needsPageRecalc = false;
  private goToLastPageAfterRecalc = false;

  virtualBlocks: string[] = [];
  visibleStart = signal(0);
  visibleEnd = signal(-1);
  topSpacerPx = signal(0);
  bottomSpacerPx = signal(0);
  private blockHeights: number[] = [];
  private prefixHeights: number[] = [0];
  private needsVirtualMeasure = false;
  private readonly virtualOverscanPx = 900;

  fontOptions = ['Space Grotesk', 'Georgia', 'Source Han Sans', 'Noto Serif JP', 'Roboto', 'System Default'];

  isLight = computed(() => {
    const hex = this.bgColor();
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 > 128;
  });

  textColor = computed(() => this.isLight() ? '#1a1a1a' : '#f0f0f0');

  private saveTimer: any;

  // TTS
  ttsMode = signal(false);
  ttsSentences = signal<string[]>([]);
  ttsContent = signal('');
  ttsCurrentIdx = signal(-1);
  ttsPlaying = signal(false);
  private ttsAudioCache = new Map<number, string>(); // idx -> base64
  private ttsFetchingSet = new Set<number>();
  private ttsAudioElement: HTMLAudioElement | null = null;
  private ttsRefAudioB64 = '';
  private ttsPageRanges: Array<[number, number]> = [];

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    public settings: SettingsService,
    private sanitizer: DomSanitizer,
    private chapterCache: ChapterCacheService,
    private injector: Injector
  ) {}

  ngOnInit() {
    this.bookId = Number(this.route.snapshot.paramMap.get('id'));
    const s = this.settings.settings();
    this.bgColor.set(s.bg_color || '#0b0b0b');
    this.fontSize.set(s.font_size || 18);
    this.fontFamily.set(s.font_family || 'Space Grotesk');
    const pw = s.page_width || 720;
    this.pageWidthPct.set(pw <= 100 ? pw : 75);
    if (s.view_mode === 'paginate') {
      this.viewMode.set('paginate');
      this.needsPageRecalc = true;
    }

    this.api.getBook(this.bookId).subscribe({ next: (b) => this.book.set(b) });
    this.loadChapterIndex();
    this.api.getProgress(this.bookId).subscribe({
      next: (p) => {
        this.currentChapter.set(p.chapter_index || 0);
        this.pendingScrollRestore = p.scroll_position || 0;
        this.pendingPageRestore = p.page_index || 0;
        this.loadChapter(p.chapter_index || 0);
      },
      error: () => this.loadChapter(0)
    });
  }

  ngOnDestroy() {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveProgress();
    this.chapterCache.clear();
    this.stopTTS();
  }

  ngAfterViewChecked() {
    if (this.needsPageRecalc && this.viewMode() === 'paginate' && this.viewportRef) {
      this.needsPageRecalc = false;
      setTimeout(() => this.recalcPages(), 0);
    }

    if (this.needsVirtualMeasure && this.viewMode() === 'scroll') {
      this.needsVirtualMeasure = false;
      this.measureVisibleBlocks();
    }
  }

  loadChapter(index: number) {
    this.translatedText.set('');
    const annotate = this.annotateJP();

    const cached = this.chapterCache.get(this.bookId, index, annotate);
    if (cached) {
      this.applyChapter(cached, index);
      this.prefetchAdjacent(index, annotate);
      return;
    }

    this.loading.set(true);
    this.api.getChapter(this.bookId, index, annotate).subscribe({
      next: (c) => {
        this.chapterCache.set(this.bookId, index, annotate, c);
        this.applyChapter(c, index);
        this.loading.set(false);
        this.prefetchAdjacent(index, annotate);
      },
      error: () => this.loading.set(false)
    });
  }

  private applyChapter(c: ChapterContent, index: number): void {
    if (this.ttsMode()) this.stopTTS();
    this.chapter.set(c);
    this.currentChapter.set(index);
    this.rememberChapterSummary(index, c.chapter_title);
    this.currentPage.set(0);
    this.needsPageRecalc = true;

    if (this.viewMode() === 'scroll') {
      this.initScrollVirtualization(c.content);
    } else {
      this.resetVirtualization();
      afterNextRender(() => this.recalcPages(), { injector: this.injector });
    }

    const scrollTarget = this.pendingScrollRestore;
    this.pendingScrollRestore = -1;
    if (scrollTarget > 0) {
      setTimeout(() => window.scrollTo({ top: scrollTarget }), 50);
    } else {
      setTimeout(() => this.scrollToTop(), 50);
    }
    this.scheduleSave();
  }

  private loadChapterIndex(force = false): void {
    if (!this.bookId || this.chapterIndexLoading()) return;
    if (!force && this.chapterSummaries().length > 0) return;

    this.chapterIndexLoading.set(true);
    this.api.getChapterIndex(this.bookId).subscribe({
      next: (chapters) => {
        this.chapterSummaries.set(chapters);
        this.chapterIndexLoading.set(false);
      },
      error: () => {
        this.chapterIndexLoading.set(false);
      }
    });
  }

  private rememberChapterSummary(index: number, title: string): void {
    const normalized = (title || '').trim() || `Chapter ${index + 1}`;
    const current = this.chapterSummaries();
    const found = current.find((chapter) => chapter.chapter_index === index);

    if (found) {
      if (found.chapter_title !== normalized) {
        this.chapterSummaries.set(
          current.map((chapter) => chapter.chapter_index === index ? { ...chapter, chapter_title: normalized } : chapter)
        );
      }
      return;
    }

    this.chapterSummaries.set([
      ...current,
      { chapter_index: index, chapter_title: normalized }
    ].sort((a, b) => a.chapter_index - b.chapter_index));
  }

  toggleChapterPicker(event?: MouseEvent): void {
    event?.stopPropagation();
    const open = !this.showChapterPicker();
    this.showChapterPicker.set(open);
    if (open) this.loadChapterIndex();
  }

  jumpToChapter(index: number): void {
    this.showChapterPicker.set(false);
    if (index === this.currentChapter()) return;
    this.loadChapter(index);
  }

  private prefetchAdjacent(current: number, annotate: boolean): void {
    const total = this.chapter()?.total_chapters ?? 1;

    if (current + 1 < total && !this.chapterCache.get(this.bookId, current + 1, annotate)) {
      this.api.getChapter(this.bookId, current + 1, annotate).subscribe({
        next: (c) => this.chapterCache.set(this.bookId, current + 1, annotate, c),
        error: () => {}
      });
    }

    if (current - 1 >= 0 && !this.chapterCache.get(this.bookId, current - 1, annotate)) {
      this.api.getChapter(this.bookId, current - 1, annotate).subscribe({
        next: (c) => this.chapterCache.set(this.bookId, current - 1, annotate, c),
        error: () => {}
      });
    }
  }
  // Stable SafeHtml per content string: bypassSecurityTrustHtml returns a new
  // object each call, which would make Angular re-set innerHTML on every CD
  // cycle and wipe imperatively-applied classes (TTS highlight).
  private safeHtmlCache: Record<string, SafeHtml> = {};

  sanitizeContent(html: string): SafeHtml {
    let safe = this.safeHtmlCache[html];
    if (!safe) {
      safe = this.sanitizer.bypassSecurityTrustHtml(html);
      this.safeHtmlCache[html] = safe;
    }
    return safe;
  }

  prevChapter() {
    if (this.currentChapter() > 0) this.loadChapter(this.currentChapter() - 1);
  }

  nextChapter() {
    const total = this.chapter()?.total_chapters ?? 1;
    if (this.currentChapter() < total - 1) this.loadChapter(this.currentChapter() + 1);
  }

  toggleAnnotate() {
    this.annotateJP.update(v => !v);
    this.loadChapter(this.currentChapter());
  }

  scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  toggleViewMode() {
    if (this.viewMode() === 'scroll') {
      this.viewMode.set('paginate');
      this.currentPage.set(0);
      this.needsPageRecalc = true;
      this.resetVirtualization();
      window.scrollTo({ top: 0 });
    } else {
      this.viewMode.set('scroll');
      if (this.chapter()) {
        this.initScrollVirtualization(this.chapter()!.content);
      }
    }
    this.settings.update({ view_mode: this.viewMode() });
  }

  get visibleBlockIndices(): number[] {
    const start = this.visibleStart();
    const end = this.visibleEnd();
    if (end < start || start < 0) return [];
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  }

  totalVirtualHeight(): number {
    if (this.prefixHeights.length === 0) return 0;
    return this.prefixHeights[this.prefixHeights.length - 1];
  }

  private resetVirtualization(): void {
    this.virtualBlocks = [];
    this.blockHeights = [];
    this.prefixHeights = [0];
    this.visibleStart.set(0);
    this.visibleEnd.set(-1);
    this.topSpacerPx.set(0);
    this.bottomSpacerPx.set(0);
    this.needsVirtualMeasure = false;
  }

  private initScrollVirtualization(content: string): void {
    this.virtualBlocks = this.splitHtmlIntoChunks(content);
    this.blockHeights = this.virtualBlocks.map((block) => this.estimateBlockHeight(block));
    this.rebuildPrefixHeights();
    this.visibleStart.set(0);
    this.visibleEnd.set(Math.min(this.virtualBlocks.length - 1, 8));
    this.topSpacerPx.set(0);
    this.bottomSpacerPx.set(Math.max(0, this.totalVirtualHeight() - (this.prefixHeights[this.visibleEnd() + 1] || 0)));

    setTimeout(() => {
      this.updateVirtualWindow(true);
    }, 0);
  }

  private splitHtmlIntoChunks(content: string): string[] {
    const temp = document.createElement('div');
    temp.innerHTML = content;

    const children = Array.from(temp.childNodes).filter((node) => {
      return node.nodeType !== Node.TEXT_NODE || !!node.textContent?.trim();
    });

    if (children.length === 0) return [content];

    const nodesToHtml = (nodes: Node[]): string => {
      const wrapper = document.createElement('div');
      nodes.forEach((node) => wrapper.appendChild(node.cloneNode(true)));
      return wrapper.innerHTML;
    };

    const chunks: string[] = [];
    let currentChunk: Node[] = [];
    let currentChars = 0;
    const maxNodesPerChunk = 14;
    const targetCharsPerChunk = 2600;

    for (const child of children) {
      const childChars = (child.textContent || '').trim().length;
      const normalizedChars = Math.max(childChars, 80);

      if (
        currentChunk.length > 0 &&
        (currentChunk.length >= maxNodesPerChunk || currentChars + normalizedChars > targetCharsPerChunk)
      ) {
        chunks.push(nodesToHtml(currentChunk));
        currentChunk = [];
        currentChars = 0;
      }

      currentChunk.push(child);
      currentChars += normalizedChars;
    }

    if (currentChunk.length > 0) {
      chunks.push(nodesToHtml(currentChunk));
    }

    return chunks.length > 0 ? chunks : [content];
  }

  private estimateBlockHeight(html: string): number {
    const plainText = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    const contentWidth = Math.max(320, window.innerWidth * this.pageWidthPct() / 100 - 48);
    const avgCharWidth = Math.max(6, this.fontSize() * 0.55);
    const charsPerLine = Math.max(12, Math.floor(contentWidth / avgCharWidth));
    const lines = Math.max(1, Math.ceil(plainText.length / charsPerLine));
    const base = lines * this.fontSize() * this.lineHeight();

    const headingBoost = (html.match(/<h[1-6][\s>]/gi)?.length ?? 0) * this.fontSize() * 1.8;
    const mediaBoost = (html.match(/<(img|table|blockquote|pre)[\s>]/gi)?.length ?? 0) * this.fontSize() * 7.5;
    return Math.max(this.fontSize() * this.lineHeight() * 1.2, base + headingBoost + mediaBoost + 18);
  }

  private rebuildPrefixHeights(): void {
    const prefix: number[] = [0];
    for (const height of this.blockHeights) {
      prefix.push(prefix[prefix.length - 1] + height);
    }
    this.prefixHeights = prefix;
  }

  private findBlockIndexAtOffset(offset: number): number {
    if (this.blockHeights.length === 0) return -1;
    if (offset <= 0) return 0;

    let low = 0;
    let high = this.blockHeights.length - 1;

    while (low <= high) {
      const mid = (low + high) >> 1;
      const start = this.prefixHeights[mid];
      const end = this.prefixHeights[mid + 1];

      if (offset < start) {
        high = mid - 1;
      } else if (offset >= end) {
        low = mid + 1;
      } else {
        return mid;
      }
    }

    return Math.max(0, Math.min(this.blockHeights.length - 1, low));
  }

  private updateVirtualWindow(markForMeasure: boolean): void {
    if (!this.virtualHostRef || this.virtualBlocks.length === 0) return;

    const host = this.virtualHostRef.nativeElement;
    const hostTop = host.getBoundingClientRect().top + window.scrollY;
    const viewportTop = Math.max(0, window.scrollY - hostTop);
    const viewportBottom = viewportTop + window.innerHeight;
    const startOffset = Math.max(0, viewportTop - this.virtualOverscanPx);
    const endOffset = Math.max(0, viewportBottom + this.virtualOverscanPx);

    const nextStart = this.findBlockIndexAtOffset(startOffset);
    const nextEnd = this.findBlockIndexAtOffset(endOffset);

    this.visibleStart.set(nextStart);
    this.visibleEnd.set(Math.max(nextStart, nextEnd));

    const topSpacer = this.prefixHeights[nextStart] || 0;
    const consumed = this.prefixHeights[Math.max(nextStart, nextEnd) + 1] || this.totalVirtualHeight();
    const bottomSpacer = Math.max(0, this.totalVirtualHeight() - consumed);

    this.topSpacerPx.set(topSpacer);
    this.bottomSpacerPx.set(bottomSpacer);

    if (markForMeasure) {
      this.needsVirtualMeasure = true;
    }
  }

  private measureVisibleBlocks(): void {
    if (!this.virtualBlockRefs || this.virtualBlockRefs.length === 0) return;

    let changed = false;
    for (const ref of this.virtualBlockRefs.toArray()) {
      const el = ref.nativeElement;
      const idx = Number(el.getAttribute('data-idx'));
      if (Number.isNaN(idx) || idx < 0 || idx >= this.blockHeights.length) continue;

      const measured = Math.ceil(el.getBoundingClientRect().height);
      if (measured > 0 && Math.abs(measured - this.blockHeights[idx]) > 2) {
        this.blockHeights[idx] = measured;
        changed = true;
      }
    }

    if (changed) {
      this.rebuildPrefixHeights();
      this.updateVirtualWindow(false);
    }
  }

  private refreshScrollVirtualizationLayout(): void {
    if (this.viewMode() !== 'scroll' || this.virtualBlocks.length === 0) return;
    this.blockHeights = this.virtualBlocks.map((block) => this.estimateBlockHeight(block));
    this.rebuildPrefixHeights();
    this.updateVirtualWindow(true);
  }

  recalcPages() {
    if (!this.viewportRef || !this.chapter()) return;
    const viewport = this.viewportRef.nativeElement as HTMLDivElement;
    const vpHeight = viewport.clientHeight;
    if (vpHeight <= 0) return;

    const content =
      this.ttsMode() && this.ttsContent() ? this.ttsContent() : this.chapter()!.content;

    // Hidden measurer with same styles as reading area
    const measurer = document.createElement('div');
    const pxWidth = Math.round(window.innerWidth * this.pageWidthPct() / 100);
    measurer.style.cssText = `
      position:absolute; visibility:hidden; z-index:-1;
      width:${pxWidth}px; max-width:${pxWidth}px;
      font-size:${this.fontSize()}px;
      font-family:${this.fontFamily()}, Georgia, serif;
      line-height:${this.lineHeight()};
      padding:40px 24px; box-sizing:border-box;
    `;
    document.body.appendChild(measurer);

    // Parse chapter HTML into top-level nodes
    const temp = document.createElement('div');
    temp.innerHTML = content;
    const children = Array.from(temp.childNodes);

    const nodesToHtml = (nodes: Node[]): string => {
      const d = document.createElement('div');
      nodes.forEach(n => d.appendChild(n.cloneNode(true)));
      return d.innerHTML;
    };

    const pages: string[] = [];
    let pageNodes: Node[] = [];

    for (const child of children) {
      // Skip empty text nodes
      if (child.nodeType === Node.TEXT_NODE && !child.textContent?.trim()) continue;

      const testNodes = [...pageNodes, child];
      measurer.innerHTML = nodesToHtml(testNodes);

      if (measurer.scrollHeight > vpHeight && pageNodes.length > 0) {
        // Current page is full, save it and start new page
        pages.push(nodesToHtml(pageNodes));
        pageNodes = [child];
      } else {
        pageNodes.push(child);
      }
    }

    if (pageNodes.length > 0) {
      pages.push(nodesToHtml(pageNodes));
    }

    document.body.removeChild(measurer);

    if (pages.length === 0) pages.push(content);

    this.pagesContent.set(pages);
    this.ttsPageRanges = this.ttsMode()
      ? pages.map((html) => {
          const d = document.createElement('div');
          d.innerHTML = html;
          const idxs = Array.from(d.querySelectorAll('[data-tts-idx]'))
            .map((el) => Number(el.getAttribute('data-tts-idx')))
            .filter((n) => !Number.isNaN(n));
          if (idxs.length === 0) return [-1, -1] as [number, number];
          return [Math.min(...idxs), Math.max(...idxs)] as [number, number];
        })
      : [];
    this.totalPages.set(pages.length);
    if (this.pendingPageRestore >= 0) {
      const target = Math.min(this.pendingPageRestore, pages.length - 1);
      this.pendingPageRestore = -1;
      this.currentPage.set(target);
    } else if (this.goToLastPageAfterRecalc) {
      this.goToLastPageAfterRecalc = false;
      this.currentPage.set(pages.length - 1);
    } else if (this.currentPage() >= pages.length) {
      this.currentPage.set(pages.length - 1);
    }
  }

  goToPage(page: number) {
    if (page < 0 || page >= this.totalPages()) return;
    this.currentPage.set(page);
    this.scheduleSave();
  }

  nextPage() {
    if (this.currentPage() < this.totalPages() - 1) {
      this.currentPage.update(p => p + 1);
      this.scheduleSave();
    } else {
      this.nextChapter();
    }
  }

  prevPage() {
    if (this.currentPage() > 0) {
      this.currentPage.update(p => p - 1);
      this.scheduleSave();
    } else {
      this.goToLastPageAfterRecalc = true;
      this.prevChapter();
    }
  }

  scheduleSave() {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.saveProgress(), 2000);
  }

  saveProgress() {
    if (!this.bookId) return;
    this.api.updateProgress(this.bookId, {
      chapter_index: this.currentChapter(),
      page_index: this.currentPage(),
      scroll_position: window.scrollY
    }).subscribe();
  }

  @HostListener('window:scroll')
  onScroll() {
    if (this.viewMode() === 'scroll') {
      this.scheduleSave();
      this.updateVirtualWindow(true);
    }
  }

  @HostListener('window:resize')
  onResize() {
    if (this.viewMode() === 'paginate') {
      this.recalcPages();
    } else {
      this.refreshScrollVirtualizationLayout();
    }
  }

  @HostListener('window:keydown', ['$event'])
  onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape' && this.showChapterPicker()) {
      this.showChapterPicker.set(false);
      return;
    }

    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'TEXTAREA') return;
    if (this.viewMode() === 'paginate') {
      // Paginated: left/right navigate pages (overflow into chapters)
      if (e.key === 'ArrowRight') { e.preventDefault(); this.nextPage(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); this.prevPage(); }
    } else {
      // Scroll: up/down scroll the page, left/right switch chapters
      if (e.key === 'ArrowRight') { e.preventDefault(); this.nextChapter(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); this.prevChapter(); }
      // ArrowUp/ArrowDown: let browser handle native scroll
    }
  }

  @HostListener('mouseup')
  onMouseUp() {
    const sel = window.getSelection()?.toString().trim();
    if (sel && sel.length > 0 && sel.length < 1000) {
      this.selectedText.set(sel);
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement | null;
    if (!target?.closest('.chapter-picker')) {
      this.showChapterPicker.set(false);
    }
  }

  onBgChange(value: string) {
    this.bgColor.set(value);
    this.settings.update({ bg_color: value });
  }

  onFontSizeChange(delta: number) {
    const val = Math.max(12, Math.min(30, this.fontSize() + delta));
    this.fontSize.set(val);
    this.settings.update({ font_size: val });
    if (this.viewMode() === 'paginate') {
      this.needsPageRecalc = true;
    } else {
      this.refreshScrollVirtualizationLayout();
    }
  }

  onFontChange(family: string) {
    this.fontFamily.set(family);
    this.settings.update({ font_family: family });
    if (this.viewMode() === 'paginate') {
      this.needsPageRecalc = true;
    } else {
      this.refreshScrollVirtualizationLayout();
    }
  }

  onPageWidthPctChange(pct: number) {
    this.pageWidthPct.set(pct);
    this.settings.update({ page_width: pct });
    if (this.viewMode() === 'paginate') {
      this.needsPageRecalc = true;
    } else {
      this.refreshScrollVirtualizationLayout();
    }
  }

  translateSelected() {
    const text = this.selectedText();
    if (!text) return;
    const s = this.settings.settings();
    if (!s.translation_api_key) {
      this.translateError.set('No API key set. Go to Settings to add one.');
      return;
    }
    this.translating.set(true);
    this.translateError.set('');
    this.api.translate({
      text,
      source_lang: this.book()?.language === 'ja' ? 'ja' : 'auto',
      target_lang: s.translation_target_lang || 'en',
      provider: s.translation_provider || 'deepl',
      api_key: s.translation_api_key
    }).subscribe({
      next: (r) => {
        this.translatedText.set(r.translated_text);
        this.translating.set(false);
      },
      error: () => {
        this.translateError.set('Translation failed. Check your API key.');
        this.translating.set(false);
      }
    });
  }

  clearSelection() {
    this.selectedText.set('');
    this.translatedText.set('');
    this.translateError.set('');
  }

  // ─── TTS ─────────────────────────────────────────────────────────────────

  toggleTTS(): void {
    if (this.ttsMode()) {
      this.stopTTS();
    } else {
      this.startTTS();
    }
  }

  private startTTS(): void {
    const content = this.chapter()?.content;
    if (!content) return;
    const wrapped = this.wrapContentForTts(content);
    if (!wrapped) return;
    this.ttsAudioCache.clear();
    this.ttsFetchingSet.clear();
    this.ttsSentences.set(wrapped.sentences);
    this.ttsContent.set(wrapped.html);
    this.ttsMode.set(true);
    this.ttsCurrentIdx.set(0);
    this.ttsPlaying.set(true);
    if (this.viewMode() === 'paginate') {
      this.needsPageRecalc = true;
    }


    const doStart = () => {
      this.bufferAhead(0);
      this.fetchAndPlay(0);
    };

    if (this.ttsRefAudioB64) {
      doStart();
    } else {
      fetch('/ref/tts_ref.wav')
        .then(r => r.arrayBuffer())
        .then(buf => {
          const bytes = new Uint8Array(buf);
          let binary = '';
          for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
          this.ttsRefAudioB64 = btoa(binary);
          doStart();
        })
        .catch(() => {
          this.stopTTS();
          console.error('Failed to load TTS reference audio from /ref/tts_ref.wav');
        });
    }
  }

  stopTTS(): void {
    if (this.ttsAudioElement) {
      this.ttsAudioElement.onended = null;
      this.ttsAudioElement.pause();
      this.ttsAudioElement = null;
    }
    this.ttsMode.set(false);
    this.ttsContent.set('');
    this.ttsSentences.set([]);
    this.ttsCurrentIdx.set(-1);
    this.ttsPlaying.set(false);
    this.clearTtsHighlight();
    if (this.viewMode() === 'paginate') {
      this.needsPageRecalc = true;
    }

  }

  onTtsSentenceClick(idx: number): void {
    if (this.ttsAudioElement) {
      this.ttsAudioElement.onended = null;
      this.ttsAudioElement.pause();
      this.ttsAudioElement = null;
    }
    this.ttsCurrentIdx.set(idx);
    this.ttsPlaying.set(true);
    this.refreshTtsHighlight();
    this.bufferAhead(idx);
    this.fetchAndPlay(idx);
  }

  private fetchAndPlay(idx: number): void {
    if (this.ttsAudioCache.has(idx)) {
      this.playFromCache(idx);
      return;
    }
    if (!this.ttsFetchingSet.has(idx)) {
      this.fetchSentenceAudio(idx);
    }
    // playFromCache will be called when fetch completes
  }

  private bufferAhead(fromIdx: number): void {
    const sentences = this.ttsSentences();
    for (let i = fromIdx + 1; i <= fromIdx + 3 && i < sentences.length; i++) {
      if (!this.ttsAudioCache.has(i) && !this.ttsFetchingSet.has(i)) {
        this.fetchSentenceAudio(i);
      }
    }
  }

  private fetchSentenceAudio(idx: number): void {
    const sentences = this.ttsSentences();
    if (idx < 0 || idx >= sentences.length) return;
    this.ttsFetchingSet.add(idx);
    this.api.tts(this.cleanTextForTTS(sentences[idx]), this.ttsRefAudioB64, this.settings.settings().tts_language || 'zh').subscribe({
      next: (r) => {
        this.ttsFetchingSet.delete(idx);
        this.ttsAudioCache.set(idx, r.audio_base64);
        // If this is the sentence we're waiting to play, play it now
        if (idx === this.ttsCurrentIdx() && this.ttsPlaying() && !this.ttsAudioElement) {
          this.playFromCache(idx);
        }
      },
      error: () => {
        this.ttsFetchingSet.delete(idx);
        // Skip errored sentence and advance
        if (idx === this.ttsCurrentIdx() && this.ttsPlaying()) {
          this.advanceToNext(idx);
        }
      }
    });
  }

  private playFromCache(idx: number): void {
    const b64 = this.ttsAudioCache.get(idx);
    if (!b64) return;
    if (this.ttsAudioElement) {
      this.ttsAudioElement.onended = null;
      this.ttsAudioElement.pause();
    }
    const audio = new Audio(`data:audio/wav;base64,${b64}`);
    this.ttsAudioElement = audio;
    audio.onended = () => {
      this.ttsAudioCache.delete(idx);
      this.ttsAudioElement = null;
      this.advanceToNext(idx);
    };
    audio.play().catch(() => {
      this.ttsAudioElement = null;
      this.advanceToNext(idx);
    });
    this.refreshTtsHighlight();
    this.scrollToTtsSentence(idx);
  }

  private advanceToNext(idx: number): void {
    if (!this.ttsMode()) return;
    const next = idx + 1;
    if (next < this.ttsSentences().length) {
      this.ttsCurrentIdx.set(next);
      this.bufferAhead(next);
      this.fetchAndPlay(next);
    } else {
      this.ttsPlaying.set(false);
    }
  }

  private scrollToTtsSentence(idx: number): void {
    if (this.viewMode() === 'paginate') {
      const page = this.findTtsPage(idx);
      if (page >= 0 && page !== this.currentPage()) {
        this.currentPage.set(page);
        this.scheduleSave();
      }
      setTimeout(() => this.refreshTtsHighlight(), 0);
      return;
    }
    setTimeout(() => {
      const el = document.querySelector(`[data-tts-idx="${idx}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 0);
  }

  private cleanTextForTTS(text: string): string {
    return text
      // Remove Japanese/Chinese bracket-style quotation marks and brackets
      .replace(/[「」『』【】《》〈〉〔〕〖〗〘〙〚〛]/g, '')
      // Remove other decorative punctuation that confuses TTS
      .replace(/[・＊※◆◇■□▲△▼▽○●◎★☆]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  onTtsContentClick(event: MouseEvent): void {
    if (!this.ttsMode()) return;
    const target = event.target as HTMLElement;
    const el = target.closest ? (target.closest('[data-tts-idx]') as HTMLElement | null) : null;
    if (!el) return;
    const idx = Number(el.getAttribute('data-tts-idx'));
    if (!Number.isNaN(idx)) this.onTtsSentenceClick(idx);
  }

  private refreshTtsHighlight(): void {
    this.clearTtsHighlight();
    if (!this.ttsMode()) return;
    const idx = this.ttsCurrentIdx();
    if (idx < 0) return;
    document.querySelector(`[data-tts-idx="${idx}"]`)?.classList.add('tts-active');
  }

  private clearTtsHighlight(): void {
    document
      .querySelectorAll('.tts-s.tts-active')
      .forEach((el) => el.classList.remove('tts-active'));
  }

  private findTtsPage(idx: number): number {
    for (let i = 0; i < this.ttsPageRanges.length; i++) {
      const [min, max] = this.ttsPageRanges[i];
      if (min <= idx && idx <= max) return i;
    }
    return -1;
  }

  private wrapContentForTts(content: string): { html: string; sentences: string[] } | null {
    // Wrap each sentence in the chapter HTML with a span carrying a
    // data-tts-idx, so the original layout is preserved and TTS can
    // highlight/scroll in place. Furigana (rt) text is skipped: TTS
    // should read the surface characters, not the reading annotation.
    const temp = document.createElement('div');
    temp.innerHTML = content;

    const sentences: string[] = [];
    const walker = document.createTreeWalker(temp, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        const parent = node.parentElement;
        if (!parent || parent.closest('script, style, rt')) return NodeFilter.FILTER_REJECT;
        return (node.textContent || '').trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });

    const textNodes: Text[] = [];
    let node: Node | null;
    while ((node = walker.nextNode())) {
      textNodes.push(node as Text);
    }

    let idx = 0;
    for (const textNode of textNodes) {
      const parts = (textNode.textContent || '')
        .split(/(?<=[。！？])|(?<=[.!?])\s+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 1);
      if (parts.length === 0) continue;

      const frag = document.createDocumentFragment();
      for (const part of parts) {
        const span = document.createElement('span');
        span.className = 'tts-s';
        span.setAttribute('data-tts-idx', String(idx));
        span.textContent = part;
        frag.appendChild(span);
        sentences.push(part);
        idx++;
      }
      textNode.parentNode?.replaceChild(frag, textNode);
    }

    if (sentences.length === 0) return null;
    return { html: temp.innerHTML, sentences };
  }

  get progress(): number {
    const total = this.chapter()?.total_chapters ?? 1;
    return Math.round(((this.currentChapter() + 1) / total) * 100);
  }
}
