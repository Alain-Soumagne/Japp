"""File de tâches : une tâche à la fois (le GPU est partagé entre Whisper et le LLM)."""
import json
import queue
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import ollama_mgr
from .config import JOBS_DIR, LLM_MODEL
from .deck import render_deck

# Poids de chaque étape dans la progression globale
STAGES = [("downloading", 0.08), ("transcribing", 0.42), ("preparing_llm", 0.05), ("summarizing", 0.38), ("rendering", 0.07)]
LABELS = {"queued": "En attente", "downloading": "Téléchargement YouTube", "transcribing": "Transcription", "preparing_llm": "Préparation du modèle de synthèse",
          "summarizing": "Synthèse", "rendering": "Création de la présentation", "done": "Terminé", "error": "Erreur"}

_jobs: dict[str, dict] = {}
_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
_lock = threading.Lock()
GPU_LOCK = threading.Lock()   # un seul usage lourd du GPU/Ollama à la fois (transcription, synthèse, exercices)


def _dir(job_id: str) -> Path:
    if not job_id.isalnum():  # ids générés en hexadécimal : refuse tout le reste (../ etc.)
        raise ValueError("id de tâche invalide")
    return JOBS_DIR / job_id


def _save(job: dict) -> None:
    with _lock:
        (_dir(job["id"]) / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def _set(job: dict, **kw) -> None:
    job.update(kw)
    job["updated"] = time.time()
    _save(job)


def _progress(job: dict, stage: str, frac: float, message: str = "") -> None:
    done = 0.0
    for name, w in STAGES:
        if name == stage:
            done += w * max(0.0, min(frac, 1.0))
            break
        done += w
    job.update(stage=stage, progress=round(done, 4), message=message or LABELS.get(stage, ""), updated=time.time())


def load_all() -> None:
    for p in sorted(JOBS_DIR.glob("*/job.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if j["status"] in ("queued", "running"):
                j.update(status="error", error="Interrompu (l'application a été fermée).")
            _jobs[j["id"]] = j
        except Exception:
            pass


def list_jobs() -> list[dict]:
    return sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)


def get(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def create(source_path: Path, name: str, lang: str, model: str, prompt: str, copy: bool) -> dict:
    job_id = uuid.uuid4().hex[:10]
    d = _dir(job_id)
    d.mkdir(parents=True)
    src = source_path
    if copy:
        src = d / ("source" + source_path.suffix)
        shutil.move(str(source_path), src)
    job = {"id": job_id, "name": name, "source": str(src), "lang": lang or "auto", "model": model or LLM_MODEL,
           "prompt": prompt or "", "status": "queued", "stage": "queued", "progress": 0.0, "message": LABELS["queued"],
           "error": None, "created": time.time(), "updated": time.time(), "files": [], "info": {}}
    _jobs[job_id] = job
    _save(job)
    _q.put(("full", job_id))
    return job


def create_youtube(url: str, lang: str, model: str, prompt: str) -> dict:
    """Tâche dont la source est une vidéo YouTube : l'audio est téléchargé par le worker (étape « downloading »)."""
    from .youtube import canonical_url, video_id
    vid = video_id(url)                      # valide et normalise (lève YoutubeError)
    job_id = uuid.uuid4().hex[:10]
    _dir(job_id).mkdir(parents=True)
    job = {"id": job_id, "name": f"YouTube {vid}", "source": "", "url": canonical_url(vid), "lang": lang or "auto",
           "model": model or LLM_MODEL, "prompt": prompt or "", "status": "queued", "stage": "queued", "progress": 0.0,
           "message": LABELS["queued"], "error": None, "created": time.time(), "updated": time.time(), "files": [], "info": {}}
    _jobs[job_id] = job
    _save(job)
    _q.put(("full", job_id))
    return job


def touch(job_id: str) -> None:
    """Marque la tâche comme modifiée (l'interface recharge la présentation et la synthèse)."""
    job = _jobs[job_id]
    _set(job, files=files(job_id))


def resummarize(job_id: str, model: str | None = None) -> dict:
    job = _jobs[job_id]
    if model:
        job["model"] = model
    _set(job, status="queued", stage="queued", progress=0.0, message=LABELS["queued"], error=None)
    _q.put(("summary", job_id))
    return job


def delete(job_id: str) -> None:
    _jobs.pop(job_id, None)
    shutil.rmtree(_dir(job_id), ignore_errors=True)


def files(job_id: str) -> list[str]:
    d = _dir(job_id)
    return [n for n in ("transcript.txt", "transcript.srt", "transcript.md", "synthese.json", "deck.html")
            if (d / n).exists()]


def _run_summary(job: dict) -> None:
    d = _dir(job["id"])
    text = (d / "transcript.txt").read_text(encoding="utf-8")
    model = job["model"]

    _progress(job, "preparing_llm", 0.0, "Démarrage d'Ollama…")
    ollama_mgr.ensure_running()
    if not ollama_mgr.has_model(model):
        _progress(job, "preparing_llm", 0.1, f"Téléchargement du modèle {model}…")
        ollama_mgr.pull(model, lambda f, s: _progress(job, "preparing_llm", 0.1 + 0.8 * f, f"Téléchargement de {model} ({int(f*100)} %)"))
    _progress(job, "preparing_llm", 0.9, "Chargement du modèle…")
    ollama_mgr.warm_up(model)

    from .summarize import summarize
    data = summarize(text, model, lambda f, m: _progress(job, "summarizing", f, m))
    data["course"] = job["name"]
    (d / "synthese.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "synthese.original.json").unlink(missing_ok=True)      # nouvelle synthèse = nouvelle base de référence

    _progress(job, "rendering", 0.5, "Création de la présentation…")
    render_deck(data, d / "deck.html", job["name"])
    ollama_mgr.unload(model)


def _worker() -> None:
    while True:
        kind, job_id = _q.get()
        job = _jobs.get(job_id)
        if not job:
            continue
        GPU_LOCK.acquire()
        try:
            _set(job, status="running", error=None)
            d = _dir(job_id)
            if kind == "full":
                if job.get("url") and not (job["source"] and Path(job["source"]).exists()):
                    from .youtube import download_audio
                    _progress(job, "downloading", 0.0, "Connexion à YouTube…")
                    _save(job)
                    path, meta = download_audio(job["url"], d, lambda f, m, job=job: _progress(job, "downloading", f, m))
                    job.update(source=str(path), name=meta["title"])
                from .transcribe import transcribe
                def on_progress(f, m, job=job):
                    _progress(job, "transcribing", f, m)

                res = transcribe(job["source"], d / "transcript", job["lang"], job["prompt"] or None, on_progress)
                job["info"] = {"language": res["language"], "duration": res["duration"]}
                if job.get("url"):                       # l'audio téléchargé n'est pas conservé
                    Path(job["source"]).unlink(missing_ok=True)
            _run_summary(job)
            _set(job, status="done", stage="done", progress=1.0, message=LABELS["done"], files=files(job_id))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _set(job, status="error", stage="error", error=f"{type(e).__name__}: {e}", message=LABELS["error"],
                 files=files(job_id))
        finally:
            GPU_LOCK.release()


def start() -> None:
    load_all()
    threading.Thread(target=_worker, daemon=True, name="job-worker").start()
