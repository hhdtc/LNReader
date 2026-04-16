import { Component, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Book } from '../../models/book.model';

@Component({
  selector: 'app-library',
  imports: [CommonModule, RouterLink],
  templateUrl: './library.component.html',
  styleUrls: ['./library.component.scss'],
})
export class LibraryComponent implements OnInit {
  books = signal<Book[]>([]);
  loading = signal(false);
  uploading = signal(false);
  error = signal('');
  dragOver = signal(false);

  constructor(
    public auth: AuthService,
    private api: ApiService,
    private router: Router
  ) {}

  ngOnInit() {
    this.loadBooks();
  }

  loadBooks() {
    this.loading.set(true);
    this.api.getBooks().subscribe({
      next: (b) => { this.books.set(b); this.loading.set(false); },
      error: () => { this.loading.set(false); }
    });
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
    this.api.deleteBook(book.id).subscribe(() => {
      this.books.update(b => b.filter(x => x.id !== book.id));
    });
  }

  getCoverUrl(book: Book): string {
    if (!book.cover_path) return '';
    return this.api.getCoverUrl(book.id);
  }

  formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }
}
