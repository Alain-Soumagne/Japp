"""Routes /exercises : profil, cours disponibles, sessions, correction, contestation."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import exercises, levels
from .config import LLM_MODEL

router = APIRouter(prefix="/exercises")


def _session(sid: str) -> dict:
    s = exercises.load_session(sid) if sid.isalnum() else None
    if not s:
        raise HTTPException(404, "Session inconnue")
    return s


def _view(s: dict) -> dict:
    return exercises.public_view(s)


@router.get("/profile")
def get_profile() -> dict:
    p = exercises.profile()
    return {"level": p["level"], "label": levels.level_label(p["level"]), "history": p["history"][-60:],
            "sessions": len(p["history"]), "default_model": LLM_MODEL}


@router.get("/courses")
def courses() -> list[dict]:
    return exercises.eligible_courses()


@router.get("/sessions")
def sessions() -> list[dict]:
    return exercises.list_sessions()


class NewSession(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=20)
    count: int = Field(default=10, ge=exercises.MIN_COUNT, le=exercises.MAX_COUNT)
    model: str = Field(default="", max_length=101)


@router.post("/sessions")
def create(body: NewSession) -> dict:
    from .main import MODEL_RE
    if body.model and not MODEL_RE.match(body.model):
        raise HTTPException(422, "Nom de modèle invalide")
    try:
        return _view(exercises.create_session(body.job_ids, body.count, body.model))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/sessions/{sid}")
def get_session(sid: str) -> dict:
    return _view(_session(sid))


@router.delete("/sessions/{sid}")
def delete(sid: str) -> dict:
    _session(sid)
    exercises.delete_session(sid)
    return {"ok": True}


class Answers(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict, max_length=60)


@router.put("/sessions/{sid}/answers")
def put_answers(sid: str, body: Answers) -> dict:
    _session(sid)
    exercises.save_answers(sid, body.answers)
    return {"ok": True}


@router.post("/sessions/{sid}/submit")
def submit(sid: str, body: Answers) -> dict:
    _session(sid)
    try:
        return _view(exercises.submit(sid, body.answers))
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


class Contest(BaseModel):
    argument: str = Field(max_length=1000)


@router.post("/sessions/{sid}/questions/{qid}/contest")
def contest(sid: str, qid: str, body: Contest) -> dict:
    _session(sid)
    try:
        return _view(exercises.contest(sid, qid, body.argument))
    except KeyError as e:
        raise HTTPException(404, "Question inconnue") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except exercises.Busy as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Le modèle n'a pas pu réexaminer la correction : {e}") from e


@router.post("/sessions/{sid}/questions/{qid}/exclude")
def exclude(sid: str, qid: str) -> dict:
    _session(sid)
    try:
        return _view(exercises.exclude(sid, qid))
    except KeyError as e:
        raise HTTPException(404, "Question inconnue") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/sessions/{sid}/finalize")
def finalize(sid: str) -> dict:
    _session(sid)
    try:
        return _view(exercises.finalize(sid))
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
