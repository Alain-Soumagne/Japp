"""Routes /vocabulary : récapitulatif du vocabulaire de tous les cours de japonais, régénération, suppression, export CSV."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import jobs, vocabulary
from .config import JOBS_DIR

router = APIRouter(prefix="/vocabulary")


def _courses() -> list[dict]:
    """Cours de japonais terminés, avec l'état de leur vocabulaire."""
    out = []
    for j in jobs.list_jobs():
        if j.get("kind", "course") != "course" or j["status"] not in ("done", "queued", "running"):
            continue
        if not (JOBS_DIR / j["id"] / "transcript.txt").exists():
            continue
        entries = vocabulary.load(JOBS_DIR / j["id"])
        out.append({"id": j["id"], "name": j["name"], "created": j["created"], "busy": j["status"] in ("queued", "running"),
                    "generated": entries is not None, "count": len(entries or []),
                    "kanji": sum(1 for e in entries or [] if e.get("has_kanji")),
                    "error": (j.get("info") or {}).get("vocabulary_error", "")})
    return sorted(out, key=lambda c: c["created"])


def _rows(job_id: str | None = None) -> list[dict]:
    rows = []
    for c in _courses():
        if job_id and c["id"] != job_id:
            continue
        for e in vocabulary.load(JOBS_DIR / c["id"]) or []:
            rows.append({**e, "job_id": c["id"], "course": c["name"]})
    return rows


@router.get("")
def overview() -> dict:
    return {"courses": _courses(), "entries": _rows()}


class Generate(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=50)


@router.post("/generate")
def generate(body: Generate) -> dict:
    started = []
    known = {c["id"]: c for c in _courses()}
    for jid in dict.fromkeys(body.job_ids):
        c = known.get(jid)
        if not c:
            raise HTTPException(404, "Cours inconnu ou sans transcription")
        if c["busy"]:
            raise HTTPException(409, f"« {c['name']} » est déjà en cours de traitement")
    for jid in dict.fromkeys(body.job_ids):
        jobs.regenerate_vocab(jid)
        started.append(jid)
    return {"started": started}


@router.delete("/{job_id}/{entry_id}")
def delete_entry(job_id: str, entry_id: str) -> dict:
    if not (job_id.isalnum() and entry_id.isalnum()) or jobs.get(job_id) is None:
        raise HTTPException(404, "Inconnu")
    if not vocabulary.remove(JOBS_DIR / job_id, entry_id):
        raise HTTPException(404, "Entrée inconnue")
    return {"ok": True}


@router.get("/export.csv")
def export(job_id: str = "") -> Response:
    if job_id and not job_id.isalnum():
        raise HTTPException(422, "Identifiant invalide")
    return Response(vocabulary.to_csv(_rows(job_id or None)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="vocabulaire-japp.csv"'})
