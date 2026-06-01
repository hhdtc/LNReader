import {
  Component, OnInit, OnDestroy, ViewChild, ElementRef, signal, computed
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import {
  Book, ChapterSummary, ChapterAudioInfo, AudioStatusResponse, ListeningProgress
} from '../../models/book.model';
@Component({
  selector: 'app-listen',
  imports: [CommonModule, RouterLink],
  templateUrl: './listen.component.html',
  styleUrls: ['./listen.component.scss'],
})
export class ListenComponent implements OnInit, OnDestroy {
  @ViewChild('audioEl') audioEl!: ElementRef<HTMLAudioElement>;

  book = signal<Book | null>(null);
  chapterIndex = signal<ChapterSummary[]>([]);
  chapterAudio = signal<ChapterAudioInfo[]>([]);
  currentChapter = signal(0);
  isPlaying = signal(false);
  currentTime = signal(0);
  duration = signal(0);
  playbackRate = signal(1);
  loading = signal(true);

  chapterAudioMap = computed(() => {
    const map = new Map<number, ChapterAudioInfo>();
    for (const c of this.chapterAudio()) map.set(c.chapter_index, c);
    return map;
  });

  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private bookId = 0;

  speeds = [0.75, 1, 1.25, 1.5, 2];

  hasAudioForChapter = computed(() => {
    const idx = this.currentChapter();
    return this.chapterAudio().find(c => c.chapter_index === idx)?.has_audio ?? false;
  });

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService,
    public auth: AuthService
  ) {}

  ngOnInit() {
    this.bookId = Number(this.route.snapshot.paramMap.get('id'));
    Promise.all([
      new Promise<void>(r => this.api.getBook(this.bookId).subscribe(b => { this.book.set(b); r(); })),
      new Promise<void>(r => this.api.getChapterIndex(this.bookId).subscribe(idx => { this.chapterIndex.set(idx); r(); })),
      new Promise<void>(r => this.api.getAudioStatus(this.bookId).subscribe(s => {
        this.chapterAudio.set(s.chapters);
        if (s.job.status === 'running') this.startPolling();
        r();
      })),
      new Promise<void>(r => this.api.getListeningProgress(this.bookId).subscribe(p => {
        this.currentChapter.set(p.chapter_index);
        this._resumePosition = p.position_seconds;
        r();
      })),
    ]).then(() => {
      this.loading.set(false);
      this.loadAudio(this.currentChapter(), true);
    });
  }

  private _resumePosition = 0;

  ngOnDestroy() {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.saveProgress();
  }

  get audio(): HTMLAudioElement {
    return this.audioEl?.nativeElement;
  }

  loadAudio(chapterIndex: number, resume = false) {
    const info = this.chapterAudio().find(c => c.chapter_index === chapterIndex);
    if (!info?.has_audio) return;

    const el = this.audio;
    if (!el) return;

    el.src = this.api.getChapterAudioUrl(this.bookId, chapterIndex);
    el.playbackRate = this.playbackRate();
    el.load();
    this.currentTime.set(0);
    this.duration.set(0);

    el.onloadedmetadata = () => {
      this.duration.set(el.duration);
      if (resume && this._resumePosition > 0 && this._resumePosition < el.duration - 1) {
        el.currentTime = this._resumePosition;
      }
      this._resumePosition = 0;
    };
  }

  togglePlay() {
    const el = this.audio;
    if (!el || !this.hasAudioForChapter()) return;
    if (el.paused) {
      el.play();
      this.isPlaying.set(true);
    } else {
      el.pause();
      this.isPlaying.set(false);
      this.saveProgress();
    }
  }

  onTimeUpdate() {
    const el = this.audio;
    if (!el) return;
    this.currentTime.set(el.currentTime);
    this.scheduleSave();
  }

  onEnded() {
    this.isPlaying.set(false);
    // mark chapter as read
    const idx = this.currentChapter();
    this.api.updateProgress(this.bookId, { chapter_index: idx, page_index: 0, scroll_position: 0 }).subscribe();
    // save progress as start of next chapter
    const next = idx + 1;
    const hasNext = this.chapterAudio().find(c => c.chapter_index === next)?.has_audio;
    if (hasNext) {
      this.currentChapter.set(next);
      this._resumePosition = 0;
      this.api.updateListeningProgress(this.bookId, { chapter_index: next, position_seconds: 0 }).subscribe();
      setTimeout(() => {
        this.loadAudio(next, false);
        this.audio?.play();
        this.isPlaying.set(true);
      }, 300);
    } else {
      this.api.updateListeningProgress(this.bookId, { chapter_index: idx, position_seconds: 0 }).subscribe();
    }
  }

  onDurationChange() {
    this.duration.set(this.audio?.duration ?? 0);
  }

  onSeek(event: Event) {
    const val = +(event.target as HTMLInputElement).value;
    if (this.audio) this.audio.currentTime = val;
    this.currentTime.set(val);
  }

  setSpeed(rate: number) {
    this.playbackRate.set(rate);
    if (this.audio) this.audio.playbackRate = rate;
  }

  prevChapter() {
    const idx = this.currentChapter();
    if (idx <= 0) return;
    const prev = idx - 1;
    this.currentChapter.set(prev);
    this._resumePosition = 0;
    const wasPlaying = !this.audio?.paused;
    this.isPlaying.set(false);
    this.loadAudio(prev, false);
    if (wasPlaying) setTimeout(() => { this.audio?.play(); this.isPlaying.set(true); }, 200);
  }

  nextChapter() {
    const idx = this.currentChapter();
    const next = idx + 1;
    if (next >= (this.book()?.total_chapters ?? 0)) return;
    this.currentChapter.set(next);
    this._resumePosition = 0;
    const wasPlaying = !this.audio?.paused;
    this.isPlaying.set(false);
    this.loadAudio(next, false);
    if (wasPlaying) setTimeout(() => { this.audio?.play(); this.isPlaying.set(true); }, 200);
  }

  jumpToChapter(idx: number) {
    const info = this.chapterAudio().find(c => c.chapter_index === idx);
    if (!info?.has_audio) return;
    this.saveProgress();
    this.currentChapter.set(idx);
    this._resumePosition = 0;
    const wasPlaying = !this.audio?.paused;
    this.isPlaying.set(false);
    this.loadAudio(idx, false);
    if (wasPlaying) setTimeout(() => { this.audio?.play(); this.isPlaying.set(true); }, 200);
  }

  scheduleSave() {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.saveProgress(), 2000);
  }

  saveProgress() {
    const el = this.audio;
    this.api.updateListeningProgress(this.bookId, {
      chapter_index: this.currentChapter(),
      position_seconds: el?.currentTime ?? 0,
    }).subscribe();
  }

  private startPolling() {
    this.pollTimer = setInterval(() => {
      this.api.getAudioStatus(this.bookId).subscribe(s => {
        this.chapterAudio.set(s.chapters);
        if (s.job.status !== 'running') {
          clearInterval(this.pollTimer!);
          this.pollTimer = null;
        }
      });
    }, 10000);
  }

  formatTime(secs: number): string {
    if (!isFinite(secs) || isNaN(secs)) return '0:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  chapterTitle(idx: number): string {
    return this.chapterIndex().find(c => c.chapter_index === idx)?.chapter_title ?? `Chapter ${idx + 1}`;
  }

  getChapterDuration(idx: number): string {
    const info = this.chapterAudio().find(c => c.chapter_index === idx);
    if (!info?.duration) return '';
    return this.formatTime(info.duration);
  }
}
