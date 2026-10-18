"""Niveau, difficulté, score : logique pure (sans I/O), entièrement testable.

Échelle : 1 (débutant) à 10 (expert), continue.

 - difficulté d'un exemple  : longueur de la phrase + part de kanji (1..10)
 - difficulté d'un cours    : moyenne des exemples + structure du cours (nombre de notions, densité de points clés)
 - difficulté d'une question: mélange exemple/cours + décalage selon le type de question
 - sélection d'une session  : mélange 20 % plus facile (révision), 60 % juste au-dessus du niveau, 20 % un cran au-dessus
 - score de session (0-100) : réussite pondérée par la difficulté (une question difficile compte plus)
 - nouveau niveau           : niveau + K × (réussite réelle - réussite attendue), limité à ±0,5 par session
                              => progression continue, jamais de saut brutal ("pas de mur de difficulté")
"""
import math
import random
import re
from collections.abc import Iterable

LEVEL_MIN, LEVEL_MAX, LEVEL_START = 1.0, 10.0, 1.5
MAX_STEP = 0.5            # variation maximale du niveau par session
K = 2.0                   # sensibilité
SLOPE = 0.8               # pente de la courbe de réussite attendue
MIX = ((0.2, -1.0), (0.6, 0.3), (0.2, 1.3))   # (part des questions, décalage par rapport au niveau)
FULL_EVIDENCE = 8         # nombre de questions à partir duquel une session compte pleinement

TYPE_OFFSET = {"reading": -1.5, "mcq": -0.5, "cloze": 0.0, "translate_ja_fr": 0.0, "short": 0.8, "translate_fr_ja": 1.2}
POINTS = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}

_KANJI = re.compile(r"[\u4e00-\u9fff々]")
_JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
LABELS = ((2.0, "Débutant"), (4.0, "Élémentaire"), (6.0, "Intermédiaire"), (8.0, "Avancé"), (10.01, "Expert"))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def level_label(level: float) -> str:
    return next(name for limit, name in LABELS if level < limit)


def example_difficulty(japanese: str) -> float:
    chars = [c for c in japanese if _JA.match(c)]
    if not chars:
        return 1.0
    kanji = sum(1 for c in chars if _KANJI.match(c)) / len(chars)
    return clamp(1 + 4 * min(len(chars) / 18, 1) + 5 * min(kanji / 0.5, 1), 1.0, 10.0)


def course_difficulty(synthese: dict) -> float:
    sections = synthese.get("sections") or []
    examples = [e for s in sections for e in s.get("examples") or [] if e.get("japanese")]
    if not sections:
        return 2.0
    ex = sum(example_difficulty(e["japanese"]) for e in examples) / len(examples) if examples else 2.0
    kp = sum(len(s.get("key_points") or []) for s in sections) / len(sections)
    structure = 1 + 3 * min(len(sections) / 8, 1) + 2 * min(kp / 4, 1)          # 1..6
    return round(clamp(0.6 * ex + 0.4 * structure * 1.6, 1.0, 10.0), 1)


def question_difficulty(qtype: str, example_diff: float | None, course_diff: float) -> float:
    base = course_diff if example_diff is None else 0.65 * example_diff + 0.35 * course_diff
    return round(clamp(base + TYPE_OFFSET.get(qtype, 0.0), 1.0, 10.0), 2)


def expected_success(level: float, difficulty: float) -> float:
    return 1 / (1 + math.exp(-SLOPE * (level - difficulty)))


def select_questions(pool: list[dict], n: int, level: float, rng: random.Random | None = None) -> list[dict]:
    """Choisit n questions dont les difficultés suivent le mélange cible, en variant les types."""
    rng = rng or random.Random()  # noqa: S311 - tirage pédagogique, sans enjeu de sécurité
    n = min(n, len(pool))
    counts = [round(share * n) for share, _ in MIX]
    counts[1] += n - sum(counts)                       # le reste va au cœur de cible
    targets = [level + off for (_, off), c in zip(MIX, counts, strict=True) for _ in range(c)]
    left = pool[:]
    rng.shuffle(left)
    used_types: dict[str, int] = {}
    used_keys: set[str] = set()
    chosen: list[dict] = []
    for t in sorted(targets):
        def cost(q: dict, t: float = t) -> float:
            dup = 2.0 if q.get("key") in used_keys else 0.0              # évite la même phrase sous plusieurs formes
            return abs(q["difficulty"] - t) + 0.5 * used_types.get(q["type"], 0) + dup
        best = min(left, key=cost)
        left.remove(best)
        chosen.append(best)
        used_types[best["type"]] = used_types.get(best["type"], 0) + 1
        if best.get("key"):
            used_keys.add(best["key"])
    rng.shuffle(chosen)
    return chosen


def _scored(questions: Iterable[dict]) -> list[dict]:
    return [q for q in questions if not q.get("excluded") and q.get("verdict") in POINTS]


def session_score(questions: Iterable[dict]) -> float:
    qs = _scored(questions)
    total = sum(q["difficulty"] for q in qs)
    if not total:
        return 0.0
    return round(100 * sum(q["difficulty"] * POINTS[q["verdict"]] for q in qs) / total, 1)


def level_delta(level: float, questions: Iterable[dict]) -> float:
    qs = _scored(questions)
    if not qs:
        return 0.0
    gap = sum(POINTS[q["verdict"]] - expected_success(level, q["difficulty"]) for q in qs) / len(qs)
    delta = K * gap * min(1.0, len(qs) / FULL_EVIDENCE)
    return round(clamp(delta, -MAX_STEP, MAX_STEP), 2)


def next_level(level: float, questions: Iterable[dict]) -> float:
    return round(clamp(level + level_delta(level, questions), LEVEL_MIN, LEVEL_MAX), 2)
