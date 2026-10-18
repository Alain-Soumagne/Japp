import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ApiService, Job, Summary } from './api.service';
import { SummaryEditor } from './summary-editor';

type Tab = 'deck' | 'transcript' | 'summary' | 'edit';

const STAGES: { id: string; label: string }[] = [
  { id: 'downloading', label: 'Téléchargement' },
  { id: 'transcribing', label: 'Transcription' },
  { id: 'preparing_llm', label: 'Modèle IA' },
  { id: 'summarizing', label: 'Synthèse' },
  { id: 'rendering', label: 'Présentation' },
];

@Component({
  selector: 'app-job-view',
  imports: [SummaryEditor],
  template: `
    @let j = job();
    <header class="head">
      <div>
        <h2>{{ j.name }}</h2>
        <p class="meta">
          {{ j.model }} · langue : {{ j.lang }}
          @if (j.info.duration) { · {{ minutes(j.info.duration) }} min }
          @if (j.info.language) { · détectée : {{ j.info.language }} }
        </p>
      </div>
      <button class="ghost danger" (click)="remove()">Supprimer</button>
    </header>

    @if (j.status === 'queued' || j.status === 'running') {
      <section class="progress">
        <ol class="steps">
          @for (s of stagesOf(j); track s.id) {
            <li [class.active]="j.stage === s.id" [class.done]="stageIndex(j.stage) > $index">{{ s.label }}</li>
          }
        </ol>
        <div class="bar"><div class="fill" [style.width.%]="j.progress * 100"></div></div>
        <p class="msg">{{ j.message }} <span class="pct">{{ (j.progress * 100).toFixed(0) }} %</span></p>
      </section>
    }

    @if (j.status === 'error') {
      <section class="error">
        <strong>La tâche a échoué.</strong>
        <pre>{{ j.error }}</pre>
        @if (j.files.includes('transcript.txt')) {
          <button (click)="regenerate()">Réessayer la synthèse</button>
        }
      </section>
    }

    @if (j.files.length) {
      <nav class="tabs">
        <button [class.on]="tab() === 'deck'" [disabled]="!j.files.includes('deck.html')" (click)="tab.set('deck')">Présentation</button>
        <button [class.on]="tab() === 'transcript'" [disabled]="!j.files.includes('transcript.txt')" (click)="tab.set('transcript')">Transcription</button>
        <button [class.on]="tab() === 'summary'" [disabled]="!j.files.includes('synthese.json')" (click)="tab.set('summary')">Synthèse</button>
        <button [class.on]="tab() === 'edit'" [disabled]="!j.files.includes('synthese.json') || running()" (click)="tab.set('edit')">Éditer</button>
        <span class="spacer"></span>
        @for (f of j.files; track f) {
          <a class="dl" [href]="api.fileUrl(j.id, f, true)" [attr.download]="f">{{ f }}</a>
        }
      </nav>

      @switch (tab()) {
        @case ('deck') {
          @if (deckUrl(); as u) {
            <div class="deck-wrap">
              <iframe [src]="u" title="Présentation" sandbox="allow-scripts" allowfullscreen referrerpolicy="no-referrer"></iframe>
              <button class="ghost open" (click)="openDeck()">Ouvrir en grand ↗</button>
            </div>
          }
        }
        @case ('transcript') {
          <section class="editor">
            <p class="hint">Corrige la transcription (une ligne = un segment), puis régénère la synthèse.</p>
            <textarea [value]="text()" (input)="onEdit($event)" spellcheck="false"></textarea>
            <div class="row">
              <button (click)="saveAndRegenerate()" [disabled]="!dirty() || running()">Enregistrer et régénérer la synthèse</button>
              <button class="ghost" (click)="save()" [disabled]="!dirty()">Enregistrer seulement</button>
              @if (saved()) { <span class="ok">Enregistré</span> }
            </div>
          </section>
        }
        @case ('edit') {
          @if (summary(); as s) { <app-summary-editor [job]="j" [summary]="s" (saved)="onSaved()" /> }
        }
        @case ('summary') {
          @if (summary(); as s) {
            <section class="summary">
              <h3>{{ s.title }}</h3>
              <p class="meta">
                {{ s.subtitle }}
                @if (s.stats?.edited) { · modifiée manuellement } @else if (s.stats) { · exemples vérifiés : {{ s.stats.examples_kept }}/{{ s.stats.examples_total }} }
              </p>
              @for (sec of s.sections; track sec.title) {
                <article>
                  <h4>{{ sec.title }}</h4>
                  <ul>@for (p of sec.key_points; track p) { <li>{{ p }}</li> }</ul>
                  @for (e of sec.examples; track e.romaji) {
                    <div class="ex"><span class="jp">{{ e.japanese }}</span><span class="ro">{{ e.romaji }}</span><span>{{ e.french }}</span></div>
                  }
                </article>
              }
            </section>
          }
        }
      }
    }
  `,
  styles: `
    :host { display: block; padding: 28px 36px 40px; }
    .head { display: flex; justify-content: space-between; align-items: start; gap: 20px; margin-bottom: 18px; }
    h2 { font: 700 34px/1.15 var(--serif); margin: 0; }
    .meta { color: var(--muted); margin: 6px 0 0; font-size: 14px; }
    .progress { background: var(--card); border: 1px solid var(--line); padding: 22px 24px; margin-bottom: 20px; }
    .steps { display: flex; gap: 8px; list-style: none; padding: 0; margin: 0 0 16px; }
    .steps li { flex: 1; padding: 8px 12px; border-bottom: 4px solid var(--line); font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
    .steps li.active { border-color: var(--red); color: var(--ink); font-weight: 700; }
    .steps li.done { border-color: var(--ink); color: var(--ink); }
    .bar { height: 10px; background: var(--paper2); }
    .fill { height: 100%; background: var(--red); transition: width .4s; }
    .msg { margin: 10px 0 0; font-size: 14px; display: flex; justify-content: space-between; }
    .pct { font-variant-numeric: tabular-nums; color: var(--muted); }
    .error { background: var(--red-soft); border: 1px solid var(--red); padding: 18px 22px; margin-bottom: 20px; }
    .error pre { white-space: pre-wrap; font-size: 13px; margin: 8px 0 12px; }
    .tabs { display: flex; align-items: center; gap: 4px; border-bottom: 2px solid var(--ink); margin-bottom: 18px; flex-wrap: wrap; }
    .tabs button { background: none; border: 0; padding: 10px 18px; font: 600 15px var(--sans); cursor: pointer; color: var(--muted); border-bottom: 4px solid transparent; margin-bottom: -2px; }
    .tabs button.on { color: var(--ink); border-color: var(--red); }
    .tabs button:disabled { opacity: .35; cursor: default; }
    .spacer { flex: 1; }
    .dl { font-size: 12px; color: var(--muted); text-decoration: none; padding: 4px 8px; border: 1px solid var(--line); margin-left: 4px; }
    .dl:hover { color: var(--red); border-color: var(--red); }
    .deck-wrap { position: relative; aspect-ratio: 16/9; width: min(100%, calc((100vh - 270px) * 16 / 9)); background: var(--paper); }
    .deck-wrap iframe { width: 100%; height: 100%; border: 0; }
    .open { position: absolute; right: 10px; top: 10px; background: #fffa !important; }
    .editor textarea { width: 100%; height: calc(100vh - 360px); min-height: 280px; font: 15px/1.6 var(--sans); padding: 16px; border: 1px solid var(--line); background: var(--card); color: var(--ink); resize: vertical; }
    .hint { color: var(--muted); font-size: 14px; margin: 0 0 8px; }
    .row { display: flex; gap: 10px; align-items: center; margin-top: 12px; }
    .ok { color: #3f6b57; font-size: 14px; }
    .summary h3 { font: 700 28px var(--serif); margin: 0; }
    .summary article { border-top: 3px solid var(--ink); margin-top: 22px; padding-top: 8px; }
    .summary h4 { font: 700 20px var(--serif); margin: 8px 0; }
    .summary ul { margin: 0 0 8px; padding-left: 20px; line-height: 1.55; }
    .ex { display: flex; gap: 16px; align-items: baseline; padding: 6px 0; border-top: 1px solid var(--line); font-size: 14px; }
    .ex .jp { font: 20px var(--serif); min-width: 280px; }
    .ex .ro { color: var(--muted); min-width: 240px; }
  `,
})
export class JobView {
  readonly api = inject(ApiService);
  private sanitizer = inject(DomSanitizer);
  readonly job = input.required<Job>();
  stagesOf(j: Job) {
    return j.url ? STAGES : STAGES.filter((s) => s.id !== 'downloading');
  }

