import json
import time

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.config import JOBS_DIR
from app.main import app

SYN = {
    "title": "Cours test", "subtitle": "Sous-titre", "course": "Cours test", "model": "m", "stats": {"examples_total": 2, "examples_kept": 2},
    "sections": [
        {"title": "A", "key_points": ["p1", "p2"], "examples": [{"japanese": "こんにちは", "romaji": "konnichiwa", "french": "bonjour"}]},
        {"title": "B", "key_points": ["q1"], "examples": []},
    ],
    "homework": ["h1", "h2"],
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture()
def job():
    jid = "edit" + str(int(time.time() * 1000))[-6:]
    d = JOBS_DIR / jid
    d.mkdir(parents=True)
    (d / "synthese.json").write_text(json.dumps(SYN, ensure_ascii=False), encoding="utf-8")
    jobs._jobs[jid] = {"id": jid, "name": "Cours test", "source": "", "status": "done", "stage": "done", "progress": 1.0,
                       "message": "", "error": None, "created": time.time(), "updated": time.time(), "files": [], "info": {},
                       "lang": "fr", "model": "m", "prompt": ""}
    yield jid
    jobs._jobs.pop(jid, None)


def body(**kw):
    b = json.loads(json.dumps(SYN))
    for k in ("course", "model", "stats"):
        b.pop(k)
    b.update(kw)
    return b


def test_supprimer_section_et_original_conserve(client, job):
    b = body(sections=[SYN["sections"][0]])
    r = client.put(f"/jobs/{job}/synthese", json=b)
    assert r.status_code == 200 and r.json()["can_restore"]
    cur = json.loads((JOBS_DIR / job / "synthese.json").read_text(encoding="utf-8"))
    assert [s["title"] for s in cur["sections"]] == ["A"]
    assert cur["model"] == "m" and cur["stats"]["edited"] is True       # champs non éditables conservés
    orig = json.loads((JOBS_DIR / job / "synthese.original.json").read_text(encoding="utf-8"))
    assert len(orig["sections"]) == 2
    deck = (JOBS_DIR / job / "deck.html").read_text(encoding="utf-8")
    assert "Cours test" in deck and '"title": "B"' not in deck and '"title":"B"' not in deck


def test_original_pas_ecrase_par_une_seconde_edition(client, job):
    client.put(f"/jobs/{job}/synthese", json=body(title="V1"))
    client.put(f"/jobs/{job}/synthese", json=body(title="V2"))
    orig = json.loads((JOBS_DIR / job / "synthese.original.json").read_text(encoding="utf-8"))
    assert orig["title"] == "Cours test"


def test_restaurer(client, job):
    client.put(f"/jobs/{job}/synthese", json=body(title="Modifié"))
    r = client.post(f"/jobs/{job}/synthese/restore")
    assert r.status_code == 200 and r.json()["synthese"]["title"] == "Cours test"
    assert client.post(f"/jobs/{job}/synthese/restore").status_code == 404
    assert client.get(f"/jobs/{job}/synthese/status").json() == {"can_restore": False}


@pytest.mark.parametrize("patch", [
    {"sections": []},
    {"sections": [{"title": "", "key_points": [], "examples": []}]},
    {"title": "   "},
    {"title": "x" * 500},
    {"homework": ["x" * 900]},
    {"sections": [{"title": "A", "key_points": ["y" * 900], "examples": []}]},
])
def test_refus_donnees_invalides(client, job, patch):
    assert client.put(f"/jobs/{job}/synthese", json=body(**patch)).status_code == 422


def test_nettoyage_lignes_vides_et_espaces(client, job):
    b = body(homework=["  a   b ", "", "   "],
             sections=[{"title": " T ", "key_points": [" ", "ok  ok"], "examples": [{"japanese": "", "romaji": "x", "french": ""}]}])
    d = client.put(f"/jobs/{job}/synthese", json=b).json()["synthese"]
    assert d["homework"] == ["a b"] and d["sections"][0]["key_points"] == ["ok ok"] and d["sections"][0]["examples"] == []


def test_refuse_pendant_un_traitement(client, job):
    jobs._jobs[job]["status"] = "running"
    assert client.put(f"/jobs/{job}/synthese", json=body()).status_code == 409


def test_job_inconnu_et_origin(client):
    assert client.put("/jobs/inconnu/synthese", json=body()).status_code == 404
    assert client.put("/jobs/x/synthese", json=body(), headers={"Origin": "https://evil.example"}).status_code == 403


def test_script_dans_le_texte_ne_sort_pas_du_json_du_deck(client, job):
    client.put(f"/jobs/{job}/synthese", json=body(title="</script><script>alert(1)</script>"))
    deck = (JOBS_DIR / job / "deck.html").read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in deck
