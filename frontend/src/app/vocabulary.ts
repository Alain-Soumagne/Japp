import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';

interface VocCourse { id: string; name: string; busy: boolean; generated: boolean; count: number; kanji: number; error: string }
interface VocEntry { id: string; job_id: string; course: string; word: string; kana: string; romaji: string; french: string; has_kanji: boolean }

@Component({
  selector: 'app-vocabulary',
  template: `
    <section class="voc">
      <p class="kicker">Vocabulaire</p>
      <h1>Tout ce que tu as vu en cours.</h1>

      @if (error()) { <p class="err" role="alert">{{ error() }}</p> }

      @if (!courses().length && loaded()) {
        <p class="muted">Aucun cours de japonais pour l'instant. Transcris un cours : son vocabulaire apparaîtra ici.</p>
      } @else {
        @if (missing().length) {
          <div class="gen">
            <div><strong>{{ missing().length }} cours sans vocabulaire</strong>
              <span>{{ missing().map(c => c.name).join(', ') }}</span></div>
            <button (click)="generate(missing())" [disabled]="anyBusy()">{{ anyBusy() ? 'Extraction en cours…' : 'Extraire le vocabulaire' }}</button>
          </div>
        }
        @if (anyBusy()) { <p class="note">Le modèle extrait le vocabulaire (quelques dizaines de secondes par cours). La liste se met à jour toute seule.</p> }

        <div class="tools">
          <input type="search" placeholder="Rechercher un mot, une lecture, une traduction…" aria-label="Rechercher"
                 [value]="q()" (input)="q.set($any($event.target).value)" />
          <select aria-label="Cours" (change)="course.set($any($event.target).value)">
            <option value="">Tous les cours</option>
            @for (c of courses(); track c.id) { <option [value]="c.id" [selected]="c.id === course()">{{ c.name }} ({{ c.count }})</option> }
          </select>
          <label class="chk"><input type="checkbox" [checked]="onlyKanji()" (change)="onlyKanji.set($any($event.target).checked)" /> Seulement les kanji</label>
          <a class="btn" [href]="csvUrl()" download="vocabulaire-japp.csv">Exporter en CSV</a>
        </div>

        <p class="count">{{ shown().length }} mot{{ shown().length > 1 ? 's' : '' }}
          @if (shown().length !== entries().length) { <span class="muted">sur {{ entries().length }}</span> }</p>

        @if (shown().length) {
          <div class="table" role="table" aria-label="Vocabulaire">
            <div class="row head" role="row"><span>Mot</span><span>Lecture (kana · romaji)</span><span>Traduction</span><span>Cours</span><span></span></div>
            @for (e of shown(); track e.job_id + e.id) {
              <div class="row" role="row">
                <span class="w" lang="ja">{{ e.word }}</span>
                <span class="k">
                  @if (e.word !== e.kana) { <span lang="ja">{{ e.kana }}</span>@if (e.romaji) { <small>{{ e.romaji }}</small> } }
                  @else { <span class="rom">{{ e.romaji || '—' }}</span> }
                </span>
                <span class="f">{{ e.french }}</span>
                <span class="c">{{ e.course }}</span>
                <button class="x" title="Retirer ce mot" aria-label="Retirer ce mot" (click)="remove(e)">✕</button>
              </div>
            }
          </div>
        } @else if (loaded() && entries().length) {
          <p class="muted">Aucun mot ne correspond à cette recherche.</p>
        }

        @if (courses().length) {
          <details class="cs">
            <summary>État par cours</summary>
            @for (c of courses(); track c.id) {
              <div class="crow">
                <span class="nm">{{ c.name }}</span>
                <span class="muted">{{ c.generated ? c.count + ' mots · ' + c.kanji + ' avec kanji' : 'pas encore extrait' }}</span>
                @if (c.error) { <span class="bad" [title]="c.error">échec de la dernière extraction</span> }
                <button class="ghost" [disabled]="c.busy || anyBusy()" (click)="generate([c])">{{ c.generated ? 'Régénérer' : 'Extraire' }}</button>
              </div>
            }
            <p class="muted small">Le vocabulaire est extrait par le modèle puis contrôlé : un mot n'est gardé que s'il apparaît dans la transcription et si sa lecture est cohérente. Relis-le tout de même, et retire les mots inutiles avec ✕.</p>
          </details>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; }
    .voc { max-width: 1040px; padding: 48px 48px 64px; }
    .kicker { font-size: 13px; letter-spacing: .22em; text-transform: uppercase; color: var(--red); font-weight: 600; margin: 0; }
    h1 { font: 700 44px/1.12 var(--serif); margin: 12px 0 24px; }
    .muted { color: #4a443b; font-size: 14px; } .small { font-size: 13px; }
    .err { color: var(--red); background: var(--red-soft); padding: 10px 14px; }
    .note { background: #f6ecd2; border-left: 4px solid #c79a2a; padding: 10px 14px; font-size: 14px; }
    .gen { display: flex; gap: 20px; align-items: center; justify-content: space-between; background: var(--card); border: 1px solid var(--line); border-left: 4px solid var(--red); padding: 14px 20px; margin-bottom: 18px; }
    .gen span { display: block; color: #5f584e; font-size: 14px; margin-top: 2px; }
    button, .btn { font: 600 14px var(--sans); padding: 10px 18px; border: 1.5px solid var(--ink); background: var(--ink); color: #fff; cursor: pointer; text-decoration: none; white-space: nowrap; display: inline-block; }
    button:hover:not(:disabled), .btn:hover { background: var(--red); border-color: var(--red); }
    button:disabled { opacity: .4; cursor: default; }
    button.ghost { background: none; color: var(--ink); padding: 6px 12px; font-size: 13px; } button.ghost:hover:not(:disabled) { color: #fff; }
    .tools { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 14px 0 6px; }
    .tools input[type=search] { flex: 1; min-width: 240px; font: 15px var(--sans); padding: 10px 12px; border: 1.5px solid var(--ink); background: #fff; }
    .tools input:focus, .tools select:focus { outline: 3px solid var(--red); outline-offset: 1px; }
    .tools select { font: 15px var(--sans); padding: 10px 12px; border: 1.5px solid var(--ink); background: var(--card); max-width: 260px; }
    .chk { display: flex; gap: 6px; align-items: center; font-size: 14px; color: var(--ink); white-space: nowrap; } .chk input { accent-color: var(--red); width: 16px; height: 16px; }
    .count { margin: 12px 0 6px; font-weight: 700; }
    .table { border-top: 3px solid var(--ink); background: var(--card); }
    .row { display: grid; grid-template-columns: 190px 190px 1fr 190px 40px; gap: 14px; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--line); }
    .row.head { font: 700 11px var(--sans); letter-spacing: .1em; text-transform: uppercase; color: #3a352e; padding: 8px 14px; background: var(--paper2); }
    .w { font: 700 28px/1.2 var(--serif); }
    .k { display: grid; font-size: 18px; min-height: 24px; } .k small { color: #4a443b; font-size: 14px; } .k .rom { font-size: 17px; }
    .f { font-size: 16px; } .c { font-size: 13px; color: #4a443b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .x { background: none; color: #8f887a; border: 0; padding: 4px 8px; font-size: 14px; } .x:hover:not(:disabled) { background: none; color: var(--red); }
    .cs { margin-top: 30px; } .cs summary { cursor: pointer; font-weight: 700; }
    .crow { display: flex; gap: 14px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--line); } .crow .nm { flex: 1; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bad { color: var(--red); font-size: 13px; }
    @media (max-width: 1100px) { .row { grid-template-columns: 140px 150px 1fr 40px; } .row .c, .row.head span:nth-child(4) { display: none; } }
  `,
})
export class VocabularyPage implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly courses = signal<VocCourse[]>([]);
  readonly entries = signal<VocEntry[]>([]);
  readonly loaded = signal(false);
  readonly error = signal('');
  readonly q = signal('');
  readonly course = signal('');
  readonly onlyKanji = signal(false);

  readonly missing = computed(() => this.courses().filter((c) => !c.generated && !c.busy));
  readonly anyBusy = computed(() => this.courses().some((c) => c.busy));
  readonly shown = computed(() => {
    const q = this.q().trim().toLowerCase();
    return this.entries().filter((e) =>
      (!this.course() || e.job_id === this.course()) && (!this.onlyKanji() || e.has_kanji) &&
      (!q || [e.word, e.kana, e.romaji, e.french].some((v) => (v ?? '').toLowerCase().includes(q))));
  });
  readonly csvUrl = computed(() => `${this.api.base}/vocabulary/export.csv${this.course() ? '?job_id=' + this.course() : ''}`);

  ngOnInit(): void {
    this.load();
    this.timer = setInterval(() => { if (this.anyBusy()) this.load(); }, 3000);
  }
  ngOnDestroy(): void { if (this.timer) clearInterval(this.timer); }

  private detail(e: unknown): string {
    const d = (e as { error?: { detail?: unknown } }).error?.detail;
    return typeof d === 'string' ? d : `Échec : ${(e as Error).message}`;
  }

  async load(): Promise<void> {
    try {
      const r = await firstValueFrom(this.http.get<{ courses: VocCourse[]; entries: VocEntry[] }>(`${this.api.base}/vocabulary`));
      this.courses.set(r.courses);
      this.entries.set(r.entries);
      this.error.set('');
    } catch (e) { this.error.set(this.detail(e)); } finally { this.loaded.set(true); }
  }

  async generate(cs: VocCourse[]): Promise<void> {
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${this.api.base}/vocabulary/generate`, { job_ids: cs.map((c) => c.id) }));
      await this.api.refresh();
      await this.load();
    } catch (e) { this.error.set(this.detail(e)); }
  }

  async remove(e: VocEntry): Promise<void> {
    try {
      await firstValueFrom(this.http.delete(`${this.api.base}/vocabulary/${e.job_id}/${e.id}`));
      this.entries.update((l) => l.filter((x) => !(x.job_id === e.job_id && x.id === e.id)));
    } catch (err) { this.error.set(this.detail(err)); }
  }
}
