#!/usr/bin/env python3
"""Génère la démonstration publique : une présentation d'exemple (site/demo/deck.html).
Contenu 100 % fictif (scripts/demo/), jamais issu d'un vrai cours.

  python scripts/build-demo.py                 # écrit site/demo/deck.html
  python scripts/build-demo.py --job-dir DIR   # crée en plus une tâche « terminée » dans DIR (captures d'écran de l'interface)
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.deck import render_deck  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--job-dir", help="dossier de données (JAPP_DATA_DIR) où créer une tâche de démonstration")
args = ap.parse_args()

data = json.loads((ROOT / "scripts" / "demo" / "synthese.json").read_text(encoding="utf-8"))
transcript = (ROOT / "scripts" / "demo" / "transcript.txt").read_text(encoding="utf-8")

out = ROOT / "site" / "demo"
out.mkdir(parents=True, exist_ok=True)
render_deck(data, out / "deck.html", "Exemple généré par Japp")
print("écrit :", out / "deck.html")

if args.job_dir:
    d = Path(args.job_dir) / "jobs" / "demo000001"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    render_deck(data, d / "deck.html", "Exemple généré par Japp")
    (d / "synthese.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "transcript.txt").write_text(transcript, encoding="utf-8")
    now = time.time()
    job = {"id": "demo000001", "name": "Cours 1 - Se présenter", "source": "cours1.m4a", "lang": "fr", "model": "gemma4:12b",
           "prompt": "", "status": "done", "stage": "done", "progress": 1.0, "message": "Terminé", "error": None,
           "created": now - 600, "updated": now - 540,
           "files": ["transcript.txt", "synthese.json", "deck.html"], "info": {"language": "fr", "duration": 1080.0}}
    (d / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    print("tâche de démonstration :", d)
