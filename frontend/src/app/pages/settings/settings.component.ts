import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { SettingsService } from '../../services/settings.service';
import { AuthService } from '../../services/auth.service';
import { ApiService } from '../../services/api.service';
import { VoiceboxProfile } from '../../models/book.model';

@Component({
  selector: 'app-settings',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  // Translation
  provider = signal('deepl');
  apiKey = signal('');
  targetLang = signal('en');
  saved = signal(false);
  showKey = signal(false);

  // Voicebox
  vbUrl = signal('http://host.docker.internal');
  vbPort = signal(17493);
  vbProfileId = signal('');
  vbLanguage = signal('en');
  vbModelSize = signal('1.7B');
  vbProfiles = signal<VoiceboxProfile[]>([]);
  vbProfilesLoading = signal(false);
  vbProfilesError = signal('');
  vbLoadingModel = signal(false);
  vbModelStatus = signal('');

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

  vbLanguages = [
    { value: 'en', label: 'English' },
    { value: 'zh', label: 'Chinese' },
  ];

  vbModelSizes = [{ value: '1.7B', label: '1.7B' }];

  constructor(public settings: SettingsService, public auth: AuthService, private api: ApiService) {}

  ngOnInit() {
    const s = this.settings.settings();
    this.provider.set(s.translation_provider || 'deepl');
    this.apiKey.set(s.translation_api_key || '');
    this.targetLang.set(s.translation_target_lang || 'en');
    this.vbUrl.set(s.voicebox_url || 'http://localhost');
    this.vbPort.set(s.voicebox_port || 8000);
    this.vbProfileId.set(s.voicebox_profile_id || '');
    this.vbLanguage.set(s.voicebox_language || 'en');
    this.vbModelSize.set(s.voicebox_model_size || '1.7B');
  }

  save() {
    this.settings.update({
      translation_provider: this.provider(),
      translation_api_key: this.apiKey(),
      translation_target_lang: this.targetLang(),
      voicebox_url: this.vbUrl(),
      voicebox_port: this.vbPort(),
      voicebox_profile_id: this.vbProfileId(),
      voicebox_language: this.vbLanguage(),
      voicebox_model_size: this.vbModelSize(),
    });
    this.saved.set(true);
    setTimeout(() => this.saved.set(false), 2000);
  }

  loadProfiles() {
    this.vbProfilesLoading.set(true);
    this.vbProfilesError.set('');
    this.api.getVoiceboxProfiles(this.vbUrl(), this.vbPort()).subscribe({
      next: (profiles) => {
        this.vbProfiles.set(profiles);
        this.vbProfilesLoading.set(false);
      },
      error: () => {
        this.vbProfilesError.set('Could not connect to Voicebox. Check URL/port.');
        this.vbProfilesLoading.set(false);
      },
    });
  }

  loadModel() {
    this.vbLoadingModel.set(true);
    this.vbModelStatus.set('');
    this.api.loadVoiceboxModel(this.vbUrl(), this.vbPort()).subscribe({
      next: () => {
        this.vbModelStatus.set('ok');
        this.vbLoadingModel.set(false);
      },
      error: () => {
        this.vbModelStatus.set('error');
        this.vbLoadingModel.set(false);
      },
    });
  }

  getProviderLabel(v: string) {
    return this.providers.find(p => p.value === v)?.label ?? v;
  }

  selectVbProfile(value: string) {
    this.vbProfileId.set(value);
    this.settings.update({ voicebox_profile_id: value });
  }

  selectVbLanguage(value: string) {
    this.vbLanguage.set(value);
    this.settings.update({ voicebox_language: value });
  }

  selectVbModelSize(value: string) {
    this.vbModelSize.set(value);
    this.settings.update({ voicebox_model_size: value });
  }

  getSelectedProfileName(): string {
    const id = this.vbProfileId();
    const found = this.vbProfiles().find(p => p.id === id);
    return found ? found.name : id || 'Select a profile';
  }
}
