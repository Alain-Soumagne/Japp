import json
import time

import pytest
from fastapi.testclient import TestClient

from app import exercises as ex
from app import jobs, levels
from app.config import JOBS_DIR
from app.main import app

SYN = {"title": "T", "subtitle": "", "sections": [{"title": "S", "key_points": ["p"], "examples": [
    {"japanese": "おはようございます。", "romaji": "Ohayō gozaimasu.", "french": "Bonjour (le matin)."},
    {"japanese": "ありがとう。", "romaji": "Arigatō.", "french": "Merci."}]}], "homework": []}


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


@pytest.fixture()
def course():
    jid = "exc" + str(int(time.time() * 1000))[-6:]
    d = JOBS_DIR / jid
    d.mkdir(parents=True)
    (d / "synthese.json").write_text(json.dumps(SYN, ensure_ascii=False), encoding="utf-8")
    jobs._jobs[jid] = {"id": jid, "name": "Cours X", "status": "done", "created": time.time(), "updated": time.time(), "files": []}
    yield jid
    jobs._jobs.pop(jid, None)


def wait(client, sid, until, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        s = client.get(f"/exercises/sessions/{sid}").json()
        if s["status"] in until:
            return s
        time.sleep(0.2)
    raise AssertionError(s["status"])


@pytest.fixture()
def no_model(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("modèle indisponible (test)")
    monkeypatch.setattr(ex, "_with_model", boom)


def test_profil_initial(client):
    r = client.get("/exercises/profile").json()
    assert r["level"] == levels.LEVEL_START and r["label"] == "Débutant"


def test_cours_listes(client, course):
    assert any(c["id"] == course and 1 <= c["difficulty"] <= 10 for c in client.get("/exercises/courses").json())


def test_refus_cours_inconnu_et_nombre_hors_bornes(client, course):
    assert client.post("/exercises/sessions", json={"job_ids": ["nope"], "count": 10}).status_code == 422
    assert client.post("/exercises/sessions", json={"job_ids": [course], "count": 999}).status_code == 422
    assert client.post("/exercises/sessions", json={"job_ids": [], "count": 10}).status_code == 422
    assert client.post("/exercises/sessions", json={"job_ids": [course], "count": 10, "model": "a b;rm"}).status_code == 422


def test_session_inconnue_ou_id_piege(client):
    for sid in ("zzz", "..%2f..%2fetc", "a.b"):
        assert client.get(f"/exercises/sessions/{sid}").status_code == 404


def test_origin_etranger_refuse(client, course):
    r = client.post("/exercises/sessions", json={"job_ids": [course], "count": 5}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_parcours_complet_sans_modele(client, course, no_model):
    p0 = client.get("/exercises/profile").json()["level"]
    s = client.post("/exercises/sessions", json={"job_ids": [course], "count": 5}).json()
    sid = s["id"]
    s = wait(client, sid, {"ready", "error"})
    assert s["status"] == "ready" and "indisponibles" in s["notice"]
    # rien de la correction n'est visible avant l'envoi
    for q in s["questions"]:
        assert not ({"reference", "accepted", "verdict", "difficulty", "explanation"} & set(q))
    assert client.post(f"/exercises/sessions/{sid}/finalize").status_code == 409          # pas encore corrigée
    answers = {q["id"]: ("ohayou gozaimasu" if q["type"] == "reading" else "x") for q in s["questions"]}
    assert client.put(f"/exercises/sessions/{sid}/answers", json={"answers": answers}).status_code == 200
    assert client.post(f"/exercises/sessions/{sid}/submit", json={"answers": answers}).status_code == 200
    assert client.post(f"/exercises/sessions/{sid}/submit", json={"answers": answers}).status_code == 409   # une seule fois
    s = wait(client, sid, {"graded", "error"})
    assert s["status"] == "graded" and s["result"]["final"] is False
    assert all(q["verdict"] in levels.POINTS and q["reference"] for q in s["questions"])
    assert "approximatives" in s["notice"] or all(q["graded_by"] == "auto" for q in s["questions"])
    q0 = s["questions"][0]["id"]
    assert client.post(f"/exercises/sessions/{sid}/questions/{q0}/exclude").status_code == 409   # pas sans contestation
    assert client.post(f"/exercises/sessions/{sid}/questions/nope/contest", json={"argument": "parce que"}).status_code == 404
    f = client.post(f"/exercises/sessions/{sid}/finalize").json()
    assert f["status"] == "finalized" and f["result"]["final"] and 0 <= f["result"]["score"] <= 100
    assert abs(f["result"]["level_after"] - f["result"]["level_before"]) <= levels.MAX_STEP + 1e-9
    prof = client.get("/exercises/profile").json()
    assert prof["level"] == f["result"]["level_after"] and prof["sessions"] >= 1 and p0 is not None
    assert client.post(f"/exercises/sessions/{sid}/finalize").status_code == 409          # pas deux fois
    assert client.delete(f"/exercises/sessions/{sid}").status_code == 200
    assert client.get(f"/exercises/sessions/{sid}").status_code == 404
