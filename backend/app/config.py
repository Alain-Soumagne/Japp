"""Configuration centrale du backend."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("COURS_DATA_DIR", ROOT.parent / "data"))
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL = os.environ.get("COURS_WHISPER_MODEL", "large-v3")
LLM_MODEL = os.environ.get("COURS_LLM_MODEL", "gemma4:12b")
OLLAMA_URL = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434").rstrip("/")
# Les appels HTTP du backend ne ciblent que ce serveur : on refuse tout autre schéma (file:, ftp:…).
if not OLLAMA_URL.startswith(("http://", "https://")):
    raise ValueError("OLLAMA_HOST_URL doit commencer par http:// ou https://")

LLM_CHOICES = ["gemma4:12b", "gemma4:e4b", "qwen3:14b"]  # ordre = préférence
