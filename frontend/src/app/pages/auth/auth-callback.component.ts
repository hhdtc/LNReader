import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-auth-callback',
  template: `
    <div style="display:flex;align-items:center;justify-content:center;height:100vh;background:#0b0b0b;color:#00d1ff;font-family:monospace;letter-spacing:.2em;font-size:.8rem;gap:12px">
      <div class="spinner"></div>
      <span>AUTHENTICATING...</span>
    </div>
  `,
  styles: [`
    @keyframes spin { to { transform: rotate(360deg); } }
    .spinner {
      width: 24px; height: 24px;
      border: 2px solid rgba(0,209,255,0.2);
      border-top-color: #00d1ff;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
  `]
})
export class AuthCallbackComponent implements OnInit {
  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private auth: AuthService
  ) {}

  ngOnInit() {
    const token = this.route.snapshot.queryParamMap.get('token');
    const error = this.route.snapshot.queryParamMap.get('error');

    if (error || !token) {
      this.router.navigate(['/login'], { queryParams: { error: error || 'auth_failed' } });
      return;
    }

    // Store token and re-check auth
    localStorage.setItem('auth_token', token);
    this.auth.checkAuth();
    this.router.navigate(['/library']);
  }
}
