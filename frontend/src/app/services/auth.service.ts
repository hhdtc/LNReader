import { Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from './api.service';
import { UserInfo } from '../models/book.model';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AuthService {
  user = signal<UserInfo | null>(null);
  loading = signal(true);

  constructor(private api: ApiService, private router: Router) {
    this.checkAuth();
  }

  checkAuth() {
    this.loading.set(true);
    this.api.getUser().subscribe({
      next: (u) => {
        this.user.set(u);
        this.loading.set(false);
      },
      error: () => {
        // Auto-login locally — no OAuth required
        this.api.loginLocal().subscribe({
          next: ({ token }) => {
            localStorage.setItem('auth_token', token);
            this.api.getUser().subscribe({
              next: (u) => { this.user.set(u); this.loading.set(false); },
              error: () => { this.loading.set(false); }
            });
          },
          error: () => { this.loading.set(false); }
        });
      }
    });
  }

  loginWithGoogle() {
    window.location.href = `${environment.apiUrl}/auth/google`;
  }

  loginLocally() {
    this.api.loginLocal().subscribe({
      next: ({ token }) => {
        localStorage.setItem('auth_token', token);
        this.checkAuth();
        this.router.navigate(['/library']);
      },
      error: () => {}
    });
  }

  logout() {
    this.api.logout().subscribe(() => {
      this.user.set(null);
      this.router.navigate(['/login']);
    });
  }

  isAuthenticated(): boolean {
    return this.user() !== null;
  }
}
