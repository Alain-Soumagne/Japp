import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ExQuestion, ExercisesService, TYPE_LABEL } from './exercises.service';
import { ApiService } from './api.service';

@Component({
  selector: 'app-exercises',
  template: `
    <section class="ex">
      @if (ex.error()) { <p class="err" role="alert">{{ ex.error() }}</p> }

      @if (s(); as ses) {
        <button class="link back" (click)="ex.close()">← Retour aux exercices</button>

        @switch (ses.status) {
          @case ('generating') {
            <div class="wait"><i class="spin"></i><h2>Préparation de la session…</h2><p>{{ ses.message }}</p>
              <p class="muted">Le modèle local lit tes cours et écrit les questions. Ça prend quelques secondes à une minute.</p></div>
          }
          @case ('grading') {
            <div class="wait"><i class="spin"></i><h2>Correction en cours…</h2><p>{{ ses.message }}</p></div>
          }
          @case ('error') {
            <div class="bad"><strong>La session a échoué.</strong><pre>{{ ses.error }}</pre><button (click)="ex.close()">Retour</button></div>
          }
          @case ('ready') {
            <!-- ============ QUESTIONS ============ -->
            @if (ses.notice) { <p class="note">{{ ses.notice }}</p> }
            @if (ex.current(); as q) {
              <div class="bar"><div [style.width.%]="(ex.index() + 1) / ses.questions.length * 100"></div></div>
              <p class="meta">Question {{ ex.index() + 1 }} sur {{ ses.questions.length }} · <span class="tag">{{ label(q.type) }}</span> · {{ q.course }}</p>
              <div class="q">
                <p class="prompt" [class.jp]="isJp(q)" [attr.lang]="isJp(q) ? 'ja' : null">{{ shown(q) }}</p>
                @if (q.hint) { <p class="hint">{{ q.hint }}</p> }
                @if (q.type === 'mcq') {
                  <div class="choices" role="radiogroup">
                    @for (c of q.choices ?? []; track $index) {
                      <button class="choice" role="radio" [attr.aria-checked]="ex.answers()[q.id] === '' + $index"
                              [class.on]="ex.answers()[q.id] === '' + $index" (click)="ex.setAnswer(q.id, '' + $index)">
                        <b>{{ 'ABCD'[$index] }}</b>{{ c }}
                      </button>
                    }
                  </div>
                } @else if (q.type === 'short') {
                  <textarea rows="3" lang="fr" maxlength="600" [value]="ex.answers()[q.id] ?? ''" (input)="ex.setAnswer(q.id, $any($event.target).value)"
                            placeholder="Ta réponse…" aria-label="Ta réponse"></textarea>
                } @else {
                  <input type="text" maxlength="600" autocomplete="off" spellcheck="false" [attr.lang]="q.type === 'translate_ja_fr' ? 'fr' : 'ja'"
                         [value]="ex.answers()[q.id] ?? ''" (input)="ex.setAnswer(q.id, $any($event.target).value)"
                         [placeholder]="placeholder(q)"
                         aria-label="Ta réponse" />
                }
              </div>
              <div class="nav">
                <button class="ghost" [disabled]="ex.index() === 0" (click)="go(-1)">← Précédente</button>
                <span class="dots">
                  @for (qq of ses.questions; track qq.id; let i = $index) {
                    <button class="dot" [class.on]="i === ex.index()" [class.done]="!!(ex.answers()[qq.id] ?? '').trim()"
                            [attr.aria-label]="'Question ' + (i + 1)" (click)="jump(i)"></button>
                  }
                </span>
                @if (ex.index() < ses.questions.length - 1) {
                  <button (click)="go(1)">Suivante →</button>
                } @else {
                  <button class="primary" [disabled]="ex.busy()" (click)="submit()">Envoyer pour correction</button>
                }
              </div>
              <p class="muted small">{{ ex.answered() }} / {{ ses.questions.length }} réponses saisies. Tu peux revenir en arrière avant d'envoyer. Les réponses en japonais peuvent s'écrire en kana, en kanji ou en romaji.</p>
            }
          }
          @default {
            <!-- ============ CORRECTION / RÉSULTAT ============ -->
            @if (ses.status === 'finalized' && ses.result; as r) {
              <div class="final">
                <p class="kicker">Session terminée</p>
                <div class="score"><span class="big">{{ r.score.toFixed(0) }}</span><span class="of">/ 100</span></div>
                <p class="lvl"><span class="from">{{ r.level_before.toFixed(1) }}</span><span class="arrow">→</span><b class="to">{{ r.level_after.toFixed(1) }}</b>
                  <span class="delta" [class.up]="r.delta > 0.005" [class.down]="r.delta < -0.005">{{ r.delta > 0 ? '+' : '' }}{{ r.delta.toFixed(2) }}</span></p>
                <p class="lname">Niveau {{ r.label }} <small>(échelle de 1 à 10)</small></p>
                <p class="muted">{{ r.answered }} réponse{{ (r.answered ?? 0) > 1 ? 's' : '' }} sur {{ r.total }} · difficulté moyenne {{ r.mean_difficulty }}/10
                  @if (r.excluded) { · {{ r.excluded }} question(s) exclue(s) }</p>
                <p class="advice">{{ advice(r.delta) }}</p>
                @if (courseScores(r.by_course); as cs) {
                  @if (cs.length > 1) {
                    <ul class="by">@for (c of cs; track c[0]) { <li><span>{{ c[0] }}</span><i><b [style.width.%]="c[1]"></b></i><em>{{ c[1].toFixed(0) }}</em></li> }</ul>
                  }
                }
                <button class="primary" (click)="ex.close()">Nouvelle session</button>
              </div>
            } @else if (ses.result; as r) {
              <div class="prov">
                <div>
                  <p class="kicker">Correction</p>
                  <h2>Score provisoire : {{ r.score.toFixed(0) }} / 100</h2>
                  <p class="muted">Niveau prévu : {{ r.level_before.toFixed(1) }} → {{ r.level_after.toFixed(1) }}.
                    Relis les corrections et conteste celles que tu estimes fausses : le modèle les réexamine une fois, sa décision est finale.</p>
                </div>
                <button class="primary" [disabled]="ex.busy()" (click)="finish()">Terminer et valider mon score</button>
              </div>
            }
            @if (ses.notice) { <p class="note">{{ ses.notice }}</p> }

            @for (q of ses.questions; track q.id; let i = $index) {
              <article class="rq" [attr.data-v]="q.excluded ? 'excluded' : q.verdict">
                <header>
                  <span class="n">{{ i + 1 }}</span><span class="tag">{{ label(q.type) }}</span>
                  <span class="badge">{{ q.excluded ? 'Exclue du score' : verdict(q) }}</span>
                </header>
                <p class="prompt" [class.jp]="isJp(q)" [attr.lang]="isJp(q) ? 'ja' : null">{{ shown(q) }}</p>
                <p class="line"><b>Ta réponse</b> {{ mine(q) || '—' }}</p>
                <p class="line"><b>Référence</b> {{ q.reference }}</p>
                <p class="fb">{{ q.feedback }} <small>({{ by(q) }})</small></p>
                @if (q.explanation) { <p class="expl">{{ q.explanation }}</p> }

                @if (q.contest; as c) {
                  <div class="contest">
                    <b>Ta contestation</b> « {{ c.argument }} »
                    <p><b>Réexamen :</b> {{ c.changed ? 'verdict modifié (' + vlabel(c.previous) + ' → ' + vlabel(c.verdict) + ')' : 'verdict maintenu' }}. {{ c.feedback }}</p>
                    @if (ses.status === 'graded' && q.verdict !== 'correct' && !q.excluded) {
                      <button class="ghost" (click)="ex.exclude(q.id)">Je reste en désaccord : exclure cette question du score</button>
                    }
                  </div>
                } @else if (ses.status === 'graded' && q.verdict !== 'correct') {
                  @if (open() === q.id) {
                    <div class="contest">
                      <label>Pourquoi cette correction te semble-t-elle fausse ?
                        <textarea rows="3" maxlength="1000" [value]="why()" (input)="why.set($any($event.target).value)"></textarea></label>
                      <div class="row">
                        <button class="primary" [disabled]="why().trim().length < 3 || ex.busy()" (click)="sendContest(q.id)">{{ ex.busy() ? 'Réexamen…' : 'Envoyer' }}</button>
                        <button class="ghost" (click)="open.set(null)">Annuler</button>
                      </div>
                    </div>
                  } @else { <button class="ghost" (click)="open.set(q.id); why.set('')">Contester cette correction</button> }
                }
              </article>
            }
          }
        }
      
      } @else {
        <!-- ============ ACCUEIL ============ -->
        <p class="kicker">Exercices</p>
        <h1>Révise ce que tu as appris.</h1>

        @if (ex.profile(); as p) {
          <div class="level">
            <div>
              <span class="lv">{{ p.level.toFixed(1) }}</span><span class="of">/ 10</span>
              <strong>{{ p.label }}</strong>
              <small>{{ p.sessions }} session{{ p.sessions > 1 ? 's' : '' }} terminée{{ p.sessions > 1 ? 's' : '' }}</small>
            </div>
            @if (chart(); as c) {
              <svg viewBox="0 0 320 90" class="chart" role="img" [attr.aria-label]="'Évolution du niveau sur ' + p.history.length + ' sessions'">
                <polyline [attr.points]="c" fill="none" stroke="var(--red)" stroke-width="3" stroke-linejoin="round" />
              </svg>
            } @else { <p class="muted">Ta courbe de progression apparaîtra après ta première session.</p> }
          </div>
        }

        <h2>Nouvelle session</h2>
        @if (!ex.courses().length) {
          <p class="muted">Aucun cours terminé pour l'instant : transcris d'abord un cours, puis reviens ici.</p>
        } @else {
          <p class="muted">Choisis les cours à inclure. Le modèle local prépare des questions adaptées à ton niveau, tirées uniquement de ces cours.</p>
          <ul class="courses">
            @for (c of ex.courses(); track c.id) {
              <li>
                <label class="pick"><input type="checkbox" [checked]="chosen().has(c.id)" (change)="toggle(c.id)" />
                  <span class="nm">{{ c.name }}</span>
                  <span class="chip">difficulté {{ c.difficulty.toFixed(1) }}/10</span>
                  <span class="chip">{{ c.examples }} exemples</span>
                </label>
              </li>
            }
          </ul>
          <div class="opts">
            <label>Nombre de questions
              <select (change)="count.set(+$any($event.target).value)">
                @for (n of [5, 10, 15, 20, 30]; track n) { <option [value]="n" [selected]="n === count()">{{ n }}</option> }
              </select>
            </label>
            <label>Modèle
              <select (change)="model.set($any($event.target).value)">
                <option value="">Par défaut ({{ ex.profile()?.default_model }})</option>
                @for (m of models(); track m) { <option [value]="m">{{ m }}</option> }
              </select>
            </label>
          </div>
          <div class="go"><button class="primary" (click)="start()" [disabled]="!chosen().size || ex.busy()">Démarrer la session</button>
            @if (!chosen().size) { <span class="muted">Coche au moins un cours.</span> }</div>
        }

        @if (ex.past().length) {
          <h2>Sessions précédentes</h2>
          <ul class="past">
            @for (p of ex.past(); track p.id) {
              <li>
                <button class="row" (click)="ex.resume(p.id)">
                  <span class="d">{{ date(p.created) }}</span>
                  <span class="nm">{{ p.course_names.join(', ') }}</span>
                  <span class="chip">{{ p.count }} q.</span>
                  <span class="st" [attr.data-s]="p.status">{{ pastLabel(p) }}</span>
                </button>
                <button class="icon" title="Supprimer cette session" (click)="remove(p.id)">✕</button>
              </li>
            }
          </ul>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; }
    .ex { max-width: 860px; padding: 48px 48px 64px; }
    .kicker { font-size: 13px; letter-spacing: .22em; text-transform: uppercase; color: var(--red); font-weight: 600; margin: 0; }
    h1 { font: 700 44px/1.12 var(--serif); margin: 12px 0 28px; }
    h2 { font: 700 24px var(--serif); margin: 34px 0 8px; }
    .muted { color: #5f584e; font-size: 14px; margin: 6px 0; }
    .small { font-size: 13px; }
    .err { color: var(--red); background: var(--red-soft); padding: 10px 14px; margin: 0 0 14px; }
    .note { background: #f6ecd2; border-left: 4px solid #c79a2a; padding: 10px 14px; font-size: 14px; }
    button { font: 600 14px var(--sans); padding: 10px 18px; border: 1.5px solid var(--ink); background: var(--ink); color: #fff; cursor: pointer; }
    button:hover:not(:disabled) { background: var(--red); border-color: var(--red); }
    button:disabled { opacity: .4; cursor: default; }
    button.ghost { background: none; color: var(--ink); }
    button.ghost:hover:not(:disabled) { color: #fff; }
    button.primary { background: var(--red); border-color: var(--red); padding: 12px 24px; font-size: 15px; }
    button.primary:hover:not(:disabled) { background: var(--ink); border-color: var(--ink); }
    button.link, .link { background: none; border: 0; color: var(--red); padding: 0 0 14px; }
    button.link:hover:not(:disabled) { background: none; text-decoration: underline; color: var(--red); }
    .level { display: flex; gap: 32px; align-items: center; justify-content: space-between; background: var(--card); border: 1px solid var(--line); border-top: 4px solid var(--ink); padding: 20px 26px; }
    .lv { font: 700 64px/1 var(--serif); color: var(--red); }
    .of { color: var(--muted); margin-left: 6px; }
    .level strong { display: block; font: 700 20px var(--serif); } .level small { color: var(--muted); }
    .chart { width: 320px; max-width: 45%; height: 90px; background: repeating-linear-gradient(0deg, transparent 0 21px, var(--line) 21px 22px); }
    .courses, .past { list-style: none; margin: 14px 0; padding: 0; display: grid; gap: 8px; }
    .pick { display: flex; gap: 12px; align-items: center; background: var(--card); border: 1px solid var(--line); padding: 12px 16px; cursor: pointer; color: var(--ink); font-size: 15px; letter-spacing: 0; }
    .pick:hover { border-color: var(--ink); }
    .pick input { width: 18px; height: 18px; accent-color: var(--red); }
    .nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
    .chip { font: 600 12px var(--sans); background: var(--paper2); padding: 3px 8px; color: #4a443b; white-space: nowrap; }
    .opts { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 16px 0 20px; }
    .past li { display: flex; gap: 6px; }
    .past .row { flex: 1; display: flex; gap: 14px; align-items: center; background: var(--card); color: var(--ink); border: 1px solid var(--line); text-align: left; font-weight: 400; }
    .past .row:hover:not(:disabled) { background: var(--card); border-color: var(--ink); color: var(--ink); }
    .past .d { color: var(--muted); font-size: 13px; min-width: 90px; }
    .past .st { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
    .past .st[data-s='finalized'] { color: #3f6b57; }
    .icon { background: none; color: var(--muted); border: 1px solid var(--line); padding: 0 12px; }
    .wait { text-align: center; padding: 70px 0; }
    .spin { display: inline-block; width: 34px; height: 34px; border: 4px solid var(--line); border-top-color: var(--red); border-radius: 50%; animation: r 1s linear infinite; }
    @keyframes r { to { transform: rotate(360deg); } }
    .bad { background: var(--red-soft); border: 1px solid var(--red); padding: 18px 22px; } .bad pre { white-space: pre-wrap; font-size: 13px; }
    .bar { height: 6px; background: var(--paper2); } .bar div { height: 100%; background: var(--red); transition: width .25s; }
    .meta { color: var(--muted); font-size: 14px; margin: 12px 0 0; } .tag { font-weight: 700; color: var(--ink); }
    .q { background: var(--card); border: 1px solid var(--line); border-top: 3px solid var(--ink); padding: 28px 30px; margin: 14px 0; }
    .prompt { font: 600 24px/1.4 var(--sans); margin: 0 0 8px; } .prompt.jp { font: 700 34px/1.4 var(--serif); }
    .hint { color: var(--muted); font-size: 14px; margin: 0 0 16px; }
    .q input[type=text], .q textarea { width: 100%; font: 20px var(--sans); padding: 12px 14px; border: 1.5px solid var(--ink); background: #fff; }
    .q input:focus, .q textarea:focus { outline: 3px solid var(--red); outline-offset: 1px; }
    .choices { display: grid; gap: 10px; }
    .choice { display: flex; gap: 14px; align-items: center; text-align: left; background: #fff; color: var(--ink); border: 1.5px solid var(--line); font-weight: 400; font-size: 17px; padding: 14px 16px; }
    .choice b { background: var(--paper2); width: 28px; height: 28px; display: grid; place-items: center; } .choice:hover:not(:disabled) { background: #fff; color: var(--ink); border-color: var(--ink); }
    .choice.on { border-color: var(--red); background: var(--red-soft); } .choice.on b { background: var(--red); color: #fff; }
    .nav { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .dots { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
    .dot { width: 18px; height: 18px; padding: 0; border: 1.5px solid var(--ink); background: none; border-radius: 50%; }
    .dot.done { background: var(--ink); } .dot.on { outline: 3px solid var(--red); outline-offset: 2px; }
    .prov { display: flex; gap: 24px; justify-content: space-between; align-items: center; background: var(--card); border: 1px solid var(--line); border-top: 4px solid var(--red); padding: 18px 24px; margin-bottom: 20px; }
    .prov h2 { margin: 4px 0; } .prov button { flex: none; }
    .final { text-align: center; padding: 30px 0 20px; }
    .score { display: flex; justify-content: center; align-items: baseline; gap: 8px; }
    .score .big { font: 700 120px/1 var(--serif); color: var(--ink); } .score .of { font-size: 26px; margin: 0; }
    .lvl { font-size: 26px; margin: 14px 0 2px; display: flex; justify-content: center; align-items: center; gap: 12px; }
    .lvl .from { color: var(--muted); } .lvl .arrow { color: var(--muted); } .lvl .to { font: 700 34px var(--serif); }
    .delta { font: 700 14px var(--sans); padding: 4px 10px; background: var(--paper2); color: var(--muted); }
    .delta.up { background: #dcebe2; color: #2f5b45; } .delta.down { background: var(--red-soft); color: var(--red); }
    .lname { margin: 0 0 14px; font-weight: 600; } .lname small { color: var(--muted); font-weight: 400; }
    .advice { display: inline-block; max-width: 560px; background: var(--card); border-left: 4px solid var(--red); padding: 10px 16px; margin: 10px 0 22px; text-align: left; }
    .final .primary { margin-top: 6px; } .final + .rq { margin-top: 34px; }
    .by { list-style: none; padding: 0; margin: 20px auto; max-width: 520px; display: grid; gap: 8px; text-align: left; }
    .by li { display: grid; grid-template-columns: 1fr 140px 36px; gap: 10px; align-items: center; font-size: 14px; }
    .by i { height: 8px; background: var(--paper2); } .by b { display: block; height: 100%; background: var(--red); } .by em { font-style: normal; font-weight: 700; text-align: right; }
    .rq { background: var(--card); border: 1px solid var(--line); border-left: 6px solid var(--line); padding: 16px 22px; margin: 14px 0; }
    .rq[data-v='correct'] { border-left-color: #3f6b57; } .rq[data-v='partial'] { border-left-color: #c79a2a; }
    .rq[data-v='incorrect'] { border-left-color: var(--red); } .rq[data-v='excluded'] { border-left-color: #8f887a; opacity: .75; }
    .rq header { display: flex; gap: 12px; align-items: center; } .rq .n { font: 700 20px var(--serif); color: var(--red); }
    .badge { margin-left: auto; font: 700 12px var(--sans); letter-spacing: .08em; text-transform: uppercase; }
    .rq[data-v='correct'] .badge { color: #3f6b57; } .rq[data-v='partial'] .badge { color: #9a741a; } .rq[data-v='incorrect'] .badge { color: var(--red); }
    .rq[data-v='correct'] .n { color: #3f6b57; } .rq[data-v='excluded'] .n { color: #8f887a; }
    .go { display: flex; gap: 14px; align-items: center; }
    .rq .prompt { font-size: 18px; } .rq .prompt.jp { font-size: 24px; }
    .line { margin: 4px 0; font-size: 15px; } .line b { display: inline-block; min-width: 92px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .fb { margin: 8px 0 4px; font-weight: 600; } .fb small { font-weight: 400; color: var(--muted); }
    .expl { margin: 4px 0; color: var(--muted); font-size: 14px; }
    .contest { background: var(--paper); border: 1px dashed #8f887a; padding: 12px 14px; margin-top: 10px; font-size: 14px; }
    .contest textarea { width: 100%; font: 15px var(--sans); padding: 8px 10px; border: 1px solid var(--ink); }
    .row { display: flex; gap: 10px; margin-top: 8px; }
    label { display: grid; gap: 6px; font-size: 13px; color: var(--muted); font-weight: 600; }
    select { font: 15px var(--sans); padding: 10px 12px; border: 1px solid var(--ink); background: var(--card); color: var(--ink); }
  `,
})
export class Exercises implements OnInit, OnDestroy {
  readonly ex = inject(ExercisesService);
  private readonly api = inject(ApiService);

