"""API locale (FastAPI) de l'application Cours → Transcription → Synthèse → Présentation."""
import asyncio
import json
import os
import re
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import jobs, ollama_mgr
from .config import JOBS_DIR, LLM_CHOICES, LLM_MODEL, WHISPER_MODEL

@asynccontextmanager
async def _lifespan(_: FastAPI):
    jobs.start()
    yield
    ollama_mgr.stop_own_server()


app = FastAPI(title="Cours Transcriber", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)

# ---------------------------------------------------------------------------
# Sécurité : l'API n'écoute que sur 127.0.0.1 et ne doit pas être pilotable depuis une page web quelconque.
#  - pas de CORS (l'interface est servie par le même serveur => même origine) ;
#  - contrôle du Host  : bloque le "DNS rebinding" (une page web qui résout son domaine vers 127.0.0.1) ;
#  - contrôle de l'Origin sur les requêtes qui modifient l'état : bloque le CSRF depuis un site tiers.
# ---------------------------------------------------------------------------
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
EXTRA_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get("COURS_DEV_ORIGINS", "").split(",") if o.strip()}
MEDIA_EXT = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".mp4", ".mkv", ".mov",
             ".avi", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp"}
MAX_UPLOAD = 20 * 1024 ** 3  # 20 Go
LANGS = {"auto", "fr", "ja", "en"}
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,100}$")


def _host_only(host_header: str) -> str:
    return host_header.rsplit(":", 1)[0] if not host_header.endswith("]") else host_header


@app.middleware("http")
async def _security(request: Request, call_next):
    host = _host_only(request.headers.get("host", ""))
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Hôte non autorisé"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin:
            o = urlparse(origin)
            same = o.hostname in {"127.0.0.1", "localhost", "::1"} and (o.port or 80) == (request.url.port or 80)
            if not same and origin.rstrip("/") not in EXTRA_ORIGINS:
                return JSONResponse({"detail": "Origine non autorisée"}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.url.path.endswith("/files/deck.html"):
        # présentation générée : scripts/styles inline uniquement, aucun accès réseau
        resp.headers["Content-Security-Policy"] = ("default-src 'none'; script-src 'unsafe-inline'; "
                                                   "style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'")
    elif not request.url.path.startswith("/jobs"):
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                                   "img-src 'self' data:; connect-src 'self'; frame-src 'self'; "
                                                   "object-src 'none'; base-uri 'self'; form-action 'self'")
    return resp


def _gpu() -> dict:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip().splitlines()[0]
        name, total, used = [x.strip() for x in out.split(",")]
        return {"name": name, "vram_total_mb": int(total), "vram_used_mb": int(used)}
    except Exception:
        return {"name": None}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "gpu": _gpu(), "whisper_model": WHISPER_MODEL,
            "ollama": ollama_mgr.status(), "llm_default": LLM_MODEL, "llm_choices": LLM_CHOICES}


def _check_options(lang: str, model: str, prompt: str) -> tuple[str, str, str]:
    if lang not in LANGS:
        raise HTTPException(422, "Langue non supportée")
    if model and not MODEL_RE.match(model):
        raise HTTPException(422, "Nom de modèle invalide")
    return lang, model, prompt[:2000]


class FromPath(BaseModel):
    path: str = Field(max_length=1024)
    lang: str = "auto"
    model: str = ""
    prompt: str = ""


@app.post("/jobs/from-path")
def create_from_path(body: FromPath) -> dict:
    lang, model, prompt = _check_options(body.lang, body.model, body.prompt)
    p = Path(body.path)
    if p.suffix.lower() not in MEDIA_EXT:
        raise HTTPException(415, "Type de fichier non supporté (audio/vidéo uniquement)")
    if not p.is_file():
        raise HTTPException(404, "Fichier introuvable")
    return jobs.create(p.resolve(), p.stem, lang, model, prompt, copy=False)


@app.post("/jobs")
async def create_upload(file: UploadFile = File(...), lang: str = Form("auto"), model: str = Form(""),
                        prompt: str = Form("")) -> dict:
    lang, model, prompt = _check_options(lang, model, prompt)
    safe = Path(file.filename or "cours").name
    ext = Path(safe).suffix.lower()
    if ext not in MEDIA_EXT:
        raise HTTPException(415, "Type de fichier non supporté (audio/vidéo uniquement)")
    tmp = JOBS_DIR / f"upload_{uuid.uuid4().hex}{ext}"
    size = 0
    try:
        with tmp.open("wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Fichier trop volumineux")
                f.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return jobs.create(tmp, Path(safe).stem, lang, model, prompt, copy=True)


@app.get("/jobs")
def list_jobs() -> list[dict]:
    return jobs.list_jobs()


def _need(job_id: str) -> dict:
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "Tâche inconnue")
    return j


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    j = _need(job_id)
    return {**j, "files": jobs.files(job_id)}


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    _need(job_id)
    jobs.delete(job_id)
    return {"ok": True}


@app.get("/jobs/{job_id}/events")
async def events(job_id: str) -> StreamingResponse:
    _need(job_id)

    async def gen():
        last = None
        while True:
            j = jobs.get(job_id)
            if not j:
                break
            snap = json.dumps({**j, "files": jobs.files(job_id)}, ensure_ascii=False)
            if snap != last:
                yield f"data: {snap}\n\n"
                last = snap
            if j["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


ALLOWED = {"transcript.txt", "transcript.srt", "transcript.md", "synthese.json", "deck.html"}


@app.get("/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str, download: bool = False):
    _need(job_id)
    if name not in ALLOWED:
        raise HTTPException(404)
    p = JOBS_DIR / job_id / name
    if not p.exists():
        raise HTTPException(404, "Fichier pas encore généré")
    return FileResponse(p, filename=name if download else None)


class TranscriptBody(BaseModel):
    text: str = Field(max_length=5_000_000)


@app.put("/jobs/{job_id}/transcript")
def put_transcript(job_id: str, body: TranscriptBody) -> dict:
    _need(job_id)
    (JOBS_DIR / job_id / "transcript.txt").write_text(body.text, encoding="utf-8")
    return {"ok": True}


class ResumBody(BaseModel):
    model: str = Field(default="", max_length=101)


@app.post("/jobs/{job_id}/resummarize")
def resummarize(job_id: str, body: ResumBody) -> dict:
    j = _need(job_id)
    if body.model and not MODEL_RE.match(body.model):
        raise HTTPException(422, "Nom de modèle invalide")
    if j["status"] in ("queued", "running"):
        raise HTTPException(409, "Tâche déjà en cours")
    if not (JOBS_DIR / job_id / "transcript.txt").exists():
        raise HTTPException(409, "Pas de transcription")
    return jobs.resummarize(job_id, body.model or None)


# --- Interface Angular servie par le backend (même origine -> pas de CORS, pas de souci de base href) ---
import os  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONT = Path(os.environ.get("COURS_FRONTEND_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist" / "frontend" / "browser"))
if _FRONT.exists():
    app.mount("/", StaticFiles(directory=_FRONT, html=True), name="ui")