  readonly tab = signal<Tab>('deck');
  readonly text = signal('');
  readonly orig = signal('');
  readonly saved = signal(false);
  readonly summary = signal<Summary | null>(null);
  readonly dirty = computed(() => this.text() !== this.orig());
  readonly running = computed(() => this.job().status === 'running' || this.job().status === 'queued');
  private readonly jobId = computed(() => this.job().id);
  private readonly deckHref = computed(() => {
    const j = this.job();
    return j.files.includes('deck.html') ? `${this.api.fileUrl(j.id, 'deck.html')}?v=${Math.floor(j.updated)}` : null;
  });
  // chaîne stable -> l'iframe ne se recharge que si le deck a réellement changé
  readonly deckUrl = computed<SafeResourceUrl | null>(() => {
    const h = this.deckHref();
    return h ? this.sanitizer.bypassSecurityTrustResourceUrl(h) : null;
  });

  private loadedKey = '';

  constructor() {
    effect(() => {
      const j = this.job();
      const key = `${j.id}:${j.status}:${Math.floor(j.updated)}`;
      if (j.status !== 'done' || key === this.loadedKey) return;
      this.loadedKey = key;
      this.load(j);
    });
    effect(() => {
      // changement de tâche (et seulement lui) : retour à l'onglet présentation
      this.jobId();
      untracked(() => {
        this.tab.set('deck');
        this.saved.set(false);
      });
    });
  }

