"""Vocabulaire d'un cours de japonais : mot (kanji) + lecture (kana) + traduction, extrait par le modèle puis VALIDÉ.

Garde-fous (le modèle ne peut pas inventer un mot qui n'a pas été prononcé) :
 1. le mot « tel qu'entendu » doit figurer dans la transcription (romaji, ou écriture japonaise selon la transcription) ;
 2. la lecture en kana proposée doit être cohérente avec le mot (conversion romaji -> kana indépendante du modèle) ;
 3. les kanji ne sont gardés que s'ils sont réellement des kanji ; traduction obligatoire ; doublons retirés ;
 4. les phrases, les syllabes isolées et les entrées dont la « traduction » est le mot lui-même (noms propres…) sont écartées.
"""
import difflib
import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path

from .kana import has_japanese, has_kanji, loose

FILE = "vocabulary.json"
MAX_ENTRIES = 600

SCHEMA = {"type": "object", "properties": {"words": {"type": "array", "items": {"type": "object", "properties": {
    "heard": {"type": "string"}, "kanji": {"type": "string"}, "kana": {"type": "string"}, "french": {"type": "string"}},
    "required": ["heard", "kanji", "kana", "french"]}}}, "required": ["words"]}

PROMPT = """Voici un EXTRAIT (partie {i}/{n}) de la transcription automatique d'un cours de japonais. Les mots japonais sont écrits en romaji ou en écriture japonaise selon l'extrait.
Liste le VOCABULAIRE japonais utile que le cours présente ou emploie (noms, verbes, adjectifs, expressions courtes ; pas les particules seules, pas les mots français).
Pour chaque mot :
- heard : le mot EXACTEMENT comme il apparaît dans l'extrait (recopié, jamais corrigé ni inventé) ;
- kanji : son écriture usuelle avec kanji si elle existe (sinon une chaîne vide) ;
- kana : sa lecture complète en hiragana (ou en katakana pour les mots d'origine étrangère) ;
- french : sa traduction courte en français.
Règles : uniquement des mots ou expressions courtes (1 à 3 mots) réellement présents dans l'extrait, JAMAIS une phrase entière ;
pas de prénoms ni de noms de personnages ou de marques ; pas les syllabes isolées d'un tableau de hiragana (し, さ, す…) ; pas les particules seules ;
aucune explication ; texte brut. Maximum 40 mots.

EXTRAIT :
{text}
"""


