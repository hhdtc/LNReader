import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/library', pathMatch: 'full' },
  {
    path: 'library',
    loadComponent: () => import('./pages/library/library.component').then(m => m.LibraryComponent),
  },
  {
    path: 'opds',
    loadComponent: () => import('./pages/opds/opds.component').then(m => m.OpdsComponent),
  },
  {
    path: 'reader/:id',
    loadComponent: () => import('./pages/reader/reader.component').then(m => m.ReaderComponent),
  },
  {
    path: 'settings',
    loadComponent: () => import('./pages/settings/settings.component').then(m => m.SettingsComponent),
  },
  {
    path: 'listen/:id',
    loadComponent: () => import('./pages/listen/listen.component').then(m => m.ListenComponent),
  },
  { path: '**', redirectTo: '/library' },
];
