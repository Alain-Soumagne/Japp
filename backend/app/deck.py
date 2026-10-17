"""Génération de la présentation HTML à partir de la synthèse JSON."""
import html
import json
from pathlib import Path

TEMPLATE = Path(__file__).parent / "templates" / "deck.html"


def render_deck(data: dict, out_path: Path, course_label: str = "") -> Path:
    payload = {k: data.get(k) for k in ("title", "subtitle", "sections", "homework")}
    payload["course_label"] = course_label
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__TITLE__", html.escape(data.get("title") or "Synthèse"))
            .replace("__DATA__", blob))
    out_path.write_text(page, encoding="utf-8")
    return out_path
