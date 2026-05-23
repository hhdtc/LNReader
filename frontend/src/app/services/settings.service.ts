import { Injectable, signal } from '@angular/core';
import { ApiService } from './api.service';
import { UserSettings } from '../models/book.model';

const DEFAULTS: UserSettings = {
  translation_provider: 'deepl',
  translation_api_key: '',
  translation_target_lang: 'en',
  bg_color: '#0b0b0b',
  font_size: 18,
  font_family: 'Space Grotesk',
  page_width: 75,
  view_mode: 'scroll',
  google_user_email: '',
  google_user_name: '',
  google_user_picture: '',
  voicebox_url: 'http://host.docker.internal',
  voicebox_port: 17493,
  voicebox_profile_id: '',
  voicebox_language: 'en',
  voicebox_model_size: '1.7B',
};

@Injectable({ providedIn: 'root' })
export class SettingsService {
  settings = signal<UserSettings>({ ...DEFAULTS });

  constructor(private api: ApiService) {
    this.load();
  }

  load() {
    this.api.getSettings().subscribe({
      next: (s) => this.settings.set(s),
      error: () => {}
    });
  }

  update(data: Partial<UserSettings>) {
    this.api.updateSettings(data).subscribe({
      next: (s) => this.settings.set(s),
      error: () => {}
    });
  }
}