  readonly s = this.ex.session;
  readonly chosen = signal(new Set<string>());
  readonly count = signal(10);
  readonly model = signal('');
  readonly open = signal<string | null>(null);
  readonly why = signal('');
  readonly models = computed(() => this.api.health()?.llm_choices ?? []);

  readonly chart = computed(() => {
    const h = this.ex.profile()?.history.slice(-30) ?? [];
    if (h.length < 2) return null;
    const lv = h.map((x) => x.level_after);
    const lo = Math.min(...lv, 1), hi = Math.max(...lv, 3);
    return lv.map((v, i) => `${(i / (lv.length - 1)) * 316 + 2},${86 - ((v - lo) / (hi - lo)) * 80}`).join(' ');
  });

  ngOnInit(): void { if (!this.ex.session()) this.ex.loadHome(); }
  ngOnDestroy(): void { /* la session reste en mémoire : on peut changer d'onglet sans la perdre */ }

  toggle(id: string): void {
    this.chosen.update((c) => { const n = new Set(c); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  start(): void { this.ex.start([...this.chosen()], this.count(), this.model()); }

  label(t: string): string { return TYPE_LABEL[t] ?? t; }
  isJp(q: ExQuestion): boolean { return ['translate_ja_fr', 'reading', 'cloze'].includes(q.type); }
  vlabel(v: string): string { return v === 'correct' ? 'Correct' : v === 'partial' ? 'Partiel' : 'Incorrect'; }
  verdict(q: ExQuestion): string { return this.vlabel(q.verdict ?? 'incorrect'); }
  by(q: ExQuestion): string { return q.graded_by === 'auto' ? 'correction automatique' : q.graded_by === 'ia' ? 'corrigé par le modèle' : 'correction approximative'; }
  mine(q: ExQuestion): string {
    if (q.type === 'mcq' && /^\d$/.test(q.answer)) return q.choices?.[+q.answer] ?? '';
    return q.answer;
  }
  date(t: number): string { return new Date(t * 1000).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' }); }
  pastLabel(p: { status: string; result: { score: number } | null }): string {
    return p.status === 'finalized' ? `${p.result?.score.toFixed(0)} / 100` : p.status === 'graded' ? 'à valider' : p.status === 'ready' ? 'en cours' : p.status === 'error' ? 'échec' : '…';
  }
  courseScores(m?: Record<string, number>): [string, number][] | null { return m ? Object.entries(m) : null; }
  advice(d: number): string {
    return d > 0.15 ? 'Belle progression : la prochaine session sera un cran plus exigeante.'
      : d < -0.15 ? 'Pas de souci : la prochaine session reviendra un peu en arrière pour consolider.'
      : 'Niveau stable : la prochaine session restera proche de celle-ci.';
  }

  shown(q: ExQuestion): string { return q.type === 'cloze' ? q.prompt.replace('＿', '［　？　］') : q.prompt; }
  placeholder(q: ExQuestion): string {
    return q.type === 'translate_ja_fr' ? 'Ta traduction en français…' : q.type === 'cloze' ? 'La particule manquante…'
      : q.type === 'reading' ? 'La lecture en romaji…' : 'Ta réponse en japonais (kana, kanji ou romaji)…';
  }

  go(d: number): void { this.ex.saveDraft(); this.ex.index.update((i) => i + d); }
  jump(i: number): void { this.ex.saveDraft(); this.ex.index.set(i); }
  async submit(): Promise<void> {
    const blanks = (this.s()?.questions.length ?? 0) - this.ex.answered();
    if (blanks > 0 && !confirm(`${blanks} question(s) sans réponse comptera(ont) pour zéro. Envoyer quand même ?`)) return;
    await this.ex.submit();
  }
  async sendContest(qid: string): Promise<void> {
    if (await this.ex.contest(qid, this.why().trim())) this.open.set(null);
  }
  async finish(): Promise<void> {
    if (confirm('Valider le score ? Après cela, tu ne pourras plus contester de correction.')) await this.ex.finalize();
  }
  async remove(id: string): Promise<void> {
    if (confirm('Supprimer cette session ?')) await this.ex.remove(id);
  }
}