  private async load(j: Job): Promise<void> {
    if (j.files.includes('transcript.txt')) {
      const t = await this.api.getText(j.id, 'transcript.txt');
      this.text.set(t);
      this.orig.set(t);
    }
    if (j.files.includes('synthese.json')) this.summary.set(await this.api.getJson<Summary>(j.id, 'synthese.json'));
  }

  onSaved(): void {
    this.api.refresh();      // met à jour la tâche : la présentation et la synthèse se rechargent
  }

  minutes(s: number): string {
    return (s / 60).toFixed(1);
  }

  stageIndex(stage: string): number {
    return this.stagesOf(this.job()).findIndex((s) => s.id === stage);
  }

  onEdit(e: Event): void {
    this.text.set((e.target as HTMLTextAreaElement).value);
    this.saved.set(false);
  }

  async save(): Promise<void> {
    await this.api.saveTranscript(this.job().id, this.text());
    this.orig.set(this.text());
    this.saved.set(true);
  }

  async saveAndRegenerate(): Promise<void> {
    await this.save();
    await this.regenerate();
  }

  async regenerate(): Promise<void> {
    await this.api.resummarize(this.job().id, this.job().model);
  }

  async remove(): Promise<void> {
    if (confirm(`Supprimer « ${this.job().name} » et ses fichiers ?`)) await this.api.remove(this.job().id);
  }

  openDeck(): void {
    const url = this.api.fileUrl(this.job().id, 'deck.html');
    if (window.native?.openExternal) window.native.openExternal(url);
    else window.open(url, '_blank');
  }
}
