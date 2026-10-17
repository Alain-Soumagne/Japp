"""Tests de sécurité de l'API locale et du rendu de la présentation."""
import json

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.config import DATA_DIR
from pathlib import Path

from app.deck import render_deck
from app.main import app

BASE = "http://127.0.0.1:8765"


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url=BASE) as c:
        yield c


def test_tests_use_isolated_data_dir():
    assert "cours-test-" in str(DATA_DIR)


def test_health_has_no_secrets(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = json.dumps(r.json())
    assert str(DATA_DIR) not in body      # pas de chemin local exposé
    assert "gpu" in r.json()


def test_docs_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code in (404, 405)


def test_foreign_host_rejected_dns_rebinding(client):
    r = client.get("/health", headers={"Host": "evil.example.com:8765"})
    assert r.status_code == 403


def test_cross_site_post_rejected_csrf(client):
    r = client.post("/jobs/from-path", json={"path": "C:/x.mp3"}, headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_same_origin_post_allowed_until_validation(client):
    r = client.post("/jobs/from-path", json={"path": "C:/inexistant.mp3"}, headers={"Origin": BASE})
    assert r.status_code == 404                           # passe le contrôle d'origine, fichier absent


def test_from_path_rejects_non_media(client):
    secret = DATA_DIR / "secret.txt"
    secret.write_text("mot de passe", encoding="utf-8")
    r = client.post("/jobs/from-path", json={"path": str(secret)})
    assert r.status_code == 415


def test_upload_rejects_non_media(client):
    r = client.post("/jobs", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_invalid_options_rejected(client):
    r = client.post("/jobs/from-path", json={"path": "C:/a.mp3", "lang": "xx"})
    assert r.status_code == 422
    r = client.post("/jobs/from-path", json={"path": "C:/a.mp3", "model": "x; rm -rf /"})
    assert r.status_code == 422


def test_job_id_traversal(client):
    for bad in ("..%2F..%2Fetc", "%2e%2e%2f%2e%2e%2fetc", "x%00y", "a%5C..%5Cb"):
        assert client.get(f"/jobs/{bad}").status_code == 404
        assert client.get(f"/jobs/{bad}/files/transcript.txt").status_code == 404


def test_only_whitelisted_files_served(client, tmp_path):
    # crée une tâche factice directement dans le magasin
    jid = "deadbeef01"
    d = DATA_DIR / "jobs" / jid
    d.mkdir(parents=True)
    (d / "transcript.txt").write_text("bonjour", encoding="utf-8")
    (d / "job.json").write_text("{}", encoding="utf-8")
    (d / "autre.txt").write_text("interdit", encoding="utf-8")
    jobs._jobs[jid] = {"id": jid, "status": "done", "created": 0, "files": [], "updated": 0}
    assert client.get(f"/jobs/{jid}/files/transcript.txt").text == "bonjour"
    assert client.get(f"/jobs/{jid}/files/autre.txt").status_code == 404
    assert client.get(f"/jobs/{jid}/files/job.json").status_code == 404
    assert client.get(f"/jobs/{jid}/files/..%2Fjob.json").status_code == 404


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "access-control-allow-origin" not in r.headers  # pas de CORS


def test_deck_escapes_script_injection(tmp_path):
    data = {"title": "</script><script>alert(1)</script>", "subtitle": "x",
            "sections": [{"title": "<img src=x onerror=alert(1)>", "key_points": ["</script>"], "examples": []}],
            "homework": []}
    out = render_deck(data, tmp_path / "deck.html")
    html = out.read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in html        # la donnée ne peut pas fermer la balise <script>
    assert html.count("</script>") == 2                    # uniquement les 2 balises légitimes du modèle
    assert "<title>&lt;/script&gt;" in html                # titre échappé


def test_deck_hides_every_slide_except_current():
    """Régression : une règle `.end{display:grid}` écrasait `.slide{display:none}` (dernière slide toujours visible)."""
    import re
    css = (Path(__file__).parents[1] / "app" / "templates" / "deck.html").read_text(encoding="utf-8")
    assert re.search(r"\.slide\{[^}]*display:none", css)
    for sel, body in re.findall(r"(?m)^(\.[\w.-]+)\{([^}]*)\}", css):
        if "display:" in body and sel.startswith(".") and sel not in (".slide.on", ".slide"):
            first = sel.split(".")[1]
            assert not (first in ("end", "cover") and sel == "." + first and "display:" in body), f"{sel} peut afficher une slide masquée"
