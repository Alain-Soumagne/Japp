import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

export interface Job {
  id: string;
  name: string;
  source: string;
  url?: string;
  lang: string;
  model: string;
  prompt: string;
  status: 'queued' | 'running' | 'done' | 'error';
  stage: string;
  progress: number;
  message: string;
  error: string | null;
  created: number;
  updated: number;
  files: string[];
  info: { language?: string; duration?: number };
}

export interface Health {
  ok: boolean;
  gpu: { name: string | null; vram_total_mb?: number; vram_used_mb?: number };
  whisper_model: string;
  ollama: { installed: boolean; running: boolean; models: string[] };
  llm_default: string;
  llm_choices: string[];
}

export interface NewJobOptions {
  lang: string;
  model: string;
  prompt: string;
}

declare global {
  interface Window {
    native?: { getPath?: (f: File) => string; openExternal?: (url: string) => void };
  }
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  // L'interface est servie par le backend : on parle à la même origine. (`ng serve` = port 4200 -> backend de dev.)
  readonly base = location.port === '4200' ? 'http://127.0.0.1:8765' : location.origin;

  readonly jobs = signal<Job[]>([]);
  readonly health = signal<Health | null>(null);
  readonly backendUp = signal<boolean>(true);
  readonly selectedId = signal<string | null>(null);
  readonly selected = computed(() => this.jobs().find((j) => j.id === this.selectedId()) ?? null);
  readonly busy = computed(() => this.jobs().some((j) => j.status === 'queued' || j.status === 'running'));

  constructor() {
    this.refresh();
    this.refreshHealth();
    setInterval(() => this.refresh(), 1200);
    setInterval(() => this.refreshHealth(), 15000);
  }

  async refresh(): Promise<void> {
    try {
      this.jobs.set(await firstValueFrom(this.http.get<Job[]>(`${this.base}/jobs`)));
      this.backendUp.set(true);
    } catch {
      this.backendUp.set(false);
    }
  }

  async refreshHealth(): Promise<void> {
    try {
      this.health.set(await firstValueFrom(this.http.get<Health>(`${this.base}/health`)));
    } catch {
      /* backend pas encore prêt */
    }
  }

  /** Dépôt d'un fichier : en Electron on passe le chemin (pas de copie), dans un navigateur on téléverse. */
  async addFile(file: File, opts: NewJobOptions): Promise<Job> {
    const path = window.native?.getPath?.(file);
    let job: Job;
    if (path) {
      job = await firstValueFrom(this.http.post<Job>(`${this.base}/jobs/from-path`, { path, ...opts }));
    } else {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('lang', opts.lang);
      fd.append('model', opts.model);
      fd.append('prompt', opts.prompt);
      job = await firstValueFrom(this.http.post<Job>(`${this.base}/jobs`, fd));
    }
    await this.refresh();
    this.selectedId.set(job.id);
    return job;
  }

  /** Lien YouTube (public ou non répertorié) : le moteur télécharge l'audio puis lance le pipeline. */
  async addYoutube(url: string, opts: NewJobOptions): Promise<Job> {
    const job = await firstValueFrom(this.http.post<Job>(`${this.base}/jobs/youtube`, { url, ...opts }));
    await this.refresh();
    this.selectedId.set(job.id);
    return job;
  }

  async remove(id: string): Promise<void> {
    await firstValueFrom(this.http.delete(`${this.base}/jobs/${id}`));
    if (this.selectedId() === id) this.selectedId.set(null);
    await this.refresh();
  }

  fileUrl(id: string, name: string, download = false): string {
    return `${this.base}/jobs/${id}/files/${name}${download ? '?download=true' : ''}`;
  }

  getText(id: string, name: string): Promise<string> {
    return firstValueFrom(this.http.get(this.fileUrl(id, name), { responseType: 'text' }));
  }

  getJson<T>(id: string, name: string): Promise<T> {
    return firstValueFrom(this.http.get<T>(this.fileUrl(id, name)));
  }

  async saveTranscript(id: string, text: string): Promise<void> {
    await firstValueFrom(this.http.put(`${this.base}/jobs/${id}/transcript`, { text }));
  }

  async resummarize(id: string, model: string): Promise<void> {
    await firstValueFrom(this.http.post(`${this.base}/jobs/${id}/resummarize`, { model }));
    await this.refresh();
  }
}
