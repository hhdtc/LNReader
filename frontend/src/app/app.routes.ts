import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/library', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./pages/auth/auth.component').then(m => m.AuthComponent),
  },
  {
    path: 'auth/callback',
    loadComponent: () => import('./pages/auth/auth-callback.component').then(m => m.AuthCallbackComponent),
  },
  {
    path: 'library',
    loadComponent: () => import('./pages/library/library.component').then(m => m.LibraryComponent),
    canActivate: [authGuard],
  },
  {
    path: 'reader/:id',
    loadComponent: () => import('./pages/reader/reader.component').then(m => m.ReaderComponent),
    canActivate: [authGuard],
  },
  {
    path: 'settings',
    loadComponent: () => import('./pages/settings/settings.component').then(m => m.SettingsComponent),
    canActivate: [authGuard],
  },
  {
    path: 'listen/:id',
    loadComponent: () => import('./pages/listen/listen.component').then(m => m.ListenComponent),
    canActivate: [authGuard],
  },
  { path: '**', redirectTo: '/library' },
];