def _nfkc(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


_PARTICLES = {"wa", "ha", "wo", "o", "ga", "ni", "de", "no", "mo", "to", "ka", "ne", "yo", "desu", "masu", "deshita", "imasu", "shimasu"}
_SYLLABLES = re.compile(r"^([a-z]{1,4})(-[a-z]{1,4})+$")


def looks_like_sentence(heard: str) -> bool:
    """Phrase entière (et non un mot / une expression courte) ? Heuristique volontairement prudente."""
    if has_japanese(heard):
        s = _nfkc(heard)
        if s.endswith("ございます"):
            return len(s) > 14
        return (len(s) > 9 or bool(re.search(r"(です|ます|ました|ません)(か)?$", s))
                or bool(re.search(r"[\u4e00-\u9fff\u30a0-\u30ff](は|を|が)", s)) and len(s) >= 4)
    toks = re.findall(r"[^\W\d_]+", heard.lower())
    return len(toks) >= 4 or (len(toks) >= 3 and any(t in _PARTICLES for t in toks))


def display_romaji(heard: str) -> str:
    """« a-ka-i » (syllabes épelées par le professeur) -> « akai » ; « minna-san » reste inchangé."""
    h = heard.strip()
    return h.replace("-", "") if _SYLLABLES.match(h.lower()) else h


def entry_id(word: str, kana: str) -> str:
    return hashlib.sha1(f"{word}|{kana}".encode()).hexdigest()[:8]  # noqa: S324 - identifiant, pas de sécurité


def validate(raw: list[dict], text: str) -> list[dict]:
    """Applique les garde-fous. `raw` : mots bruts du modèle ; `text` : transcription complète."""
    n_all = " " + _norm(text) + " "
    jp_all = _nfkc(text)
    out, seen = [], set()
    for w in raw:
        heard = (w.get("heard") or "").strip()
        kana = (w.get("kana") or "").strip()
        french = re.sub(r"\s+", " ", (w.get("french") or "")).strip()
        kanji = (w.get("kanji") or "").strip()
        if not heard or not kana or not french or len(heard) > 60 or len(french) > 120:
            continue
        if looks_like_sentence(heard) or _norm(french) == _norm(heard) or (len(kana) == 1 and not has_kanji(kanji)):
            continue
        # 1. présent dans la transcription
        if has_japanese(heard):
            if _nfkc(heard) not in jp_all:
                continue
        else:
            h = _norm(heard)
            if len(h) < 2 or f" {h} " not in n_all and h not in n_all:
                continue
        # 2. lecture cohérente avec le mot entendu
        if not has_japanese(kana):
            continue
        #    (impossible à comparer si le mot entendu est déjà écrit en kanji : seule sa présence dans le texte fait alors foi)
        if not has_kanji(heard) and difflib.SequenceMatcher(None, loose(heard), loose(kana)).ratio() < 0.75:
            continue
        # 3. kanji réels uniquement
        if kanji and (not has_kanji(kanji) or len(kanji) > 30):
            kanji = ""
        word = kanji or kana
        key = (word, loose(kana))
        if key in seen:
            continue
        seen.add(key)
        romaji = display_romaji(heard) if not has_japanese(heard) else ""
        out.append({"id": entry_id(word, kana), "word": word, "kana": kana, "romaji": romaji, "french": french,
                    "has_kanji": bool(kanji)})
    return out[:MAX_ENTRIES]


def extract(text: str, model: str, on_progress: Callable[[float, str], None] | None = None) -> list[dict]:
    from .summarize import call, chunks
    lines = [ln for ln in text.splitlines() if ln.strip()]
    parts = chunks(lines, 110) if lines else []
    raw: list[dict] = []
    for i, part in enumerate(parts, 1):
        if on_progress:
            on_progress((i - 1) / max(len(parts), 1), f"Vocabulaire : extrait {i}/{len(parts)}…")
        d = call(model, PROMPT.format(text="\n".join(part), i=i, n=len(parts)), SCHEMA)
        raw += d.get("words", [])
    return validate(raw, text)


def save(job_dir: Path, entries: list[dict], model: str) -> None:
    (job_dir / FILE).write_text(json.dumps({"version": 1, "model": model, "entries": entries}, ensure_ascii=False, indent=1), encoding="utf-8")


def load(job_dir: Path) -> list[dict] | None:
    """None = vocabulaire jamais généré ; [] = généré mais vide."""
    p = job_dir / FILE
    if not p.exists():
        return None
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).get("entries") or [])
    except (OSError, ValueError):
        return None


def remove(job_dir: Path, eid: str) -> bool:
    entries = load(job_dir)
    if entries is None:
        return False
    kept = [e for e in entries if e.get("id") != eid]
    if len(kept) == len(entries):
        return False
    p = job_dir / FILE
    data = json.loads(p.read_text(encoding="utf-8"))
    data["entries"] = kept
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def csv_cell(v: str) -> str:
    """Neutralise l'injection de formules (Excel) et protège les guillemets."""
    v = str(v or "").replace("\r", " ").replace("\n", " ")
    if v[:1] in ("=", "+", "-", "@", "\t"):
        v = "'" + v
    return '"' + v.replace('"', '""') + '"'


def to_csv(rows: list[dict]) -> str:
    head = ["Mot", "Lecture", "Romaji", "Traduction", "Cours"]
    lines = [";".join(csv_cell(h) for h in head)]
    for r in rows:
        lines.append(";".join(csv_cell(r.get(k, "")) for k in ("word", "kana", "romaji", "french", "course")))
    return "\ufeff" + "\r\n".join(lines) + "\r\n"
