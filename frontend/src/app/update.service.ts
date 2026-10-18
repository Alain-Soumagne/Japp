import { Injectable, computed, signal } from '@angular/core';

export interface UpdateState {
  enabled: boolean;
  current: string;
  checking: boolean;
  error: string;
  checkedAt: number;
  available: { version: string; notes: string; size: number; name: string; url: string } | null;
  dismissed: boolean;
  download: { status: 'idle' | 'running' | 'done' | 'error'; progress: number; path: string; error: string };
}

/** Mises à jour : uniquement dans l'application Electron (window.native.update). Dans un navigateur, le service reste inerte. */
@Injectable({ providedIn: 'root' })
export class UpdateService {
  private readonly api = window.native?.update;
  readonly supported = !!this.api;
  readonly state = signal<UpdateState | null>(null);
  readonly upToDate = signal(false);
  readonly banner = computed(() => {
    const s = this.state();
    return s && s.available && !s.dismissed ? s : null;
  });

  constructor() {
    if (!this.api) return;
    this.api.get().then((s) => s && this.state.set(s));
    this.api.onState((s) => this.state.set(s));
  }

  async check(): Promise<void> {
    if (!this.api) return;
    this.upToDate.set(false);
    const s = await this.api.check();
    this.state.set(s);
    if (!s.available && !s.error) {
      this.upToDate.set(true);
      setTimeout(() => this.upToDate.set(false), 5000);
    }
  }
  download(): void { this.api?.download(); }
  reveal(): void { this.api?.reveal(); }
  dismiss(): void { this.api?.dismiss(); }
  setEnabled(on: boolean): void { this.api?.setEnabled(on); }
  openNotes(url: string): void { window.native?.openExternal?.(url); }

  mb(bytes: number): string { return bytes ? `${Math.round(bytes / 1e6)} Mo` : ''; }
}
