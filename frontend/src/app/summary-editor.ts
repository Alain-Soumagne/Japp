import { Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { ApiService, Job, Summary } from './api.service';

@Component({
  selector: 'app-summary-editor',
  template: `
    @if (draft(); as d) {
      <section class="ed">
        <p class="hint">
          Corrige le texte, supprime ce qui ne te sert pas (✕) ou réordonne les notions (↑ ↓).
          Chaque notion devient une ou plusieurs diapos ; supprimer une notion supprime ses diapos.
        </p>

        <div class="card">
          <label>Titre<input [value]="d.title" (input)="set($event, (x, v) => (x.title = v))" maxlength="200" /></label>
          <label>Sous-titre<input [value]="d.subtitle" (input)="set($event, (x, v) => (x.subtitle = v))" maxlength="300" /></label>
        </div>

        @for (sec of d.sections; track $index; let si = $index) {
          <article class="card sec">
            <header>
              <span class="num">{{ (si + 1).toString().padStart(2, '0') }}</span>
              <input class="stitle" [value]="sec.title" (input)="set($event, (x, v) => (x.sections[si].title = v))"
                     maxlength="200" placeholder="Titre de la notion" aria-label="Titre de la notion" />
              <button class="icon" title="Monter" [disabled]="si === 0" (click)="move(si, -1)">↑</button>
              <button class="icon" title="Descendre" [disabled]="si === d.sections.length - 1" (click)="move(si, 1)">↓</button>
              <button class="icon danger" title="Supprimer cette notion et ses diapos" [disabled]="d.sections.length === 1" (click)="removeSection(si)">✕ Supprimer</button>
            </header>

            <h5>Points clés</h5>
            @for (p of sec.key_points; track $index; let pi = $index) {
              <div class="line">
                <textarea rows="2" [value]="p" maxlength="800" (input)="set($event, (x, v) => (x.sections[si].key_points[pi] = v))"></textarea>
                <button class="icon danger" title="Supprimer ce point" (click)="mut(x => x.sections[si].key_points.splice(pi, 1))">✕</button>
              </div>
            }
            <button class="add" (click)="mut(x => x.sections[si].key_points.push(''))">＋ Ajouter un point</button>

            <h5>Exemples</h5>
            @if (sec.examples.length) {
              <div class="line cols"><span>Japonais</span><span>Romaji</span><span>Français</span><i></i></div>
            }
            @for (e of sec.examples; track $index; let ei = $index) {
              <div class="line ex">
                <input class="jp" [value]="e.japanese" placeholder="日本語" (input)="set($event, (x, v) => (x.sections[si].examples[ei].japanese = v))" maxlength="400" aria-label="Japonais" />
                <input [value]="e.romaji" placeholder="romaji" (input)="set($event, (x, v) => (x.sections[si].examples[ei].romaji = v))" maxlength="400" aria-label="Romaji" />
                <input [value]="e.french" placeholder="français" (input)="set($event, (x, v) => (x.sections[si].examples[ei].french = v))" maxlength="400" aria-label="Français" />
                <button class="icon danger" title="Supprimer cet exemple" (click)="mut(x => x.sections[si].examples.splice(ei, 1))">✕</button>
              </div>
            }
            <button class="add" (click)="mut(x => x.sections[si].examples.push({ japanese: '', romaji: '', french: '' }))">＋ Ajouter un exemple</button>
          </article>
        }
        <button class="add big" (click)="mut(x => x.sections.push({ title: 'Nouvelle notion', key_points: [''], examples: [] }))">＋ Ajouter une notion</button>

        <article class="card">
          <h5 style="margin-top:0">Devoirs et conseils</h5>
          @for (h of d.homework; track $index; let hi = $index) {
            <div class="line">
              <textarea rows="2" [value]="h" maxlength="800" (input)="set($event, (x, v) => (x.homework[hi] = v))"></textarea>
              <button class="icon danger" title="Supprimer" (click)="mut(x => x.homework.splice(hi, 1))">✕</button>
            </div>
          }
          <button class="add" (click)="mut(x => x.homework.push(''))">＋ Ajouter un devoir</button>
        </article>

        <footer class="bar">
          <button (click)="save()" [disabled]="!dirty() || busy()">{{ busy() ? 'Enregistrement…' : 'Enregistrer' }}</button>
          <button class="ghost" (click)="reset()" [disabled]="!dirty() || busy()">Annuler les changements</button>
          @if (canRestore()) {
            <button class="ghost" (click)="restore()" [disabled]="busy()">Restaurer la version de l'IA</button>
          }
          <span class="spacer"></span>
          @if (msg(); as m) { <span [class.err]="isErr()" [class.ok]="!isErr()">{{ m }}</span> }
          @else if (dirty()) { <span class="muted">Modifications non enregistrées</span> }
        </footer>
      </section>
    }
  `,
  styles: `
    :host { display: block; padding-bottom: 8px; }
    .hint { color: var(--muted); font-size: 14px; margin: 0 0 14px; max-width: 60em; }
    .card { background: var(--card); border: 1px solid var(--line); padding: 16px 18px; margin-bottom: 14px; display: grid; gap: 10px; }
    label { display: grid; gap: 4px; font-size: 13px; font-weight: 600; color: var(--muted); }
    input, textarea { font: 15px/1.5 var(--sans); padding: 8px 10px; border: 1px solid var(--line); background: #fff; color: var(--ink); width: 100%; min-width: 0; }
    input:focus, textarea:focus { outline: 2px solid var(--red); outline-offset: -1px; }
    textarea { resize: vertical; }
    .sec { border-top: 3px solid var(--ink); }
    .sec header { display: flex; gap: 8px; align-items: center; }
    .num { font: 700 26px var(--serif); color: var(--red); min-width: 36px; }
    .stitle { font: 700 19px var(--serif); }
    h5 { margin: 8px 0 0; font: 700 12px var(--sans); letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
    .line { display: flex; gap: 8px; align-items: start; }
    .line.ex { align-items: center; }
    .line.ex input:nth-child(1), .line.cols span:nth-child(1) { flex: 5; }
    .line.ex input:nth-child(2), .line.cols span:nth-child(2) { flex: 4; }
    .line.ex input:nth-child(3), .line.cols span:nth-child(3) { flex: 6; }
    .line.cols { font: 600 11px var(--sans); color: var(--muted); letter-spacing: .08em; text-transform: uppercase; margin-bottom: -4px; }
    .line.cols i { width: 34px; flex: none; }
    .jp { font: 18px var(--serif); }
    .icon { background: none; border: 1px solid var(--line); padding: 6px 10px; cursor: pointer; font: 600 13px var(--sans); color: var(--ink); white-space: nowrap; }
    .icon:hover:not(:disabled) { border-color: var(--ink); }
    .icon.danger:hover:not(:disabled) { color: #fff; background: var(--red); border-color: var(--red); }
    .icon:disabled { opacity: .3; cursor: default; }
    .add { justify-self: start; background: none; border: 1px dashed #8f887a; padding: 6px 12px; cursor: pointer; font: 600 13px var(--sans); color: var(--muted); }
    .add:hover { color: var(--red); border-color: var(--red); }
    .add.big { margin-bottom: 14px; padding: 10px 16px; font-size: 14px; }
    .bar { position: sticky; bottom: 0; display: flex; gap: 10px; align-items: center; padding: 12px 0; background: var(--paper); box-shadow: 0 -14px 14px -8px var(--paper); z-index: 2; border-top: 2px solid var(--ink); margin-top: 10px; }
    .spacer { flex: 1; }
    .muted { color: var(--red-ink, #a82920); font-size: 14px; font-weight: 600; }
    .ok { color: #3f6b57; font-size: 14px; }
    .err { color: var(--red); font-size: 14px; }
  `,
  imports: [],
})
export class SummaryEditor {
  private readonly api = inject(ApiService);
  readonly job = input.required<Job>();
  readonly summary = input.required<Summary>();
  readonly saved = output<void>();

  readonly draft = signal<Summary | null>(null);
  private readonly base = signal('');
  readonly busy = signal(false);
  readonly msg = signal('');
  readonly isErr = signal(false);
  readonly canRestore = signal(false);
  readonly dirty = computed(() => !!this.draft() && JSON.stringify(this.draft()) !== this.base());

  constructor() {
    effect(() => {
      const s = this.summary();
      const id = this.job().id;
      untracked(() => {
        // on ne remplace pas un brouillon en cours de frappe par la version rechargée du serveur
        if (this.dirty()) return;
        this.init(s);
        this.api.synthesStatus(id).then((r) => this.canRestore.set(r.can_restore)).catch(() => this.canRestore.set(false));
      });
    });
  }

  private init(s: Summary): void {
    const c = structuredClone(s);
    c.subtitle ??= '';
    c.homework ??= [];
    this.draft.set(c);
    this.base.set(JSON.stringify(c));
  }

  mut(fn: (d: Summary) => void): void {
    this.draft.update((d) => {
      const c = structuredClone(d!);
      fn(c);
      return c;
    });
    this.msg.set('');
  }

  set(ev: Event, fn: (d: Summary, v: string) => void): void {
    const v = (ev.target as HTMLInputElement | HTMLTextAreaElement).value;
    this.mut((d) => fn(d, v));
  }

  move(i: number, delta: number): void {
    this.mut((d) => {
      const [x] = d.sections.splice(i, 1);
      d.sections.splice(i + delta, 0, x);
    });
  }

  removeSection(i: number): void {
    this.mut((d) => d.sections.splice(i, 1));
  }

  reset(): void {
    this.init(this.summary());
    this.msg.set('');
  }

  async save(): Promise<void> {
    const d = this.draft();
    if (!d) return;
    this.busy.set(true);
    try {
      const r = await this.api.saveSynthese(this.job().id, {
        title: d.title, subtitle: d.subtitle, sections: d.sections, homework: d.homework,
      });
      this.init(r.synthese);
      this.canRestore.set(r.can_restore);
      this.flash('Enregistré — la présentation est à jour.', false);
      this.saved.emit();
    } catch (e) {
      this.flash(this.detail(e), true);
    } finally {
      this.busy.set(false);
    }
  }

  async restore(): Promise<void> {
    if (!confirm("Restaurer la synthèse d'origine ? Tes modifications seront perdues.")) return;
    this.busy.set(true);
    try {
      const r = await this.api.restoreSynthese(this.job().id);
      this.init(r.synthese);
      this.canRestore.set(false);
      this.flash("Version d'origine restaurée.", false);
      this.saved.emit();
    } catch (e) {
      this.flash(this.detail(e), true);
    } finally {
      this.busy.set(false);
    }
  }

  private detail(e: unknown): string {
    const d = (e as { error?: { detail?: unknown } }).error?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length) return `Données invalides : ${(d[0] as { msg?: string }).msg ?? 'vérifie les champs'}`;
    return `Échec : ${(e as Error).message}`;
  }

  private flash(m: string, err: boolean): void {
    this.msg.set(m);
    this.isErr.set(err);
    setTimeout(() => this.msg() === m && this.msg.set(''), 5000);
  }
}
