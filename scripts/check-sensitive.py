#!/usr/bin/env python3
"""Détecte les données sensibles avant publication : secrets, chemins personnels, données de cours, URL signées.

Usage : python scripts/check-sensitive.py          (analyse les fichiers suivis par git, ou tout le dossier hors .gitignore)
Code de sortie 1 si quelque chose est trouvé. Exécuté aussi par la CI.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (nom, motif) — appliqué au contenu texte des fichiers
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("clé privée", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("jeton GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("clé AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jeton API (sk-…)", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("jeton Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("URL signée YouTube/Google", re.compile(r"googlevideo\.com|[?&]sig=[A-Za-z0-9%_-]{20,}")),
    ("chemin utilisateur Windows", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<|%|\{|\$|VOTRE|YOU|USER|nom|\.\.\.)[A-Za-z0-9._-]+", re.I)),
    ("chemin utilisateur Unix", re.compile(r"/(?:home|Users)/(?!<|\$|\{|you|user|nom)[a-z0-9._-]{2,}/")),
    ("adresse e-mail", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.|users\.noreply\.github\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("affectation de secret", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]

# Fichiers qui ne doivent jamais être suivis (données de cours, binaires audio/vidéo, journaux, secrets)
FORBIDDEN_NAMES = re.compile(
    r"(^|/)(data/|\.env($|\.)|.*\.(m4a|mp3|wav|flac|ogg|opus|mp4|mkv|mov|avi|webm|srt|log|pem|key|pfx|p12)$)", re.I)

SKIP_SUFFIXES = {".png", ".ico", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".exe", ".zip", ".lock"}
SKIP_FILES = {"package-lock.json", "check-sensitive.py"}  # ce script contient les motifs eux-mêmes


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
        return [l for l in out.splitlines() if l]
    except Exception:  # noqa: BLE001 - pas de dépôt git : on parcourt le dossier
        return [str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*") if p.is_file()]


def main() -> int:
    problems: list[str] = []
    files = tracked_files()
    for rel in files:
        if FORBIDDEN_NAMES.search(rel):
            problems.append(f"{rel}: fichier qui ne doit pas être publié (données, média, journal ou secret)")
            continue
        p = ROOT / rel
        if p.suffix.lower() in SKIP_SUFFIXES or p.name in SKIP_FILES or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pat in PATTERNS:
                m = pat.search(line)
                if m:
                    problems.append(f"{rel}:{lineno}: {name} → « {m.group(0)[:60]} »")
    print(f"{len(files)} fichiers analysés.")
    if problems:
        print("\n⚠ Éléments sensibles détectés :")
        print("\n".join("  - " + x for x in problems))
        return 1
    print("✔ Aucune donnée sensible détectée.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
