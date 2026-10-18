import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';

export interface ExCourse { id: string; name: string; difficulty: number; examples: number; sections: number }
export interface ExHistory { id: string; date: string; score: number; level_before: number; level_after: number; n: number; courses: string[] }
export interface ExProfile { level: number; label: string; history: ExHistory[]; sessions: number; default_model: string }
export interface ExContest { argument: string; verdict: Verdict; feedback: string; changed: boolean; previous: Verdict }
export type Verdict = 'correct' | 'partial' | 'incorrect';
export interface ExQuestion {
  id: string; type: string; prompt: string; hint: string; choices?: string[]; course: string; section: string; answer: string;
  verdict?: Verdict; points?: number; feedback?: string; graded_by?: string; reference?: string; explanation?: string;
  contest?: ExContest | null; excluded?: boolean;
}
export interface ExResult {
  score: number; level_before: number; level_after: number; delta: number; final: boolean; label?: string;
  by_course?: Record<string, number>; answered?: number; total?: number; excluded?: number; mean_difficulty?: number;
}
export interface ExSession {
  id: string; status: 'generating' | 'ready' | 'grading' | 'graded' | 'finalized' | 'error'; message: string; error: string | null;
  notice: string; course_names: string[]; count: number; questions: ExQuestion[]; result: ExResult | null; level_at_start: number; created: number;
}
export interface ExSummary { id: string; created: number; status: string; count: number; course_names: string[]; result: ExResult | null }

export const TYPE_LABEL: Record<string, string> = {
  mcq: 'QCM', short: 'Question courte', translate_ja_fr: 'Traduction japonais → français', translate_fr_ja: 'Traduction français → japonais',
  reading: 'Lecture (romaji)', cloze: 'Particule manquante',
};

@Injectable({ providedIn: 'root' })
export class ExercisesService {
  private http = inject(HttpClient);
  private api = inject(ApiService);
  private get base(): string { return `${this.api.base}/exercises`; }

  readonly profile = signal<ExProfile | null>(null);
  readonly courses = signal<ExCourse[]>([]);
  readonly past = signal<ExSummary[]>([]);
  readonly session = signal<ExSession | null>(null);
  readonly answers = signal<Record<string, string>>({});
  readonly index = signal(0);
  readonly error = signal('');
  readonly busy = signal(false);
  private timer: ReturnType<typeof setTimeout> | null = null;

  readonly current = computed(() => this.session()?.questions[this.index()] ?? null);
  readonly answered = computed(() => Object.values(this.answers()).filter((v) => v.trim()).length);

  detail(e: unknown): string {
    const d = (e as { error?: { detail?: unknown } }).error?.detail;
    return typeof d === 'string' ? d : `Échec : ${(e as Error).message}`;
  }

  async loadHome(): Promise<void> {
    try {
      const [p, c, s] = await Promise.all([
        firstValueFrom(this.http.get<ExProfile>(`${this.base}/profile`)),
        firstValueFrom(this.http.get<ExCourse[]>(`${this.base}/courses`)),
        firstValueFrom(this.http.get<ExSummary[]>(`${this.base}/sessions`)),
      ]);
      this.profile.set(p); this.courses.set(c); this.past.set(s);
    } catch (e) { this.error.set(this.detail(e)); }
  }

  async start(jobIds: string[], count: number, model: string): Promise<void> {
    this.error.set(''); this.busy.set(true);
    try {
      const s = await firstValueFrom(this.http.post<ExSession>(`${this.base}/sessions`, { job_ids: jobIds, count, model }));
      this.open(s);
    } catch (e) { this.error.set(this.detail(e)); } finally { this.busy.set(false); }
  }

  async resume(id: string): Promise<void> {
    this.error.set('');
    try { this.open(await firstValueFrom(this.http.get<ExSession>(`${this.base}/sessions/${id}`))); }
    catch (e) { this.error.set(this.detail(e)); }
  }

  private open(s: ExSession): void {
    this.session.set(s);
    this.index.set(0);
    this.answers.set(Object.fromEntries(s.questions.map((q) => [q.id, q.answer ?? ''])));
    this.poll();
  }

  private poll(): void {
    if (this.timer) clearTimeout(this.timer);
    const s = this.session();
    if (!s || !['generating', 'grading'].includes(s.status)) return;
    this.timer = setTimeout(async () => {
      try {
        const n = await firstValueFrom(this.http.get<ExSession>(`${this.base}/sessions/${s.id}`));
        if (this.session()?.id !== s.id) return;
        if (n.status !== s.status && n.status === 'ready') this.answers.set(Object.fromEntries(n.questions.map((q) => [q.id, q.answer ?? ''])));
        this.session.set(n);
      } catch { /* moteur momentanément indisponible : on réessaie */ }
      this.poll();
    }, 1500);
  }

  stopPolling(): void { if (this.timer) clearTimeout(this.timer); }

  setAnswer(qid: string, v: string): void { this.answers.update((a) => ({ ...a, [qid]: v })); }

  async saveDraft(): Promise<void> {
    const s = this.session();
    if (s?.status !== 'ready') return;
    try { await firstValueFrom(this.http.put(`${this.base}/sessions/${s.id}/answers`, { answers: this.answers() })); } catch { /* brouillon : sans conséquence */ }
  }

  async submit(): Promise<void> {
    const s = this.session();
    if (!s) return;
    this.error.set(''); this.busy.set(true);
    try {
      this.session.set(await firstValueFrom(this.http.post<ExSession>(`${this.base}/sessions/${s.id}/submit`, { answers: this.answers() })));
      this.poll();
    } catch (e) { this.error.set(this.detail(e)); } finally { this.busy.set(false); }
  }

  async contest(qid: string, argument: string): Promise<boolean> {
    const s = this.session();
    if (!s) return false;
    this.error.set(''); this.busy.set(true);
    try {
      this.session.set(await firstValueFrom(this.http.post<ExSession>(`${this.base}/sessions/${s.id}/questions/${qid}/contest`, { argument })));
      return true;
    } catch (e) { this.error.set(this.detail(e)); return false; } finally { this.busy.set(false); }
  }

  async exclude(qid: string): Promise<void> {
    const s = this.session();
    if (!s) return;
    this.error.set('');
    try { this.session.set(await firstValueFrom(this.http.post<ExSession>(`${this.base}/sessions/${s.id}/questions/${qid}/exclude`, {}))); }
    catch (e) { this.error.set(this.detail(e)); }
  }

  async finalize(): Promise<void> {
    const s = this.session();
    if (!s) return;
    this.error.set(''); this.busy.set(true);
    try {
      this.session.set(await firstValueFrom(this.http.post<ExSession>(`${this.base}/sessions/${s.id}/finalize`, {})));
      await this.loadHome();
    } catch (e) { this.error.set(this.detail(e)); } finally { this.busy.set(false); }
  }

  async remove(id: string): Promise<void> {
    await firstValueFrom(this.http.delete(`${this.base}/sessions/${id}`));
    if (this.session()?.id === id) this.close();
    await this.loadHome();
  }

  close(): void {
    this.stopPolling();
    this.session.set(null);
    this.error.set('');
    this.loadHome();
  }
}
