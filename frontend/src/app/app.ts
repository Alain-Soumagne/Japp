import { Component, computed, inject, signal } from '@angular/core';
import { ApiService, Job } from './api.service';
import { JobView } from './job-view';

const LANGS = [
  { id: 'auto', label: 'Automatique' },
  { id: 'fr', label: 'Français (mots japonais en romaji)' },
  { id: 'ja', label: 'Japonais' },
];

@Component({
  selector: 'app-root',
  imports: [JobView],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly api = inject(ApiService);
  readonly langs = LANGS;
  readonly lang = signal('fr');
  readonly model = signal('');
  readonly prompt = signal('');
  readonly over = signal(false);
  readonly error = signal('');
  readonly showOptions = signal(false);

  readonly models = computed(() => {
    const h = this.api.health();
    return h ? h.llm_choices : [];
  });
  readonly installed = computed(() => new Set(this.api.health()?.ollama.models ?? []));
  readonly warning = computed(() => {
    const h = this.api.health();
    if (!this.api.backendUp()) return 'Le moteur local ne répond pas.';
    if (!h) return '';
    if (!h.gpu.name) return 'Aucun GPU NVIDIA détecté : la transcription sera très lente ou impossible.';
    if (!h.ollama.installed) return "Ollama n'est pas installé : la transcription fonctionne, mais pas la synthèse.";
    return '';
  });

  async onDrop(ev: DragEvent): Promise<void> {
    ev.preventDefault();
    this.over.set(false);
    await this.addFiles(Array.from(ev.dataTransfer?.files ?? []));
  }

  async onPick(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    await this.addFiles(Array.from(input.files ?? []));
    input.value = '';
  }

  private async addFiles(files: File[]): Promise<void> {
    this.error.set('');
    for (const f of files) {
      try {
        await this.api.addFile(f, { lang: this.lang(), model: this.model(), prompt: this.prompt() });
      } catch (e) {
        this.error.set(`Impossible d'ajouter « ${f.name} » : ${(e as Error).message}`);
      }
    }
  }

  readonly ytUrl = signal('');
  readonly ytBusy = signal(false);

  setYt(ev: Event): void {
    this.ytUrl.set((ev.target as HTMLInputElement).value);
  }

  async addYoutube(ev?: Event): Promise<void> {
    ev?.preventDefault();
    const url = this.ytUrl().trim();
    if (!url || this.ytBusy()) return;
    this.error.set('');
    this.ytBusy.set(true);
    try {
      await this.api.addYoutube(url, { lang: this.lang(), model: this.model(), prompt: this.prompt() });
      this.ytUrl.set('');
    } catch (e) {
      const d = (e as { error?: { detail?: string } }).error?.detail;
      this.error.set(typeof d === 'string' ? d : `Impossible d'ajouter ce lien : ${(e as Error).message}`);
    } finally {
      this.ytBusy.set(false);
    }
  }

  readonly needsOllama = computed(() => !!this.api.health() && !this.api.health()!.ollama.installed);

  getOllama(): void {
    const url = 'https://ollama.com/download';
    if (window.native?.openExternal) window.native.openExternal(url);
    else window.open(url, '_blank', 'noopener');
  }

  select(j: Job): void {
    this.api.selectedId.set(j.id);
  }

  statusLabel(j: Job): string {
    switch (j.status) {
      case 'queued': return 'En attente';
      case 'running': return `${Math.round(j.progress * 100)} %`;
      case 'done': return 'Terminé';
      default: return 'Erreur';
    }
  }

  setLang(e: Event): void { this.lang.set((e.target as HTMLSelectElement).value); }
  setModel(e: Event): void { this.model.set((e.target as HTMLSelectElement).value); }
  setPrompt(e: Event): void { this.prompt.set((e.target as HTMLTextAreaElement).value); }
  dragState(v: boolean, ev: DragEvent): void { ev.preventDefault(); this.over.set(v); }
}
