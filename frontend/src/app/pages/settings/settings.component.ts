import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { SettingsService } from '../../services/settings.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-settings',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  provider = signal('deepl');
  apiKey = signal('');
  targetLang = signal('en');
  saved = signal(false);
  showKey = signal(false);

  providers = [
    { value: 'deepl', label: 'DeepL', desc: 'High-quality neural translation. Free tier available.' },
    { value: 'google', label: 'Google Translate', desc: 'Google Cloud Translation API.' },
    { value: 'openai', label: 'OpenAI (GPT)', desc: 'Uses GPT-4o-mini for nuanced translation.' },
  ];

  languages = [
    { value: 'en', label: 'English' },
    { value: 'zh', label: 'Chinese (Simplified)' },
    { value: 'ko', label: 'Korean' },
    { value: 'fr', label: 'French' },
    { value: 'de', label: 'German' },
    { value: 'es', label: 'Spanish' },
    { value: 'ja', label: 'Japanese' },
  ];

  constructor(public settings: SettingsService, public auth: AuthService) {}

  ngOnInit() {
    const s = this.settings.settings();
    this.provider.set(s.translation_provider || 'deepl');
    this.apiKey.set(s.translation_api_key || '');
    this.targetLang.set(s.translation_target_lang || 'en');
  }

  save() {
    this.settings.update({
      translation_provider: this.provider(),
      translation_api_key: this.apiKey(),
      translation_target_lang: this.targetLang(),
    });
    this.saved.set(true);
    setTimeout(() => this.saved.set(false), 2000);
  }

  getProviderLabel(v: string) {
    return this.providers.find(p => p.value === v)?.label ?? v;
  }
}
