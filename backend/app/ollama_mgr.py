"""Gestion d'Ollama : détection, démarrage (flash attention désactivée pour la RTX 50xx), modèles, chauffe."""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from collections.abc import Callable

from .config import OLLAMA_URL

_proc: subprocess.Popen | None = None


def find_exe() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
        if base:
            p = Path(base) / "Programs" / "Ollama" / "ollama.exe"
            if p.exists():
                return str(p)
            p = Path(base) / "Ollama" / "ollama.exe"
            if p.exists():
                return str(p)
    return None


def _get(path: str, timeout: float = 3):
    with urllib.request.urlopen(OLLAMA_URL + path, timeout=timeout) as r:
        return json.load(r)


def is_running() -> bool:
    try:
        _get("/api/version", 1.5)
        return True
    except Exception:
        return False


def list_models() -> list[str]:
    try:
        return [m["name"] for m in _get("/api/tags")["models"]]
    except Exception:
        return []


def has_model(name: str) -> bool:
    names = list_models()
    return name in names or (":" not in name and f"{name}:latest" in names)


def ensure_running() -> None:
    """Démarre `ollama serve` si besoin. OLLAMA_FLASH_ATTENTION=0 : evite le crash CUDA de gemma4:12b sur RTX 5080."""
    global _proc
    if is_running():
        return
    exe = find_exe()
    if not exe:
        raise RuntimeError("Ollama n'est pas installé (https://ollama.com/download).")
    env = {**os.environ, "OLLAMA_FLASH_ATTENTION": "0"}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    _proc = subprocess.Popen([exe, "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags)
    for _ in range(60):
        if is_running():
            return
        time.sleep(0.5)
    raise RuntimeError("Ollama n'a pas démarré.")


def pull(name: str, on_progress: Callable[[float, str], None] | None = None) -> None:
    ensure_running()
    body = json.dumps({"model": name, "stream": True}).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/pull", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            d = json.loads(line)
            if d.get("error"):
                raise RuntimeError(d["error"])
            if on_progress and d.get("total"):
                on_progress(d.get("completed", 0) / d["total"], d.get("status", ""))


def warm_up(model: str) -> None:
    """Le 1er appel après chargement échoue souvent (500) : on chauffe avec retries."""
    body = json.dumps({"model": model, "stream": False, "think": False, "keep_alive": "10m",
                       "messages": [{"role": "user", "content": "ok"}]}).encode()
    for _ in range(4):
        try:
            req = urllib.request.Request(OLLAMA_URL + "/api/chat", body, {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=600).read()
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(3)
    raise RuntimeError(f"Impossible de charger le modèle {model}.")


def unload(model: str) -> None:
    try:
        body = json.dumps({"model": model, "keep_alive": 0, "messages": []}).encode()
        urllib.request.urlopen(urllib.request.Request(OLLAMA_URL + "/api/chat", body,
                                                      {"Content-Type": "application/json"}), timeout=30).read()
    except Exception:
        pass


def status() -> dict:
    running = is_running()
    # « installé » = exécutable trouvé OU serveur qui répond (installation à un emplacement inhabituel)
    return {"installed": running or find_exe() is not None, "running": running,
            "models": list_models() if running else []}


def stop_own_server() -> None:
    """N'arrête Ollama que s'il a été démarré par l'application (jamais l'instance de l'utilisateur)."""
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=10)
        except Exception:
            _proc.kill()
    _proc = None
