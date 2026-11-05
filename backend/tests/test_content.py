"""Type de contenu, langues (#17, #18) et vocabulaire (#16)."""
import time

import pytest
from fastapi.testclient import TestClient

from app import jobs, summarize, vocabulary
from app.config import JOBS_DIR
from app.main import app
from app.transcribe import whisper_options

TEXT = """Hello everyone, today we talk about the past tense.
We add ed to regular verbs: I walked to school yesterday.
Homework: learn ten irregular verbs.
Hello everyone, welcome again.
"""


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


# ---- options de langue
def test_options_whisper():
    assert whisper_options("auto", None) == (None, None)
    assert whisper_options("en", "mots") == ("en", "mots")
    assert whisper_options("de", "") == ("de", None)


def test_api_refuse_options_incoherentes(client):
    assert client.post("/jobs/from-path", json={"path": "C:/x.mp3", "lang": "fr_kana"}).status_code == 422
    assert client.post("/jobs/from-path", json={"path": "C:/x.mp3", "kind": "nope"}).status_code == 422
    assert client.post("/jobs/from-path", json={"path": "C:/x.mp3", "lang": "klingon"}).status_code == 422


@pytest.mark.parametrize("lang", ["en", "de", "fr", "ja", "auto"])
def test_api_accepte_les_langues(client, lang, tmp_path, monkeypatch):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    monkeypatch.setattr(jobs._q, "put", lambda *_: None)       # ne pas lancer de vrai traitement
    r = client.post("/jobs/from-path", json={"path": str(f), "lang": lang, "kind": "course"})
    assert r.status_code == 200 and r.json()["lang"] == lang and r.json()["kind"] == "course"
    client.delete(f"/jobs/{r.json()['id']}")


# ---- synthèse « autre contenu » (modèle simulé)
def fake_call(model, prompt, schema):
    if "sections finales" in prompt:
        return {"groups": [{"title": "Le prétérit", "members": [0]}], "title": "Cours d'anglais", "subtitle": "Passé simple"}
    assert "japonais" not in prompt.split("EXTRAIT")[0].lower().replace("n'écris jamais de japonais", "")
    return {"sections": [{"title": "Prétérit", "key_points": ["On ajoute ed aux verbes réguliers."], "examples": [
        {"quote": "I walked to school yesterday", "french": "Je suis allé à l'école à pied hier."},
        {"quote": "I flew to the moon", "french": "invention"}]}], "homework": ["Apprendre dix verbes irréguliers."]}


def test_synthese_autre_contenu_sans_japonais(monkeypatch):
    monkeypatch.setattr(summarize, "call", fake_call)
    d = summarize.summarize(TEXT, "m", kind="other", lang="en")
    assert d["kind"] == "other"
    ex = d["sections"][0]["examples"]
    assert ex == [{"source": "I walked to school yesterday", "french": "Je suis allé à l'école à pied hier."}]   # la citation inventée est écartée
    assert "japanese" not in ex[0] and "romaji" not in ex[0]
    assert d["stats"] == {"examples_total": 2, "examples_kept": 1}


def test_synthese_cours_inchangee(monkeypatch):
    def call(model, prompt, schema):
        if "Regroupe" in prompt:
            return {"groups": [{"title": "Salut", "members": [0]}], "title": "T", "subtitle": "S"}
        return {"sections": [{"title": "Salut", "key_points": ["p"], "examples": [{"quote": "konnichiwa", "french": "bonjour"}]}], "homework": []}
    monkeypatch.setattr(summarize, "call", call)
    d = summarize.summarize("sensei: konnichiwa minna\nkonnichiwa", "m")
    e = d["sections"][0]["examples"][0]
    assert d["kind"] == "course" and e["romaji"] == "konnichiwa" and e["japanese"] and "source" not in e


def test_citation_francaise_acceptee_seulement_pour_autre_contenu():
    n_lines = [summarize.norm("Il est important de revoir la leçon")]
    n_all = " ".join(n_lines)
    q = "Il est important de revoir la leçon"
    assert not summarize.quote_ok(q, n_lines, n_all)
    assert summarize.quote_ok(q, n_lines, n_all, allow_french=True)


# ---- vocabulaire
TRANSCRIPT = "Alors gakusei veut dire étudiant.\nNihongo c'est la langue japonaise.\nEt arigatou, merci."


def raw(**kw):
    return {"heard": "gakusei", "kanji": "学生", "kana": "がくせい", "french": "étudiant", **kw}


def test_vocabulaire_valide_et_filtre():
    words = [
        raw(),                                                                       # ok
        {"heard": "nihongo", "kanji": "日本語", "kana": "にほんご", "french": "japonais"},   # ok
        {"heard": "arigatou", "kanji": "", "kana": "ありがとう", "french": "merci"},         # ok sans kanji
        raw(heard="kuruma", kanji="車", kana="くるま", french="voiture"),                  # jamais prononcé -> écarté
        raw(heard="gakusei", kana="せんせい", french="x"),                                 # lecture incohérente -> écarté
        raw(french=""),                                                              # sans traduction -> écarté
        {"heard": "nihongo", "kanji": "日本語", "kana": "にほんご", "french": "doublon"},   # doublon -> écarté
        {"heard": "arigatou", "kanji": "abc", "kana": "ありがとう", "french": "merci2"},     # faux kanji -> sans kanji, doublon écarté
    ]
    out = vocabulary.validate(words, TRANSCRIPT)
    assert [(e["word"], e["has_kanji"]) for e in out] == [("学生", True), ("日本語", True), ("ありがとう", False)]
    assert out[0]["romaji"] == "gakusei" and out[0]["kana"] == "がくせい"
    assert len({e["id"] for e in out}) == 3


