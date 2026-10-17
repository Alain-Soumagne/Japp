"""Synthèse locale d'une transcription de cours (Ollama) -> JSON structuré, avec garde-fous.
Pipeline : extraction par morceaux -> validation des exemples (citations présentes dans la transcription)
           -> fusion/regroupement des sections -> nettoyage.
Usage: python summarize.py transcription.txt [--model gemma4:e4b] [--out synthese.json]"""
import urllib.error
import difflib
import json
import re
import time
import unicodedata
import urllib.request

from .config import OLLAMA_URL
URL = OLLAMA_URL + "/api/chat"

# ---------- schémas ----------
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "examples": {"type": "array", "items": {"type": "object", "properties": {
                "quote": {"type": "string"}, "french": {"type": "string"}},
                "required": ["quote", "french"]}},
        }, "required": ["title", "key_points", "examples"]}},
        "homework": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sections", "homework"],
}
GROUP_SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "members": {"type": "array", "items": {"type": "integer"}}},
        "required": ["title", "members"]}},
        "title": {"type": "string"}, "subtitle": {"type": "string"}},
    "required": ["groups", "title", "subtitle"],
}

EXTRACT_PROMPT = """Tu es un assistant pédagogique. Voici un EXTRAIT (partie {i}/{n}) de la transcription automatique (Whisper) d'un cours de japonais donné en français.
La transcription contient des erreurs : corrige-les avec ton bon sens (« adjectifs en A » = adjectifs en na, etc.).
Produis en JSON, en français, les notions de grammaire/vocabulaire de CET extrait :
- sections : une par notion, avec key_points (règles courtes et exactes) et examples ;
- examples : « quote » = phrase japonaise EN ROMAJI recopiée MOT POUR MOT depuis l'extrait (jamais inventée, jamais de kana), « french » = sa traduction. S'il n'y a aucun exemple de ce type pour une notion, mets une liste vide ;
- homework : devoirs et conseils du professeur présents dans l'extrait (liste vide sinon).
Règles de forme STRICTES : texte brut (pas de markdown, pas de **, pas de LaTeX, pas de $) ; n'invente aucune notion ni phrase ; les hiragana sont à LIRE, pas à écrire, sauf indication contraire.

EXTRAIT :
{text}
"""

GROUP_PROMPT = """Voici la liste numérotée des sections extraites d'un cours de japonais, avec des doublons et des sections trop fines.
Regroupe-les en 6 à 8 sections finales logiques, dans l'ordre du cours. Chaque section finale a un titre court et la liste des numéros des sections sources qu'elle absorbe (chaque numéro dans UN seul groupe, aucun oublié).
Donne aussi un titre et un sous-titre pour la synthèse complète. Texte brut, en français.

SECTIONS :
{listing}
"""


def call(model, prompt, schema):
    body = {"model": model, "stream": False, "think": False,
            "messages": [{"role": "user", "content": prompt}], "format": schema,
            "options": {"temperature": 0.2}}  # pas de num_ctx par requête (plante gemma4 / Ollama 0.40.5)
    for attempt in range(4):  # 1er appel après chargement / JSON invalide -> 500 : on réessaie
        try:
            req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
            return json.loads(json.load(urllib.request.urlopen(req, timeout=1200))["message"]["content"])
        except (urllib.error.URLError, ConnectionError, json.JSONDecodeError):
            if attempt == 3:
                raise
            body["options"]["temperature"] = 0.2 + 0.2 * (attempt + 1)
            time.sleep(3)


# ---------- utilitaires ----------
def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clean(t):
    t = t.replace("$\\rightarrow$", "→").replace("**", "").replace("$", "")
    return re.sub(r"(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)", "", t).strip()


