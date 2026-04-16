import { Injectable } from '@angular/core';
import { ChapterContent } from '../models/book.model';

interface CacheEntry {
  data: ChapterContent;
  chapterIndex: number;
}

@Injectable({ providedIn: 'root' })
export class ChapterCacheService {
  private cache = new Map<string, CacheEntry>();
  private maxSize = 5;

  private makeKey(bookId: number, chapter: number, annotate: boolean): string {
    return `${bookId}:${chapter}:${annotate}`;
  }

  get(bookId: number, chapter: number, annotate: boolean): ChapterContent | null {
    const entry = this.cache.get(this.makeKey(bookId, chapter, annotate));
    return entry?.data ?? null;
  }

  set(bookId: number, chapter: number, annotate: boolean, data: ChapterContent): void {
    this.cache.set(this.makeKey(bookId, chapter, annotate), { data, chapterIndex: chapter });
    this.evictIfNeeded(chapter);
  }

  clear(): void {
    this.cache.clear();
  }

  private evictIfNeeded(currentChapter: number): void {
    while (this.cache.size > this.maxSize) {
      let farthestKey = '';
      let farthestDist = -1;
      for (const [key, entry] of this.cache) {
        const dist = Math.abs(entry.chapterIndex - currentChapter);
        if (dist > farthestDist) {
          farthestDist = dist;
          farthestKey = key;
        }
      }
      if (farthestKey) this.cache.delete(farthestKey);
      else break;
    }
  }
}