def test_vocabulaire_transcription_en_japonais():
    out = vocabulary.validate([{"heard": "学生", "kanji": "学生", "kana": "がくせい", "french": "étudiant"}], "私は学生です。")
    assert out and out[0]["romaji"] == ""
    assert vocabulary.validate([{"heard": "先生", "kanji": "先生", "kana": "せんせい", "french": "professeur"}], "私は学生です。") == []


def test_csv_neutralise_les_formules():
    csv = vocabulary.to_csv([{"word": "=CMD()", "kana": "a", "romaji": "", "french": '+1 "x"', "course": "C"}])
    assert csv.startswith("\ufeff") and '"\'=CMD()"' in csv and '"\'+1 ""x"""' in csv


# ---- API vocabulaire
@pytest.fixture()
def course():
    jid = "voc" + str(int(time.time() * 1000))[-6:]
    d = JOBS_DIR / jid
    d.mkdir(parents=True)
    (d / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
    jobs._jobs[jid] = {"id": jid, "name": "Cours V", "kind": "course", "status": "done", "created": time.time(), "updated": time.time(),
                       "files": [], "info": {}}
    vocabulary.save(d, vocabulary.validate([raw()], TRANSCRIPT), "m")
    yield jid
    jobs._jobs.pop(jid, None)


def test_api_vocabulaire(client, course):
    r = client.get("/vocabulary").json()
    c = next(x for x in r["courses"] if x["id"] == course)
    assert c["generated"] and c["count"] == 1 and c["kanji"] == 1
    e = next(x for x in r["entries"] if x["job_id"] == course)
    assert e["word"] == "学生" and e["course"] == "Cours V"
    csv = client.get("/vocabulary/export.csv", params={"job_id": course})
    assert csv.status_code == 200 and "学生" in csv.text and "attachment" in csv.headers["content-disposition"]
    assert client.delete(f"/vocabulary/{course}/{e['id']}").status_code == 200
    assert client.delete(f"/vocabulary/{course}/{e['id']}").status_code == 404
    assert client.get("/vocabulary").json()["entries"] == [x for x in client.get("/vocabulary").json()["entries"] if x["job_id"] != course]


def test_api_vocabulaire_refus(client, course):
    assert client.post("/vocabulary/generate", json={"job_ids": ["nope"]}).status_code == 404
    assert client.delete("/vocabulary/..%2f/x").status_code in (404, 405)
    assert client.get("/vocabulary/export.csv", params={"job_id": "a/b"}).status_code == 422
    assert client.post("/vocabulary/generate", json={"job_ids": [course]}, headers={"Origin": "https://evil.example"}).status_code == 403
    jobs._jobs[course]["status"] = "running"
    assert client.post("/vocabulary/generate", json={"job_ids": [course]}).status_code == 409


def test_les_contenus_autres_n_ont_pas_de_vocabulaire(client, course):
    jobs._jobs[course]["kind"] = "other"
    assert all(c["id"] != course for c in client.get("/vocabulary").json()["courses"])


# ---- filtres issus d'un essai réel sur un cours de 19 minutes (gemma4:12b)
@pytest.mark.parametrize("heard", ["Hon wa omoi desu", "Naruto wa oishii ramen o taberu", "WATASHIWA SUSHI GA SUKI", "Yumeina manga desu",
                                   "Sai wa hon o kau", "本は重いです", "イノスケは山を見る", "天気はいいです"])
def test_phrases_ecartees(heard):
    assert vocabulary.looks_like_sentence(heard)


@pytest.mark.parametrize("heard", ["konnichiwa", "ohayou gozaimasu", "minna-san", "shiroi kabe", "ramen otabelu", "Oishikunai", "好き",
                                   "おはようございます", "黄色い帽子"])
def test_mots_et_expressions_gardes(heard):
    assert not vocabulary.looks_like_sentence(heard)


def test_romaji_epele_et_composes():
    assert vocabulary.display_romaji("a-ka-i") == "akai"
    assert vocabulary.display_romaji("chai-ro") == "chairo"
    assert vocabulary.display_romaji("minna-san") == "minna-san"
    assert vocabulary.display_romaji("Aka") == "Aka"


def test_noms_propres_syllabes_et_phrases_ecartes_a_la_validation():
    text = "Sakura mange. shi sa su. Hon wa omoi desu. monge. akai"
    words = [
        {"heard": "Sakura", "kanji": "", "kana": "さくら", "french": "Sakura"},               # nom propre : traduction = mot
        {"heard": "shi", "kanji": "", "kana": "し", "french": "shi (syllabe)"},                # syllabe isolée
        {"heard": "Hon wa omoi desu", "kanji": "本は重いです", "kana": "ほんはおもいです", "french": "Le livre est lourd"},
        {"heard": "akai", "kanji": "赤い", "kana": "あかい", "french": "rouge"},
    ]
    out = vocabulary.validate(words, text)
    assert [e["word"] for e in out] == ["赤い"]