def chunks(lines, size=110):
    n = max(1, round(len(lines) / size))
    step = -(-len(lines) // n)
    return [lines[k:k + step] for k in range(0, len(lines), step)]


_FR = {"le", "la", "les", "des", "de", "du", "est", "un", "une", "je", "tu", "il", "on", "vous", "ce", "ca", "et", "que", "qui", "pas", "mais", "pour"}


def looks_french(q):
    if re.search(r"[àâçéèêëîïôùûœ']", q.lower()):
        return True
    return sum(w in _FR for w in norm(q).split()) >= 2


def quote_ok(quote, norm_lines, norm_all):
    q = norm(quote)
    if len(q) < 4 or looks_french(quote):
        return False
    if q in norm_all:
        return True
    best = max((difflib.SequenceMatcher(None, q, l).ratio() for l in norm_lines if l), default=0)
    return best >= 0.88


# romaji -> hiragana (approximatif : les noms propres en katakana restent en hiragana)
_SYL = {}
for base, kana in {"a": "あいうえお", "k": "かきくけこ", "s": "さしすせそ", "t": "たちつてと", "n": "なにぬねの",
                   "h": "はひふへほ", "m": "まみむめも", "r": "らりるれろ", "g": "がぎぐげご", "z": "ざじずぜぞ",
                   "d": "だぢづでど", "b": "ばびぶべぼ", "p": "ぱぴぷぺぽ"}.items():
    for v, k in zip("aiueo", kana):
        _SYL[v if base == "a" else base + v] = k
_SYL.update({"shi": "し", "chi": "ち", "tsu": "つ", "fu": "ふ", "ji": "じ", "wa": "わ", "wo": "を", "n": "ん",
             "ya": "や", "yu": "ゆ", "yo": "よ"})
for c, ks in {"sh": "しゃしゅしょ", "ch": "ちゃちゅちょ", "j": "じゃじゅじょ", "ky": "きゃきゅきょ", "gy": "ぎゃぎゅぎょ",
              "ny": "にゃにゅにょ", "hy": "ひゃひゅひょ", "my": "みゃみゅみょ", "ry": "りゃりゅりょ", "by": "びゃびゅびょ",
              "py": "ぴゃぴゅぴょ"}.items():
    for v, k in zip("auo", (ks[0:2], ks[2:4], ks[4:6])):
        _SYL[c + v] = k
_PART = {"wa": "は", "o": "を", "ga": "が", "e": "へ"}


def romaji_to_kana(text):
    out = []
    for tok in re.findall(r"[A-Za-zāīūēō']+|[^A-Za-zāīūēō']+", text):
        if not re.match(r"[A-Za-zāīūēō']", tok):
            out.append(tok.replace(",", "、").replace(".", "。").replace("?", "？")); continue
        t = tok.lower().replace("ā", "aa").replace("ī", "ii").replace("ū", "uu").replace("ē", "ee").replace("ō", "ou")
        if t in _PART:
            out.append(_PART[t]); continue
        res, i = "", 0
        while i < len(t):
            if i + 1 < len(t) and t[i] == t[i + 1] and t[i] not in "aiueon":
                res += "っ"; i += 1; continue
            for L in (3, 2, 1):
                if t[i:i + L] in _SYL:
                    res += _SYL[t[i:i + L]]; i += L; break
            else:
                res += t[i]; i += 1
        out.append(res)
    return "".join(out)


# ---------- pipeline ----------
def summarize(text: str, model: str, on_progress=None) -> dict:
    """Transcription (texte brut, 1 segment/ligne) -> synthèse structurée validée."""
    lines = [l for l in text.splitlines() if l.strip()]
    n_lines = [norm(l) for l in lines]
    n_all = " ".join(n_lines)
    parts = chunks(lines)
    raw, homework = [], []
    stats = {"examples_total": 0, "examples_kept": 0}

    for i, part in enumerate(parts, 1):
        if on_progress:
            on_progress((i - 1) / (len(parts) + 1), f"Synthèse : extraction {i}/{len(parts)}…")
        d = call(model, EXTRACT_PROMPT.format(text="\n".join(part), i=i, n=len(parts)), EXTRACT_SCHEMA)
        for s in d["sections"]:
            exs = []
            for e in s["examples"]:
                stats["examples_total"] += 1
                if quote_ok(e["quote"], n_lines, n_all):
                    stats["examples_kept"] += 1
                    exs.append({"romaji": clean(e["quote"]), "japanese": romaji_to_kana(clean(e["quote"])),
                                "french": clean(e["french"])})
            raw.append({"title": clean(s["title"]), "key_points": [clean(k) for k in s["key_points"] if k.strip()],
                        "examples": exs})
        homework += [clean(h) for h in d["homework"]]

    if on_progress:
        on_progress(len(parts) / (len(parts) + 1), "Synthèse : regroupement des sections…")
    listing = "\n".join(f"{k}. {s['title']} — " + " / ".join(s["key_points"])[:160] for k, s in enumerate(raw))
    g = call(model, GROUP_PROMPT.format(listing=listing), GROUP_SCHEMA)
    seen, sections = set(), []
    for grp in g["groups"]:
        pts, exs = [], []
        for m in grp["members"]:
            if m in seen or not (0 <= m < len(raw)):
                continue
            seen.add(m)
            for p in raw[m]["key_points"]:
                if norm(p) not in {norm(x) for x in pts}:
                    pts.append(p)
            for e in raw[m]["examples"]:
                if norm(e["romaji"]) not in {norm(x["romaji"]) for x in exs}:
                    exs.append(e)
        if pts:
            sections.append({"title": clean(grp["title"]), "key_points": pts, "examples": exs})
    for k in range(len(raw)):  # rien ne se perd : sections non classées gardées
        if k not in seen:
            sections.append(raw[k])
    return {"title": clean(g["title"]), "subtitle": clean(g["subtitle"]), "sections": sections,
            "homework": list(dict.fromkeys(h for h in homework if h)), "stats": stats, "model": model}
