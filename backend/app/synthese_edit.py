"""Édition manuelle de la synthèse : validation stricte, sauvegarde de l'original, régénération de la présentation (sans IA)."""
import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .deck import render_deck

ORIGINAL = "synthese.original.json"


def _clean(s: str) -> str:
    return " ".join(s.replace("\x00", "").split())


class ExampleIn(BaseModel):
    japanese: str = Field(default="", max_length=400)
    romaji: str = Field(default="", max_length=400)
    french: str = Field(default="", max_length=400)

    @field_validator("*")
    @classmethod
    def _c(cls, v: str) -> str:
        return _clean(v)


class SectionIn(BaseModel):
    title: str = Field(max_length=200)
    key_points: list[str] = Field(default_factory=list, max_length=40)
    examples: list[ExampleIn] = Field(default_factory=list, max_length=40)

    @field_validator("title")
    @classmethod
    def _t(cls, v: str) -> str:
        return _clean(v)

    @field_validator("key_points")
    @classmethod
    def _k(cls, v: list[str]) -> list[str]:
        out = [_clean(x) for x in v]
        if any(len(x) > 800 for x in out):
            raise ValueError("Un point clé dépasse 800 caractères.")
        return [x for x in out if x]


class SyntheseIn(BaseModel):
    title: str = Field(max_length=200)
    subtitle: str = Field(default="", max_length=300)
    sections: list[SectionIn] = Field(min_length=1, max_length=80)
    homework: list[str] = Field(default_factory=list, max_length=80)

    @field_validator("title", "subtitle")
    @classmethod
    def _t(cls, v: str) -> str:
        return _clean(v)

    @field_validator("homework")
    @classmethod
    def _h(cls, v: list[str]) -> list[str]:
        out = [_clean(x) for x in v]
        if any(len(x) > 800 for x in out):
            raise ValueError("Un devoir dépasse 800 caractères.")
        return [x for x in out if x]


def normalize(body: SyntheseIn) -> dict:
    """Retire les lignes vides : un exemple sans japonais ni français, une section sans titre."""
    d = body.model_dump()
    d["sections"] = [
        {**s, "examples": [e for e in s["examples"] if e["japanese"] or e["french"]]}
        for s in d["sections"] if s["title"]
    ]
    if not d["sections"]:
        raise ValueError("Il faut au moins une section avec un titre.")
    if not d["title"]:
        raise ValueError("Le titre ne peut pas être vide.")
    return d


def save(job_dir: Path, body: SyntheseIn, course_label: str) -> dict:
    new = normalize(body)
    path = job_dir / "synthese.json"
    cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    orig = job_dir / ORIGINAL
    if cur and not orig.exists():                      # première modification : on garde la version de l'IA
        orig.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    stats = dict(cur.get("stats") or {})
    stats["edited"] = True
    data = {**cur, **new, "stats": stats}              # conserve course, model, stats
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    render_deck(data, job_dir / "deck.html", course_label)
    return data


def restore(job_dir: Path, course_label: str) -> dict:
    orig = job_dir / ORIGINAL
    if not orig.exists():
        raise FileNotFoundError("Aucune version d'origine à restaurer.")
    data = json.loads(orig.read_text(encoding="utf-8"))
    (job_dir / "synthese.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    render_deck(data, job_dir / "deck.html", course_label)
    orig.unlink()
    return data


def has_original(job_dir: Path) -> bool:
    return (job_dir / ORIGINAL).exists()
